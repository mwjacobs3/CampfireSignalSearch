"""
Account Watch scraper — targeted signal search scoped to the HubSpot
companies you own, rather than the open-web ICP net the other scrapers cast
(see GoogleNewsScraper). Each owned company gets one combined Google News
query covering all four Campfire trigger-event categories; a result is only
kept if the company's own name actually appears in the article (cuts
name-collision noise, e.g. a generic "CFO" or "audit" story) and at least
one classification keyword hits (a bare name mention isn't a signal).

Unlike the ICP-scan scrapers, this does NOT apply BaseScraper._make_event()'s
broad ICP filters (public-company exclusion, non-tech sector exclusion, size
band, US-territory scoring) — these companies are already known, qualified
CRM accounts, so we want every concrete signal about them rather than a
re-filter of whether they're a plausible ICP-fit stranger.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from datetime import datetime
from typing import Any, Optional

import feedparser

from ..models import EventSource, EventType, TriggerEvent
from .base import BaseScraper

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"

# One combined query per company across all four trigger-event categories —
# keeps this to ~1 HTTP request per owned account instead of 4.
_SIGNAL_TERMS = [
    '"series a"', '"series b"', '"series c"', '"series d"', "funding", "raises", "secures",
    "CFO", '"chief financial officer"', '"VP finance"', "controller",
    '"chief accounting officer"', '"head of finance"',
    "NetSuite", '"Sage Intacct"', "QuickBooks", "Xero", '"general ledger"',
    '"SOC 2"', "IPO", '"S-1"', "audit",
]
_SIGNAL_CLAUSE = " OR ".join(_SIGNAL_TERMS)


class AccountWatchScraper(BaseScraper):
    """Runs one targeted Google News query per HubSpot-owned company."""

    def __init__(self, config: dict[str, Any], companies: list[dict]):
        super().__init__(config)
        self.companies = companies
        self.results_per_company = int(
            config.get("account_watch", {}).get("results_per_company", 5)
        )
        self.source_statuses: list[dict] = []

    def scrape(self) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        seen_urls: set[str] = set()
        errors = 0

        for company in self.companies:
            try:
                for event in self._fetch_for_company(company):
                    if event.url not in seen_urls:
                        seen_urls.add(event.url)
                        events.append(event)
            except Exception as exc:
                errors += 1
                print(f"    [AccountWatch] Error for '{company.get('name')}': {exc}")
            self._sleep()

        self.source_statuses = [{
            "source_name": "HubSpot Account Watch — Google News",
            "source_type": "account_watch",
            "status": "success" if errors == 0 else "partial",
            "events_found": len(events),
            "error_message": f"{errors} companies failed" if errors else None,
        }]
        return events

    def _fetch_for_company(self, company: dict) -> list[TriggerEvent]:
        name = company["name"]
        query = f'"{name}" ({_SIGNAL_CLAUSE})'
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        url = f"{GOOGLE_NEWS_BASE}?{urllib.parse.urlencode(params)}"

        feed = feedparser.parse(url)
        name_lower = name.lower()
        results: list[TriggerEvent] = []

        for entry in feed.entries[: self.results_per_company]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            if not title or not link:
                continue
            summary = self._strip_html(entry.get("summary", "") or "")

            # The company name must actually appear in the article — a bare
            # keyword hit ("CFO", "audit") elsewhere is not a signal.
            if name_lower not in f"{title} {summary}".lower():
                continue

            published = self._parse_date(entry.get("published", ""))
            event = self._make_account_event(
                company=company,
                title=title,
                url=link,
                description=summary,
                published_date=published,
                source_name=entry.get("source", {}).get("title", "Google News"),
                query=query,
            )
            if event:
                results.append(event)

        return results

    def _make_account_event(
        self,
        company: dict,
        title: str,
        url: str,
        description: str,
        published_date: datetime,
        source_name: str,
        query: str,
    ) -> Optional[TriggerEvent]:
        combined = f"{title}\n{description or ''}".lower()

        event_type = self._classify(combined)
        keywords_hit = self._matched_keywords(combined, event_type)
        if event_type == EventType.OTHER and not keywords_hit:
            return None  # name mention with no concrete trigger-event signal

        original = f"{title}\n{description or ''}"

        return TriggerEvent(
            id=self._account_event_id(url, title),
            title=title.strip(),
            event_type=event_type,
            source=EventSource.GOOGLE_NEWS,
            url=url,
            published_date=published_date,
            source_name=source_name,
            company_name=company["name"],
            company_website=company.get("domain") or None,
            description=(description or "")[:2000],
            person_name=self._extract_person(title, event_type),
            person_title=self._extract_person_title(title, event_type),
            founder_name=self._extract_founder(original),
            legacy_systems=self._extract_legacy_systems(combined),
            erp_pain_signal=self._has_erp_pain(combined),
            tech_stack=self._extract_tech_stack(combined),
            legacy_erp_mention=self._has_legacy_erp(combined),
            entry_stack_mention=self._has_entry_stack(combined),
            integration_match=self._extract_integrations(combined),
            billing_model=self._detect_billing_model(combined),
            funding_round=self._extract_funding_round(combined),
            funding_amount=self._extract_funding_amount(combined),
            matched_keywords=keywords_hit,
            relevance_score=min(len(keywords_hit) * 20 + 40, 100),
            query=query,
            pipeline="account_watch",
            hubspot_company_id=str(company["id"]),
            hubspot_company_url=company.get("hubspot_url"),
        )

    @staticmethod
    def _account_event_id(url: str, title: str) -> str:
        # Salted distinctly from BaseScraper._generate_id so the same article
        # surfaced by both the ICP-scan and Account Watch pipelines is stored
        # as two rows (different pipeline tags) instead of one overwriting
        # the other's `pipeline` column on upsert.
        key = f"account_watch|{url}|{title}".lower().strip()
        return hashlib.sha256(key.encode()).hexdigest()
