"""
Funding-focused RSS scraper.

Unlike the CPG-focused predecessor this project was adapted from — which
deliberately dropped TechCrunch/Crunchbase/VentureBeat because AI/SaaS/
fintech rounds are off their ICP — Campfire's ICP *is* AI/SaaS/fintech, so
this scraper leans into the general startup-funding wires plus a couple of
finance-press feeds that specifically cover CFO-side news.
"""

from __future__ import annotations

from typing import Any

import feedparser

from ..models import EventSource, EventType, TriggerEvent
from .base import BaseScraper


FUNDING_FEEDS = [
    {"name": "TechCrunch — Startups", "url": "https://techcrunch.com/category/startups/feed/"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/feed/"},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/"},
    {"name": "FinSMEs — Funding News", "url": "https://www.finsmes.com/feed"},
    {"name": "Inc. — Startups & Funding", "url": "https://www.inc.com/rss/startup.xml"},
    {"name": "CFO Dive", "url": "https://www.cfodive.com/feeds/news/"},
    {"name": "SaaStr Blog", "url": "https://www.saastr.com/feed/"},
]

# Round labels worth capturing
ROUND_LABELS = [
    "series a", "series b", "series c", "series d", "series e",
    "seed round", "pre-seed", "seed funding",
    "growth round", "growth investment", "growth equity",
    "private equity", "pe investment",
    "strategic investment", "minority stake",
]


class FundingFeedScraper(BaseScraper):
    """
    Monitors startup-funding and CFO-press feeds for Series B/C/D+ rounds at
    SaaS/AI companies — the classic "just raised, about to outgrow QuickBooks"
    Campfire trigger.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.source_statuses: list[dict] = []

    def scrape(self) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        self.source_statuses = []

        for feed_cfg in FUNDING_FEEDS:
            feed_events, status = self._scrape_feed(feed_cfg)
            events.extend(feed_events)
            self.source_statuses.append({
                "source_name": feed_cfg["name"],
                "source_type": "funding_feed",
                "status": status,
                "events_found": len(feed_events),
            })
            self._sleep()

        return events

    def _scrape_feed(self, feed_cfg: dict) -> tuple[list[TriggerEvent], str]:
        name = feed_cfg["name"]
        url = feed_cfg["url"]

        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                return [], "error"

            events: list[TriggerEvent] = []
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                summary = self._strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                )
                combined = f"{title} {summary}".lower()

                # Must mention a funding round type
                has_round = any(r in combined for r in ROUND_LABELS)
                if not has_round:
                    continue

                # Must be tech-relevant
                if not self._is_tech_relevant(combined):
                    continue

                if self.exclude_public and self._is_public_company(combined):
                    continue

                # Location is tagged (US vs International) in _make_event,
                # not filtered — international leads are kept but scored lower.

                published = self._parse_date(
                    entry.get("published", "") or entry.get("updated", "")
                )
                event = self._make_event(
                    title=title,
                    url=link,
                    description=summary,
                    source_name=name,
                    published_date=published,
                    event_type=EventType.FUNDING,
                )
                if event:
                    event.source = EventSource.FUNDING_FEED
                    events.append(event)

            return events, "success" if events else "partial"

        except Exception as exc:
            print(f"  [FundingFeed] Error fetching '{name}': {exc}")
            return [], "error"
