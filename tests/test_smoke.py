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
    import src.alerts  # noqa: F401
    import src.database  # noqa: F401
    import src.enrichment  # noqa: F401
    import src.main  # noqa: F401
    import src.models  # noqa: F401
    from src.scrapers import (  # noqa: F401
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
