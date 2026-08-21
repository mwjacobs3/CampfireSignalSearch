"""
Google News RSS scraper using Campfire ICP-tuned search queries.

Queries are loaded from config.yaml (google_news_queries section) so they
can be tuned without touching code.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Optional

import feedparser

from ..models import EventSource, EventType, TriggerEvent
from .base import BaseScraper

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"


class GoogleNewsScraper(BaseScraper):

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.queries_by_type: dict[str, list[str]] = config.get(
            "google_news_queries", {}
        )
        self.source_statuses: list[dict] = []

    def scrape(self) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        seen_urls: set[str] = set()
        self.source_statuses = []

        type_map = {
            "funding":            EventType.FUNDING,
            "finance_exec_hire":  EventType.FINANCE_EXEC_HIRE,
            "erp_change_signal":  EventType.ERP_CHANGE_SIGNAL,
            "compliance_signal":  EventType.COMPLIANCE_SIGNAL,
        }

        for type_key, queries in self.queries_by_type.items():
            # Unmapped query buckets (stack_footprint, sector-specific launch
            # blocks) auto-classify off the article text instead of getting
            # stuck as OTHER — otherwise their keyword bonus never fires and
            # they fall below the relevance gate.
            event_type = type_map.get(type_key)
            found_this_type = 0

            for query in queries:
                results = self._fetch(query, event_type)
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        events.append(r)
                        found_this_type += 1
                self._sleep()

            self.source_statuses.append({
                "source_name": f"Google News — {type_key.replace('_', ' ').title()}",
                "source_type": "google_news",
                "status": "success",
                "events_found": found_this_type,
            })

        return events

    def _fetch(self, query: str, event_type: Optional[EventType]) -> list[TriggerEvent]:
        params = {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
        url = f"{GOOGLE_NEWS_BASE}?{urllib.parse.urlencode(params)}"
        try:
            feed = feedparser.parse(url)
            results = []
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                summary = self._strip_html(
                    entry.get("summary", "") or ""
                )
                published = self._parse_date(entry.get("published", ""))

                event = self._make_event(
                    title=title,
                    url=link,
                    description=summary,
                    source_name=entry.get("source", {}).get("title", "Google News"),
                    published_date=published,
                    event_type=event_type,
                    query=query,
                )
                if event:
                    event.source = EventSource.GOOGLE_NEWS
                    results.append(event)

            return results
        except Exception as exc:
            print(f"  [GoogleNews] Error for '{query}': {exc}")
            return []
