"""
AccountWatchMonitor — HubSpot-owned-accounts signal search.

Runs *alongside* (not instead of) the open-web ICP scan in `src.main`: that
pipeline finds new-account leads across the whole web; this one watches the
accounts you already own in HubSpot for the same four Campfire trigger-event
categories (funding, finance exec hires, ERP-change signals, compliance
readiness), scoped to just those companies.

Usage:
    python -m src.account_watch_main              # run once
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .alerts import AlertManager
from .database import SupabaseManager
from .hubspot_client import HubSpotClient
from .models import TriggerEvent
from .scrapers import AccountWatchScraper


class AccountWatchMonitor:

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.aw_config = self.config.get("account_watch", {})
        self.db = SupabaseManager()
        self.alert_manager = AlertManager(self.config)
        self.hubspot = HubSpotClient()

    @staticmethod
    def _load_config(config_path: str) -> dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            print(f"Config not found: {config_path} — copy config.example.yaml to config.yaml")
            sys.exit(1)
        with open(path) as f:
            return yaml.safe_load(f)

    def run_once(self) -> list[TriggerEvent]:
        print(f"\n{'='*60}")
        print(f"  Campfire Account Watch — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        if not self.aw_config.get("enabled", True):
            print("  Account Watch disabled in config.yaml (account_watch.enabled: false)")
            return []

        if not self.hubspot.configured:
            print("  HUBSPOT_ACCESS_TOKEN not set — skipping. See README for setup.")
            return []

        self.db.verify_schema()

        owner_email = self.aw_config.get("owner_email", "")
        if not owner_email:
            print("  No account_watch.owner_email configured — skipping.")
            return []

        try:
            owner_id = self.hubspot.get_owner_id_by_email(owner_email)
        except Exception as exc:
            print(f"  ERROR looking up HubSpot owner '{owner_email}': {exc}")
            return []
        if not owner_id:
            print(f"  No HubSpot owner found for '{owner_email}' — skipping.")
            return []

        max_companies = int(self.aw_config.get("max_companies", 500))
        try:
            companies = self.hubspot.get_owned_companies(owner_id, max_companies=max_companies)
        except Exception as exc:
            print(f"  ERROR fetching owned companies: {exc}")
            return []

        print(f"  Owned companies  : {len(companies)} (owner: {owner_email})")
        if not companies:
            return []

        scraper = AccountWatchScraper(self.config, companies)
        candidates = scraper.scrape()
        print(f"  Candidate events : {len(candidates)}")
        for s in scraper.source_statuses:
            self.db.save_source_status(
                source_name=s["source_name"],
                source_type=s["source_type"],
                status=s["status"],
                events_found=s.get("events_found", 0),
                error_message=s.get("error_message"),
            )

        max_age_hours = int(self.aw_config.get("max_age_hours", 0))
        cutoff = (
            datetime.utcnow() - timedelta(hours=max_age_hours) if max_age_hours else None
        )
        min_score = float(self.aw_config.get("min_relevance_score", 0))

        new_events: list[TriggerEvent] = []
        for event in candidates:
            if cutoff and event.published_date and event.published_date < cutoff:
                continue
            if min_score > 0 and (event.relevance_score or 0) < min_score:
                continue
            if self.db.has_seen_url(event.url, event.title):
                continue
            new_events.append(event)

        print(f"  New events       : {len(new_events)}")

        saved = 0
        for event in new_events:
            if self.db.save_event(event):
                saved += 1
        print(f"  Saved to Supabase: {saved}")

        if new_events:
            handlers = self.alert_manager.send_alerts(
                new_events,
                heading="Campfire Account Watch — Your Owned HubSpot Accounts",
                subject_label="Campfire Account Watch",
            )
            if not handlers:
                print("  [Email] Not configured — set EMAIL_SENDER / EMAIL_PASSWORD / EMAIL_RECIPIENTS")
            self._print_summary(new_events)
        else:
            print("\n  No new events this cycle.")

        return new_events

    @staticmethod
    def _print_summary(events: list[TriggerEvent]) -> None:
        print(f"\n{'='*60}")
        print("  TOP ACCOUNT WATCH EVENTS")
        print(f"{'='*60}")
        sorted_events = sorted(events, key=lambda e: e.relevance_score, reverse=True)
        for i, e in enumerate(sorted_events[:10], 1):
            print(f"\n  {i}. [{e.event_type.value.upper()}] {e.company_name}")
            print(f"     {e.title[:80]}")
            print(f"     Score   : {e.relevance_score:.0f}/100")
            print(f"     URL     : {e.url}")
        if len(events) > 10:
            print(f"\n  … and {len(events) - 10} more (see dashboard / email digest)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Campfire Account Watch Monitor")
    parser.add_argument("--config", "-c", default="config.yaml")
    args = parser.parse_args()
    AccountWatchMonitor(args.config).run_once()


if __name__ == "__main__":
    main()
