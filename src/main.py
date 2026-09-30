"""
TriggerEventMonitor — main orchestrator for CampfireSignalSearch.

Usage:
    python -m src.main              # run once
    python -m src.main --daemon     # run every N minutes (set in config.yaml)
    python -m src.main --stats      # print Supabase stats and exit
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .alerts import AlertManager
from .database import SupabaseManager
from .enrichment import enrich_event, enrich_hiring_signal
from .models import TriggerEvent
from .scrapers import ExecHireScraper, FundingFeedScraper, GoogleNewsScraper, RSSScraper


class TriggerEventMonitor:

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.db = SupabaseManager()
        self.alert_manager = AlertManager(self.config)
        self.running = True

        self.scrapers = [
            RSSScraper(self.config),
            GoogleNewsScraper(self.config),
            ExecHireScraper(self.config),
            FundingFeedScraper(self.config),
        ]

    # ── Config ────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_config(config_path: str) -> dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            print(f"Config not found: {config_path} — copy config.example.yaml to config.yaml")
            sys.exit(1)
        with open(path) as f:
            return yaml.safe_load(f)

    # ── Main run ──────────────────────────────────────────────────────────────

    def run_once(self) -> list[TriggerEvent]:
        print(f"\n{'='*60}")
        print(f"  Campfire Trigger Event Search — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # Fail-fast guard: if the events table is missing a column the scraper
        # writes, every save silently fails. Surface it before wasting a run.
        self.db.verify_schema()

        max_age_hours = self.config.get("scraper", {}).get("max_age_hours", 0)
        cutoff = (
            datetime.utcnow() - timedelta(hours=max_age_hours)
            if max_age_hours
            else None
        )

        all_events: list[TriggerEvent] = []

        for scraper in self.scrapers:
            name = type(scraper).__name__
            print(f"\n  [{name}]")
            try:
                events = scraper.scrape()
                print(f"    {len(events)} candidate events")
                all_events.extend(events)

                # Persist source health
                if hasattr(scraper, "source_statuses"):
                    for s in scraper.source_statuses:
                        self.db.save_source_status(
                            source_name=s["source_name"],
                            source_type=s["source_type"],
                            status=s["status"],
                            events_found=s.get("events_found", 0),
                            error_message=s.get("error_message"),
                        )
            except Exception as exc:
                print(f"    ERROR: {exc}")

        # Age filter + relevance gate + dedup
        min_score = float(
            self.config.get("scraper", {}).get("min_relevance_score", 0)
        )
        new_events: list[TriggerEvent] = []
        skipped_old = 0
        skipped_low_score = 0
        for event in all_events:
            if cutoff:
                pub = event.published_date
                if pub and pub < cutoff:
                    skipped_old += 1
                    continue
            if min_score > 0 and (event.relevance_score or 0) < min_score:
                skipped_low_score += 1
                continue
            if self.db.has_seen_url(event.url, event.title):
                continue
            new_events.append(event)

        age_note = f"  Too old (>{max_age_hours}h): {skipped_old}\n" if cutoff else ""
        score_note = (
            f"  Below score gate (<{min_score:.0f}): {skipped_low_score}\n"
            if min_score > 0 else ""
        )
        print(f"\n  Total candidates : {len(all_events)}")
        if age_note:
            print(age_note, end="")
        if score_note:
            print(score_note, end="")
        print(f"  New events       : {len(new_events)}")

        # Optional website enrichment — best-effort, never blocks.
        enrichment_cfg = self.config.get("enrichment", {})
        if enrichment_cfg.get("enabled", True) and new_events:
            print(f"  Enriching        : {len(new_events)} events (website fingerprints)")
            timeout = float(enrichment_cfg.get("timeout_seconds", 6))
            ua = self.config.get("scraper", {}).get(
                "user_agent",
                "Mozilla/5.0 (compatible; CampfireSignalSearch/1.0)",
            )
            enriched_count = 0
            hiring_count = 0
            for event in new_events:
                before = len(event.integration_match or [])
                try:
                    enrich_event(event, timeout=timeout, user_agent=ua)
                except Exception as exc:
                    print(f"    Enrichment skipped for {event.company_name or event.url}: {exc}")
                    continue
                if len(event.integration_match or []) > before:
                    enriched_count += 1

                # Independent pass: check the prospect's public Greenhouse/
                # Lever/Ashby job board for open accounting/finance reqs — a
                # real-time hiring signal, separate from anything press-derived.
                try:
                    enrich_hiring_signal(event, timeout=timeout, user_agent=ua)
                except Exception as exc:
                    print(f"    Hiring-signal check skipped for {event.company_name or event.url}: {exc}")
                    continue
                if event.hiring_finance_roles:
                    hiring_count += 1
            print(f"  Integrations +   : {enriched_count} events gained tech-stack hits")
            print(f"  Hiring finance   : {hiring_count} events found an open accounting/finance req")

        # Save + alert
        saved = 0
        failed = 0
        for event in new_events:
            if self.db.save_event(event):
                saved += 1
            else:
                failed += 1

        print(f"  Saved to Supabase: {saved}")
        # A non-zero new-event batch that saves nothing means every insert was
        # rejected (e.g. a schema/column mismatch) — surface it loudly instead
        # of letting the table silently stop growing.
        if failed and saved == 0:
            print(
                f"  WARNING: all {failed} new events FAILED to save to Supabase. "
                "Likely a schema mismatch between models.to_dict() and the "
                "events table — check the [DB] save_event errors above."
            )
        elif failed:
            print(f"  WARNING: {failed} of {len(new_events)} events failed to save.")

        if new_events:
            handlers = self.alert_manager.send_alerts(new_events)
            if not handlers:
                print("  [Email] Not configured — set EMAIL_SENDER / EMAIL_PASSWORD / EMAIL_RECIPIENTS")
            self._print_summary(new_events)
        else:
            print("\n  No new events this cycle.")

        return new_events

    # ── Daemon ────────────────────────────────────────────────────────────────

    def run_daemon(self) -> None:
        interval = self.config.get("scraper", {}).get("check_interval_minutes", 240)
        print(f"Daemon mode — running every {interval} minutes. Ctrl+C to stop.")
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        while self.running:
            try:
                self.run_once()
                if self.running:
                    print(f"\nNext run in {interval} minutes…")
                    for _ in range(interval * 60):
                        if not self.running:
                            break
                        time.sleep(1)
            except Exception as exc:
                print(f"Cycle error: {exc} — retrying in 5 min")
                time.sleep(300)

        print("Daemon stopped.")

    def _handle_signal(self, signum, frame) -> None:
        print("\nShutting down…")
        self.running = False

    # ── Stats ─────────────────────────────────────────────────────────────────

    def show_stats(self) -> None:
        stats = self.db.get_stats()
        print(f"\n{'='*60}")
        print("  SUPABASE STATS")
        print(f"{'='*60}")
        print(f"  Total events: {stats['total_events']}")
        print("\n  By type:")
        for k, v in stats.get("events_by_type", {}).items():
            print(f"    {k:<20} {v}")

    # ── Summary ───────────────────────────────────────────────────────────────

    @staticmethod
    def _print_summary(events: list[TriggerEvent]) -> None:
        print(f"\n{'='*60}")
        print("  TOP NEW EVENTS")
        print(f"{'='*60}")
        sorted_events = sorted(events, key=lambda e: e.relevance_score, reverse=True)
        for i, e in enumerate(sorted_events[:10], 1):
            print(f"\n  {i}. [{e.event_type.value.upper()}] {e.title[:70]}")
            if e.company_name:
                region = "US" if e.is_us_company is True else (
                    e.company_country or "Intl" if e.is_us_company is False else "?"
                )
                hq = f" — {e.hq_city}, {e.hq_state}" if e.hq_city and e.hq_state else ""
                print(f"     Company : {e.company_name} [{region}]{hq}")
            if e.founder_name:
                print(f"     Founder : {e.founder_name}")
            if e.person_name:
                print(f"     Person  : {e.person_name} — {e.person_title or ''}")
            if e.funding_round:
                print(f"     Round   : {e.funding_round} {e.funding_amount or ''}")
            viability = []
            if e.founding_year:
                viability.append(f"founded {e.founding_year}")
            if e.arr:
                viability.append(f"{e.arr}")
            if e.total_funding:
                viability.append(f"{e.total_funding} total")
            if e.employee_count:
                viability.append(f"{e.employee_count} employees")
            if viability:
                print(f"     Company : {' · '.join(viability)}")
            fit = []
            if e.erp_pain_signal:
                fit.append("erp/close pain")
            if e.legacy_erp_mention:
                fit.append("legacy ERP")
            if e.entry_stack_mention:
                fit.append("QuickBooks/Xero")
            if e.integration_match:
                fit.append(f"stack:{'/'.join(e.integration_match[:3])}")
            if e.billing_model:
                fit.append(e.billing_model.lower().replace("_", " "))
            if e.hiring_finance_roles:
                fit.append(f"hiring:{'/'.join(e.open_finance_roles[:3])}")
            if fit:
                print(f"     Fit     : {', '.join(fit)}")
            print(f"     Score   : {e.relevance_score:.0f}/100")
            print(f"     Source  : {e.source_name}")
            print(f"     URL     : {e.url}")
        if len(events) > 10:
            print(f"\n  … and {len(events) - 10} more (see dashboard / email digest)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Campfire Trigger Event Monitor")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--daemon", "-d", action="store_true")
    parser.add_argument("--stats",  "-s", action="store_true")
    args = parser.parse_args()

    monitor = TriggerEventMonitor(args.config)

    if args.stats:
        monitor.show_stats()
    elif args.daemon:
        monitor.run_daemon()
    else:
        monitor.run_once()


if __name__ == "__main__":
    main()
