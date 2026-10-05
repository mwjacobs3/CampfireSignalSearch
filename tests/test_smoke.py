"""Smoke tests — cheap import/config checks that guard against breakage.

These intentionally avoid any network / Supabase access so they run
anywhere (CI, Claude Code web sessions) without secrets.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_source_package_imports() -> None:
    """Every source module imports without side effects (no DB connection at import)."""
    import src.account_import  # noqa: F401
    import src.account_watch_main  # noqa: F401
    import src.alerts  # noqa: F401
    import src.database  # noqa: F401
    import src.enrichment  # noqa: F401
    import src.main  # noqa: F401
    import src.models  # noqa: F401
    from src.scrapers import (  # noqa: F401
        AccountWatchScraper,
        ExecHireScraper,
        FundingFeedScraper,
        GoogleNewsScraper,
        RSSScraper,
    )


def test_example_config_parses() -> None:
    """config.example.yaml is valid YAML and has the expected top-level keys."""
    with open(ROOT / "config.example.yaml") as f:
        cfg = yaml.safe_load(f)
    assert isinstance(cfg, dict)
    assert "scraper" in cfg


def test_trigger_event_model() -> None:
    """The core model can be constructed and knows its event types."""
    from datetime import datetime

    from src.models import EventSource, EventType, TriggerEvent

    assert EventType.FUNDING.value == "funding"
    event = TriggerEvent(
        id="abc",
        title="Test event",
        event_type=EventType.FUNDING,
        source=EventSource.RSS_FEED,
        url="https://example.com/story",
        published_date=datetime.utcnow(),
    )
    assert event.title == "Test event"
    assert event.event_type is EventType.FUNDING
    assert event.pipeline == "icp_scan"  # default — Account Watch sets "account_watch"


def test_account_watch_scraper_constructs() -> None:
    """AccountWatchScraper builds off the same config/keyword lists as the
    other scrapers, and no-ops cleanly with an empty company list."""
    from src.scrapers import AccountWatchScraper

    with open(ROOT / "config.example.yaml") as f:
        cfg = yaml.safe_load(f)
    scraper = AccountWatchScraper(cfg, companies=[])
    assert scraper.scrape() == []


def test_load_owned_companies_csv() -> None:
    """The bundled example export parses into the scraper's company shape,
    matching HubSpot's default 'Company name' / 'Company Domain Name' /
    'Record ID' headers without any renaming."""
    from src.account_import import load_owned_companies_csv

    companies = load_owned_companies_csv(
        str(ROOT / "owned_accounts.example.csv"), portal_id="12345"
    )
    assert len(companies) == 2
    assert companies[0]["name"] == "Acme Robotics"
    assert companies[0]["domain"] == "acmerobotics.com"
    assert companies[0]["hubspot_url"] == (
        "https://app.hubspot.com/contacts/12345/record/0-2/123456789"
    )


def test_load_owned_companies_csv_missing_file() -> None:
    from src.account_import import load_owned_companies_csv

    try:
        load_owned_companies_csv(str(ROOT / "does_not_exist.csv"))
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
