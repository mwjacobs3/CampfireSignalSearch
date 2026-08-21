"""
RSS feed scraper for SaaS/startup/finance trade publications.

Sources include TechCrunch, VentureBeat, CFO Dive, Accounting Today, SaaStr,
and BusinessWire / PR Newswire press-release feeds.
"""

from __future__ import annotations

from typing import Any

import feedparser

from ..models import EventSource, TriggerEvent
from .base import BaseScraper


class RSSScraper(BaseScraper):
    """Scrapes SaaS/startup/finance industry RSS feeds."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.feeds = config.get("rss_feeds", [])
        self.max_age_hours = config.get("scraper", {}).get("max_age_hours", 72)
        self.source_statuses: list[dict] = []

    def scrape(self) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        self.source_statuses = []

        for feed_cfg in self.feeds:
            name = feed_cfg.get("name", "Unknown Feed")
            url = feed_cfg.get("url", "")
            if not url:
                continue

            feed_events, status = self._scrape_feed(feed_cfg)
            events.extend(feed_events)
            self.source_statuses.append({
                "source_name": name,
                "source_type": "rss_feed",
                "status": status,
                "events_found": len(feed_events),
            })
            self._sleep()

        return events

    def _scrape_feed(
        self, feed_cfg: dict
    ) -> tuple[list[TriggerEvent], str]:
        name = feed_cfg.get("name", "")
        url = feed_cfg.get("url", "")
        category_hint = feed_cfg.get("category", "")

        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                return [], "error"

            events: list[TriggerEvent] = []
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                summary = self._strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                )
                published_str = entry.get("published", "") or entry.get("updated", "")
                published = self._parse_date(published_str)

                event = self._make_event(
                    title=title,
                    url=link,
                    description=summary,
                    source_name=name,
                    published_date=published,
                    sector_hint=category_hint,
                )
                if event is None:
                    continue

                event.source = EventSource.RSS_FEED
                events.append(event)

            return events, "success" if events else "partial"

        except Exception as exc:
            print(f"  [RSS] Error fetching '{name}': {exc}")
            return [], "error"
