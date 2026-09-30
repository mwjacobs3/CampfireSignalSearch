"""
Website-stack enrichment for Campfire trigger events.

Press text rarely names a prospect's accounting/ERP stack, but a B2B SaaS
company's own marketing site often leaks adjacent signals: a Stripe Checkout
embed, an Intercom or Drift chat widget, a HubSpot tracking script, a
Vanta/Drata/Secureframe trust-center badge (a SOC 2 program in progress —
a strong compliance_signal proxy), or a Greenhouse/Lever/Ashby careers-board
embed (a hiring/growth proxy). This module fetches the company website
homepage once and fingerprints it for those tells.

Detected products are merged into `event.tech_stack` and re-evaluated for
Campfire-adjacent-stack overlap, which updates `event.integration_match`. The
whole pass is wrapped in try/except — enrichment is strictly best-effort
and never blocks event ingestion.

`enrich_hiring_signal` is a second, independent enrichment pass: it looks for
a public Greenhouse/Lever/Ashby job board (linked from the homepage, or found
by probing a few common /careers paths) and checks it for open accounting/
finance reqs. Those ATS boards are public, unauthenticated JSON APIs meant to
power a company's own careers widget, so — unlike LinkedIn or Indeed — they
don't block bots. A growing finance team is a real-time buying signal in its
own right, independent of anything press coverage discloses.
"""

from __future__ import annotations

import re
from typing import Optional

import requests

from .models import TriggerEvent
from .scrapers.base import FINANCE_ROLE_TITLE_KEYWORDS, INTEGRATION_KEYWORDS

# ── Homepage HTML fingerprints ──────────────────────────────────────────────
# Each entry is (regex, canonical-product-key). Keys overlap with
# INTEGRATION_KEYWORDS so the integration_match list stays consistent.
_HOMEPAGE_FINGERPRINTS: list[tuple[re.Pattern, str]] = [
    # Billing / payments
    (re.compile(r"js\.stripe\.com|checkout\.stripe\.com", re.I), "stripe"),
    (re.compile(r"chargebee\.com", re.I), "chargebee"),
    (re.compile(r"zuora\.com", re.I), "zuora"),
    # CRM / RevOps
    (re.compile(r"js\.hs-scripts\.com|hubspot\.com|hs-analytics\.net", re.I), "hubspot"),
    (re.compile(r"salesforce\.com/embeddedservice|force\.com", re.I), "salesforce"),
    # Support / chat widgets (adjacent GTM-maturity signal)
    (re.compile(r"widget\.intercom\.io|intercomcdn\.com", re.I), "intercom"),
    (re.compile(r"js\.driftt\.com|drift\.com", re.I), "drift"),
    # Compliance / trust-center badges — a strong compliance_signal proxy
    (re.compile(r"trust\.vanta\.com|vanta\.com/embed", re.I), "vanta"),
    (re.compile(r"trust\.drata\.com", re.I), "drata"),
    (re.compile(r"trust\.secureframe\.com", re.I), "secureframe"),
    # Careers / hiring embeds — a headcount-growth proxy
    (re.compile(r"boards\.greenhouse\.io", re.I), "greenhouse"),
    (re.compile(r"jobs\.lever\.co", re.I), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com", re.I), "ashby"),
    # Docs / e-sign
    (re.compile(r"docusign\.net|docusign\.com", re.I), "docusign"),
]


def enrich_event(
    event: TriggerEvent,
    timeout: float = 6.0,
    user_agent: str = "Mozilla/5.0 (compatible; CampfireSignalSearch/1.0)",
) -> TriggerEvent:
    """Fetch the prospect's homepage and merge tech-stack fingerprint hits.

    Idempotent and side-effect-free outside `event` mutation. Any failure is
    swallowed — this is a *best-effort* enrichment pass.
    """
    site = event.company_website
    if not site:
        return event

    html = _fetch_homepage(site, timeout=timeout, user_agent=user_agent)
    if not html:
        return event

    new_stack = list(event.tech_stack or [])
    new_integrations = list(event.integration_match or [])

    for rx, key in _HOMEPAGE_FINGERPRINTS:
        if rx.search(html) and key not in new_stack:
            new_stack.append(key)

    # Promote new tech-stack hits into integration_match.
    combined_lc = " ".join(new_stack).lower()
    for needle, label in INTEGRATION_KEYWORDS.items():
        if needle in combined_lc and label not in new_integrations:
            new_integrations.append(label)

    event.tech_stack = new_stack
    event.integration_match = new_integrations
    return event


def _fetch_homepage(
    domain: str, timeout: float, user_agent: str
) -> Optional[str]:
    if not domain:
        return None
    url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.text:
            return resp.text[:200_000]  # cap at ~200KB
    except requests.RequestException:
        return None
    return None


# ── Careers-page / ATS job-board enrichment ──────────────────────────────────
# Greenhouse, Lever, and Ashby all expose a public, unauthenticated JSON API
# meant to power a company's own embeddable careers widget — unlike LinkedIn
# or Indeed, these don't block bots, so we can check a prospect's real open
# reqs without scraping a job board that would 403 us. The catch: we need the
# company's ATS board slug, which we get either from a link already embedded
# on their homepage, or by probing a couple of common /careers paths.
_ATS_BOARD_LINK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"boards\.greenhouse\.io/([a-zA-Z0-9\-]+)", re.I), "greenhouse"),
    (re.compile(r"job-boards\.greenhouse\.io/([a-zA-Z0-9\-]+)", re.I), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([a-zA-Z0-9\-]+)", re.I), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9\-]+)", re.I), "ashby"),
]

_CAREERS_PATHS = ["/careers", "/careers/", "/jobs", "/about/careers", "/company/careers"]


def _find_ats_board(html: str) -> Optional[tuple[str, str]]:
    """Return (provider, slug) for the first Greenhouse/Lever/Ashby board link
    found in HTML, or None."""
    for pattern, provider in _ATS_BOARD_LINK_PATTERNS:
        m = pattern.search(html or "")
        if m:
            return provider, m.group(1)
    return None


def _discover_ats_board(
    website: str, timeout: float, user_agent: str, homepage_html: Optional[str] = None
) -> Optional[tuple[str, str]]:
    """Find a prospect's public ATS board (provider, slug) by checking their
    homepage HTML first, then a few common careers-page paths. Best-effort —
    any fetch failure just means no board is found."""
    html = homepage_html if homepage_html is not None else _fetch_homepage(
        website, timeout=timeout, user_agent=user_agent
    )
    if html:
        board = _find_ats_board(html)
        if board:
            return board

    base = website if website.startswith(("http://", "https://")) else f"https://{website}"
    for path in _CAREERS_PATHS:
        try:
            resp = requests.get(
                base.rstrip("/") + path,
                timeout=timeout,
                headers={"User-Agent": user_agent},
                allow_redirects=True,
            )
            if resp.status_code == 200 and resp.text:
                board = _find_ats_board(resp.text[:200_000])
                if board:
                    return board
        except requests.RequestException:
            continue
    return None


def _fetch_ats_job_titles(
    provider: str, slug: str, timeout: float, user_agent: str
) -> list[str]:
    """Query the provider's public job-board JSON API and return raw job titles."""
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    try:
        if provider == "greenhouse":
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                timeout=timeout, headers=headers,
            )
            if resp.status_code != 200:
                return []
            return [j.get("title", "") for j in resp.json().get("jobs", [])]

        if provider == "lever":
            resp = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                timeout=timeout, headers=headers,
            )
            if resp.status_code != 200:
                return []
            return [p.get("text", "") for p in resp.json()]

        if provider == "ashby":
            resp = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                timeout=timeout, headers=headers,
            )
            if resp.status_code != 200:
                return []
            return [j.get("title", "") for j in resp.json().get("jobs", [])]
    except (requests.RequestException, ValueError):
        return []
    return []


_ATS_BOARD_URL = {
    "greenhouse": "https://boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
}


def enrich_hiring_signal(
    event: TriggerEvent,
    timeout: float = 6.0,
    user_agent: str = "Mozilla/5.0 (compatible; CampfireSignalSearch/1.0)",
    homepage_html: Optional[str] = None,
) -> TriggerEvent:
    """Check a prospect's public Greenhouse/Lever/Ashby job board for open
    accounting/finance reqs (Staff Accountant, AP/AR, Payroll, FP&A, Controller,
    ...) — real, current hiring signal, not press-derived. A growing finance
    team is a buying trigger in its own right, even before a CFO is named.

    Best-effort and side-effect-free outside `event` mutation: any network
    failure or missing board just leaves the event's hiring fields at their
    defaults.
    """
    site = event.company_website
    if not site:
        return event

    board = _discover_ats_board(site, timeout=timeout, user_agent=user_agent, homepage_html=homepage_html)
    if not board:
        return event

    provider, slug = board
    titles = _fetch_ats_job_titles(provider, slug, timeout=timeout, user_agent=user_agent)
    if not titles:
        return event

    matched: list[str] = []
    for title in titles:
        title_lc = (title or "").lower()
        if any(kw in title_lc for kw in FINANCE_ROLE_TITLE_KEYWORDS) and title not in matched:
            matched.append(title.strip())
        if len(matched) >= 10:
            break

    event.careers_page_url = _ATS_BOARD_URL[provider].format(slug=slug)
    if matched:
        event.hiring_finance_roles = True
        event.open_finance_roles = matched
        # A currently-growing finance/accounting team is a strong, real-time
        # buying signal — on par with the other Campfire-fit bonuses.
        event.relevance_score = min((event.relevance_score or 0) + 12, 100)

    return event
