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
"""

from __future__ import annotations

import re
from typing import Optional

import requests

from .models import TriggerEvent
from .scrapers.base import INTEGRATION_KEYWORDS

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
