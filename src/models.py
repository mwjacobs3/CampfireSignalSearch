"""Data models for Campfire buying-signal / trigger events."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(Enum):
    FUNDING            = "funding"              # Series B/C/D+ raise (VC/PE) at a SaaS/AI company
    FINANCE_EXEC_HIRE   = "finance_exec_hire"     # New CFO / VP Finance / Controller hire
    ERP_CHANGE_SIGNAL   = "erp_change_signal"     # Outgrowing QuickBooks/Xero, evaluating/ripping out an ERP
    COMPLIANCE_SIGNAL   = "compliance_signal"     # SOC 2, IPO/S-1, first audit — investor/audit-ready reporting need
    OTHER                = "other"


class EventSource(Enum):
    RSS_FEED      = "rss_feed"
    GOOGLE_NEWS   = "google_news"
    EXEC_HIRE_WIRE = "exec_hire_wire"   # Press-release-based finance exec hire detection
    FUNDING_FEED  = "funding_feed"
    OTHER         = "other"


@dataclass
class TriggerEvent:
    """A single trigger event surfaced as a Campfire sales signal."""

    id: str                        # sha256(url + title)
    title: str
    event_type: EventType
    source: EventSource
    url: str
    published_date: datetime

    discovered_date: datetime = field(default_factory=datetime.utcnow)
    source_name: Optional[str] = None    # Human-readable feed/source name

    # Company intel
    company_name: Optional[str] = None
    company_location: Optional[str] = None
    company_country: Optional[str] = None   # "US" | "International" | None (unknown)
    is_us_company: Optional[bool] = None    # True=US, False=Intl, None=Unknown
    sector: Optional[str] = None       # Campfire ICP slice: ai_ml, horizontal_saas, fintech, etc.

    # Outreach enrichment
    company_website: Optional[str] = None      # apex domain, e.g. "example.com"
    company_linkedin: Optional[str] = None     # linkedin.com/company/<slug>
    founder_linkedin: Optional[str] = None     # linkedin.com/in/<slug>
    hq_city: Optional[str] = None
    hq_state: Optional[str] = None             # 2-letter US state abbreviation

    # Viability signals
    founding_year: Optional[int] = None
    employee_count: Optional[str] = None       # raw string, e.g. "40", "100-person"
    total_funding: Optional[str] = None        # "$65M to date"
    arr: Optional[str] = None                  # "$50M ARR" — parsed from press when disclosed
    legacy_systems: list = field(default_factory=list)   # named ERP/accounting systems mentioned

    # Campfire fit signals
    erp_pain_signal: bool = False              # article mentions close/reconciliation/reporting pain
    tech_stack: list = field(default_factory=list)     # "stripe", "netsuite", "salesforce", etc.
    legacy_erp_mention: bool = False           # NetSuite / Sage Intacct / SAP / Oracle / Dynamics named
    entry_stack_mention: bool = False          # QuickBooks / Xero named (outgrowing entry-level tools)
    integration_match: list = field(default_factory=list)  # finance/RevOps stack products mentioned
    billing_model: Optional[str] = None        # "SUBSCRIPTION" | "USAGE_BASED" | "SUBSCRIPTION_PLUS_USAGE"

    # Article body
    description: Optional[str] = None

    # People
    person_name: Optional[str] = None    # Exec hire specifics
    person_title: Optional[str] = None
    founder_name: Optional[str] = None   # Founder mentioned in the article

    # Funding specifics
    funding_amount: Optional[str] = None
    funding_round: Optional[str] = None   # "Series A", "Series B", etc.

    # Matching metadata
    matched_keywords: list = field(default_factory=list)
    relevance_score: float = 0.0
    query: Optional[str] = None          # Google News query that surfaced it

    # Lead workflow
    lead_status: str = "NEW"
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "title": self.title,
            "company_name": self.company_name or "",
            "company_location": self.company_location or "",
            "company_country": self.company_country or "",
            "is_us_company": self.is_us_company,
            "sector": self.sector or "",
            "company_website": self.company_website or "",
            "company_linkedin": self.company_linkedin or "",
            "founder_linkedin": self.founder_linkedin or "",
            "hq_city": self.hq_city or "",
            "hq_state": self.hq_state or "",
            "founding_year": self.founding_year,
            "employee_count": self.employee_count or "",
            "total_funding": self.total_funding or "",
            "arr": self.arr or "",
            "legacy_systems": ",".join(self.legacy_systems),
            "erp_pain_signal": self.erp_pain_signal,
            "tech_stack": ",".join(self.tech_stack),
            "legacy_erp_mention": self.legacy_erp_mention,
            "entry_stack_mention": self.entry_stack_mention,
            "integration_match": ",".join(self.integration_match),
            "billing_model": self.billing_model or "",
            "description": (self.description or "")[:2000],
            "source_name": self.source_name or "",
            "source_url": self.url,
            "published_date": self.published_date.isoformat(),
            "discovered_at": self.discovered_date.isoformat(),
            "person_name": self.person_name or "",
            "person_title": self.person_title or "",
            "founder_name": self.founder_name or "",
            "funding_amount": self.funding_amount or "",
            "funding_round": self.funding_round or "",
            "matched_keywords": ",".join(self.matched_keywords),
            "relevance_score": round(self.relevance_score, 2),
            "query": self.query or "",
            "lead_status": self.lead_status,
        }
