"""
Finance-exec-hire scraper via BusinessWire and PR Newswire press releases.

Rather than scraping job boards (which block bots), this scraper monitors
the press-release wire services for exec appointment announcements — the
same signal, but from a more reliable source. Filters for the Campfire ICP:
finance leadership hires (CFO, VP Finance, Controller, Chief Accounting
Officer, Head of FP&A) at venture-backed tech companies — the #1 Campfire
buying trigger, since a new finance leader almost always re-evaluates the
accounting stack in their first 90 days.
"""

from __future__ import annotations

from typing import Any

import feedparser

from ..models import EventSource, EventType, TriggerEvent
from .base import BaseScraper


PRESS_RELEASE_FEEDS = [
    {
        "name": "BusinessWire — Technology",
        "url": "https://feed.businesswire.com/rss/home/?rss=G9",
    },
    {
        "name": "BusinessWire — Corporate Changes",
        "url": "https://feed.businesswire.com/rss/home/?rss=G6",
    },
    {
        "name": "PR Newswire — Technology",
        "url": "https://www.prnewswire.com/rss/technology-latest-news.rss",
    },
    {
        "name": "PR Newswire — Financial Services",
        "url": "https://www.prnewswire.com/rss/financial-services-latest-news.rss",
    },
    {
        "name": "GlobeNewswire — Technology",
        "url": "https://www.globenewswire.com/RssFeed/subjectCode/13",
    },
    {
        "name": "EIN Presswire — Technology",
        "url": "https://www.einpresswire.com/rss/technology/",
    },
    {
        "name": "AccessWire",
        "url": "https://www.accesswire.com/rss/news",
    },
]

# Campfire ICP titles: the finance leader who owns the accounting-stack decision.
EXEC_TITLE_KEYWORDS = [
    "chief financial officer", " cfo ", " cfo,", " cfo.",
    "chief accounting officer", " cao ",
    "vp finance", "vp of finance", "svp finance", "svp of finance",
    "evp finance", "evp of finance",
    "vice president finance", "vice president of finance",
    "senior vice president finance", "senior vice president of finance",
    "head of finance", "head of accounting", "head of fp&a",
    "vp fp&a", "vp of fp&a",
    "director of finance", "director of accounting",
    "controller", "corporate controller", "assistant controller",
]

APPOINTMENT_VERBS = [
    "appoints", "names", "hires", "promotes", "welcomes",
    "announces appointment", "joins as", "appointed as",
]


class ExecHireScraper(BaseScraper):
    """
    Monitors press-release feeds for finance-leadership hires at tech companies.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.source_statuses: list[dict] = []

    def scrape(self) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        self.source_statuses = []

        for feed_cfg in PRESS_RELEASE_FEEDS:
            feed_events, status = self._scrape_feed(feed_cfg)
            events.extend(feed_events)
            self.source_statuses.append({
                "source_name": feed_cfg["name"],
                "source_type": "exec_hire_wire",
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
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                summary = self._strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                )
                combined = f"{title} {summary}".lower()

                # Must mention an appointment verb AND a finance-leader title
                has_verb = any(v in combined for v in APPOINTMENT_VERBS)
                has_title = any(t in combined for t in EXEC_TITLE_KEYWORDS)

                if not has_verb or not has_title:
                    continue

                # Must also be tech-relevant
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
                    event_type=EventType.FINANCE_EXEC_HIRE,
                )
                if event:
                    event.source = EventSource.EXEC_HIRE_WIRE
                    events.append(event)

            return events, "success" if events else "partial"

        except Exception as exc:
            print(f"  [ExecHireScraper] Error fetching '{name}': {exc}")
            return [], "error"
