"""Base scraper with Campfire ICP filtering — venture-backed SaaS/AI companies
roughly $20M-$300M ARR that have outgrown QuickBooks/Xero or resent NetSuite,
Sage Intacct, or SAP."""

from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import requests

from ..models import EventType, TriggerEvent


# ── Company-size & public-company exclusions ─────────────────────────────────
# Campfire targets private, venture-backed companies roughly $20M-$300M ARR.
# Exclude Fortune 500 / already-public mega-caps.
PUBLIC_COMPANY_INDICATORS = [
    "nasdaq:", "(nasdaq", "nyse:", "(nyse", "otcbb:", "(otcbb",
    "otc markets", "(otcqx", "(otcqb", "amex:", "(amex",
    "s&p 500", "fortune 500", "fortune 100", "fortune 1000",
    "russell 2000", "russell 1000", "dow jones industrial",
    "publicly traded", "publicly-traded", "publicly held",
    "market capitalization of", "market cap of $",
    "q1 earnings", "q2 earnings", "q3 earnings", "q4 earnings",
    "quarterly earnings", "annual report",
    "10-k filing", "10-q filing", "8-k filing",
    "sec filing", "proxy statement", "investor relations",
    "shareholder meeting", "dividend declaration",
]

# Ticker patterns: (NYSE: ABC), (NASDAQ: XYZ), NYSE:ABC, etc.
PUBLIC_TICKER_REGEX = re.compile(
    r"\((?:nyse|nasdaq|otcbb|otcqx|otcqb|amex|lse|tsx|asx)\s*[:.]\s*[a-z0-9.\-]{1,6}\)"
    r"|\b(?:nyse|nasdaq|otcbb|amex|lse|tsx|asx)\s*:\s*[a-z0-9.\-]{1,6}\b",
    re.IGNORECASE,
)

# Already-public enterprise tech giants — if mentioned, the article is either
# about them or their earnings, not a Campfire prospect. Uses precise, formal
# legal names (not bare product words like "SAP" or "NetSuite") so a prospect
# story that merely NAMES one of these as a stack component — "runs on
# Salesforce", "migrating off Oracle NetSuite" — is never wrongly dropped;
# those product mentions are the positive signals in INTEGRATION_KEYWORDS below.
EXCLUDED_MEGA_TECH = [
    "meta platforms", "alphabet inc", "amazon.com, inc", "apple inc",
    "microsoft corporation", "salesforce.com, inc", "salesforce, inc",
    "workday, inc", "servicenow, inc", "adobe inc", "intuit inc",
    "ibm corporation", "international business machines",
    "automatic data processing", "ceridian hcm holding",
    "sap se", "the sage group plc", "oracle corporation",
    "snowflake inc", "palantir technologies inc", "datadog, inc",
    "hubspot, inc", "zoom video communications", "twilio inc",
    "cloudflare, inc", "mongodb, inc", "docusign, inc", "shopify inc",
    "block, inc", "paypal holdings", "visa inc", "mastercard incorporated",
    "fiserv, inc", "fidelity national information services",
    "s&p global", "moody's corporation",
]

# Legacy alias — preserved so older configs that reference this still load.
EXCLUDED_COMPANIES = EXCLUDED_MEGA_TECH

# Large companies / platforms — filter ONLY when they are the SUBJECT of the
# article. A scaling SaaS company that *mentions* running on Salesforce or
# migrating off NetSuite is exactly the signal we want, so we don't want to
# blanket-exclude these names. ERP_ENTRY_SIGNALS (below) protects the
# "migrating off X" phrasing from being dropped even when X leads the title.
EXCLUDED_MEGA_SUBJECTS = [
    "salesforce", "hubspot", "stripe", "workday", "servicenow",
    "netsuite", "oracle netsuite", "sage intacct", "quickbooks", "xero",
    "sap", "microsoft dynamics", "zendesk", "intercom",
    "ramp", "brex", "rippling", "gusto", "carta", "bill.com",
    "expensify", "deel", "docusign", "ironclad", "chargebee", "zuora",
    "mongodb", "snowflake", "datadog", "twilio", "shopify",
]

# ── Non-tech sector exclusions ───────────────────────────────────────────────
# Campfire sells to venture-backed software/AI companies. The general business
# funding feeds are full of CPG, retail, real estate, biotech, and industrial
# stories that match our funding/hire keywords but are NOT our ICP. An article
# hitting any of these is dropped UNLESS it also carries a concrete tech-sector
# signal (so "AI-powered fintech for restaurants" survives).
NON_TECH_SECTOR_KEYWORDS = [
    # CPG / consumer goods
    "consumer packaged goods", "cpg brand", "food and beverage brand",
    "beverage brand", "snack brand", "beauty brand", "skincare brand",
    "supplement brand", "apparel brand", "dtc brand", "d2c brand",
    "direct-to-consumer brand", "co-manufacturer", "co-packer",
    "third-party logistics", " 3pl ", "retail expansion", "wholesale distributor",
    # Retail / grocery / restaurants
    "grocery chain", "grocery store", "restaurant chain", "restaurant group",
    "quick service restaurant", "casual dining", "fast food chain",
    "convenience store chain", "department store chain",
    # Real estate / construction
    "real estate developer", "real estate development", "homebuilder",
    "commercial real estate", "residential real estate",
    "construction company", "construction firm", "general contractor",
    # Heavy industry / extractive / agriculture
    "oil and gas company", "oil & gas company", "mining company",
    "heavy manufacturing", "industrial manufacturer", "steel producer",
    "farming operation", "agricultural producer", "livestock producer",
    # Hospitality / travel (physical)
    "hotel chain", "hospitality group", "cruise line", "airline carrier",
    # Traditional financial institutions (not fintech software vendors)
    "regional bank", "commercial bank", "insurance carrier",
    "credit union",
    # Bio / pharma / medtech care delivery (distinct from health-tech software)
    "pharmaceutical company", "pharma company", "drug company",
    "drugmaker", "clinical stage biotech", "hospital system",
    "hospital network", "hospital chain", "nursing home operator",
]

# Positive signals that a company is in the right size/stage band
TARGET_SIZE_SIGNALS = [
    "series b", "series c", "series d", "series e", "growth round",
    "growth equity", "unicorn", "high-growth", "hypergrowth",
    "scaling startup", "venture-backed", "vc-backed", "late-stage startup",
]

# Location signals — we FLAG rather than exclude. US companies are the
# priority Campfire ICP, but an international company raising from a US fund
# or expanding into the US is still a valid lead — it gets tagged
# "International" and scored lower.
CANADA_SIGNALS = [
    " canada", "canadian", "toronto", "vancouver", "montreal",
    "calgary", "edmonton", "ottawa", "winnipeg", "quebec",
    "british columbia", "ontario", "alberta",
]

INTERNATIONAL_SIGNALS = [
    "united kingdom", " uk ", " u.k.", "britain", "british", "london",
    "australia", "australian", "sydney", "melbourne",
    "india", "indian", "mumbai", "bangalore", "delhi", "bengaluru",
    "germany", "german", "berlin", "munich",
    "france", "french", "paris",
    "china", "chinese", "shanghai", "beijing",
    "japan", "japanese", "tokyo",
    "mexico", "mexican",
    "brazil", "brazilian",
    "europe", "european union", " eu ",
    "asia-pacific", "apac", "asia pacific",
    "africa", "african",
    "middle east", "uae", "dubai", "saudi arabia", "israel", "israeli",
    "singapore", "hong kong", "south korea", "korean",
    "ireland", "irish", "dublin",
    "netherlands", "dutch", "amsterdam",
    "spain", "spanish", "madrid", "barcelona",
    "italy", "italian", "milan", "rome",
    "sweden", "swedish", "stockholm",
    "new zealand",
]

# Explicit US signals: checked FIRST — a US-based company expanding overseas
# should still be tagged US.
US_SIGNALS = [
    " u.s.", " u.s ", "u.s.-based", "us-based", "usa",
    "united states", " american ", "america",
    "stateside", "domestic market", "san francisco", "silicon valley",
]

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "washington, d.c.",
    "district of columbia",
}

US_CITY_STATE_REGEX = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?,\s*"
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|"
    r"UT|VT|VA|WA|WV|WI|WY|DC)\b"
)

# ── Founder extraction patterns ──────────────────────────────────────────────
_FOUNDER_REGEXES = [
    re.compile(r"[Ff]ounded\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z'’\-]+){1,2})"),
    re.compile(
        r"(?:[Cc]o-)?[Ff]ounder\s*(?:and|&|,)\s*(?:[Cc]o-)?(?:CEO|COO|CTO|CFO|President)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z'’\-]+){1,2})"
    ),
    re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z'’\-]+){1,2}),\s+(?:the\s+)?(?:[Cc]o-)?[Ff]ounder"
    ),
    re.compile(
        r"(?:^|[.\s])(?:[Cc]o-)?[Ff]ounder\s+([A-Z][a-z]+(?:\s+[A-Z][a-z'’\-]+){1,2})"
    ),
]

_FOUNDER_NAME_BLOCKLIST = {
    "Ceo", "Coo", "Cto", "Cfo", "Llc", "Inc", "Corp", "Company",
    "President", "Partners", "Ventures", "Capital", "Holdings",
}

# ── Outreach enrichment ──────────────────────────────────────────────────────
_URL_REGEX = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z0-9\-.]+)")
_NON_COMPANY_DOMAINS = {
    "businesswire.com", "prnewswire.com", "globenewswire.com",
    "einpresswire.com", "accesswire.com", "finsmes.com",
    "techcrunch.com", "crunchbase.com", "news.crunchbase.com",
    "venturebeat.com", "fortune.com", "inc.com", "axios.com",
    "cfodive.com", "accountingtoday.com", "journalofaccountancy.com",
    "saastr.com", "pitchbook.com", "cfo.com", "cfobrew.com",
    "forbes.com", "bloomberg.com", "reuters.com", "wsj.com",
    "google.com", "news.google.com", "yahoo.com",
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "medium.com", "substack.com",
}
_LINKEDIN_COMPANY_REGEX = re.compile(
    r"linkedin\.com/company/([a-zA-Z0-9\-_]+)", re.IGNORECASE
)
_LINKEDIN_PROFILE_REGEX = re.compile(
    r"linkedin\.com/in/([a-zA-Z0-9\-_]+)", re.IGNORECASE
)

_CITY_STATE_CAPTURE_REGEX = re.compile(
    r"\b(?P<city>[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s*"
    r"(?P<state>AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|"
    r"MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|"
    r"TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b"
)

# ── Viability signals ────────────────────────────────────────────────────────
_FOUNDING_YEAR_REGEXES = [
    re.compile(r"[Ff]ounded\s+in\s+((?:19|20)\d{2})"),
    re.compile(
        r"[Ff]ounded\s+by\s+[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,4}"
        r"\s+in\s+((?:19|20)\d{2})"
    ),
]
_EMPLOYEE_COUNT_REGEXES = [
    re.compile(
        r"(?:team\s+of|workforce\s+of|employs|with)\s+"
        r"([\d,]+)\s+(?:employees|people|staff|team\s+members)",
        re.IGNORECASE,
    ),
    re.compile(r"\b([\d,]+)[-\s]+(?:person|employee)\s+(?:team|company|staff)", re.IGNORECASE),
    re.compile(r"\b([\d,]+)\s+employees\b", re.IGNORECASE),
]
_TOTAL_FUNDING_REGEX = re.compile(
    r"(?:raised|secured|bringing\s+total\s+to|total\s+of)\s+"
    r"\$\s*([\d,.]+)\s*(million|billion|M|B)\b"
    r"(?:[^.]{0,40}(?:to\s+date|in\s+total|total\s+raised|overall|across|cumulative))",
    re.IGNORECASE,
)
# ARR is a much more direct proxy for Campfire's $20M-$300M ICP band than
# total funding raised, and tech press discloses it far more often than CPG
# press discloses revenue.
_ARR_REGEXES = [
    re.compile(
        r"\$\s*([\d,.]+)\s*(million|billion|M|B)\b[^.]{0,30}?"
        r"(?:in\s+|of\s+)?(?:ARR|annual\s+recurring\s+revenue)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:ARR|annual\s+recurring\s+revenue)\s+(?:of|reaching|surpassing|crossing|hitting|topping)?\s*"
        r"\$\s*([\d,.]+)\s*(million|billion|M|B)\b",
        re.IGNORECASE,
    ),
]

# Named legacy ERP / accounting systems — a rough "current stack" footprint,
# same role DOSS's retail_doors list played for retail footprint.
LEGACY_SYSTEM_KEYWORDS = [
    "netsuite", "sage intacct", "sap business one", "sap s/4hana",
    "sap s4hana", "sap erp", "microsoft dynamics", "dynamics 365",
    "dynamics gp", "dynamics nav", "oracle erp cloud", "oracle fusion",
    "epicor", "acumatica", "infor cloudsuite", "workday financial management",
    "quickbooks online", "quickbooks desktop", "quickbooks", "xero",
]

# ── Campfire fit signals ─────────────────────────────────────────────────────
ERP_PAIN_KEYWORDS = [
    "manual close", "close takes weeks", "days to close the books",
    "month-end close", "closing the books", "spreadsheet hell",
    "spreadsheet nightmare", "drowning in spreadsheets",
    "manual reconciliation", "reconciliation nightmare",
    "revenue recognition headache", "revenue recognition complexity",
    "asc 606 complexity", "outgrew quickbooks", "outgrowing quickbooks",
    "outgrew xero", "outgrowing xero", "couldn't keep up", "can't keep up",
    "audit readiness", "not audit ready", "investor-ready reporting",
    "board-ready financials", "finance team bottleneck",
    "finance operations bottleneck", "erp implementation nightmare",
    "failed erp implementation", "multi-entity consolidation nightmare",
    "consolidation headache", "scaling finance operations",
    "finance stack overhaul", "rip and replace", "system overhaul",
    "closing the books manually", "finance ops couldn't scale",
]

TECH_STACK_KEYWORDS = [
    "netsuite", "sage intacct", "sap", "oracle", "quickbooks", "xero",
    "microsoft dynamics", "acumatica", "epicor", "workday",
    "stripe", "chargebee", "zuora", "recurly", "salesforce", "hubspot",
    "ramp", "brex", "rippling", "gusto", "deel", "carta", "bill.com",
    "expensify", "ironclad", "docusign", "snowflake", "vanta", "drata",
]

# Named legacy/full ERP systems — the exact prospects Campfire is built to
# replace, so (unlike a lightweight point solution) this is a STRONG POSITIVE
# signal for Campfire, the mirror image of how a CPG-focused tool would treat
# "already on a full ERP" as a disqualifier.
LEGACY_ERP_SYSTEMS = [
    "netsuite", "oracle netsuite", "on netsuite", "using netsuite",
    "netsuite implementation", "sage intacct", "intacct erp",
    "sap erp", "sap business one", "sap s/4hana", "sap s4hana",
    "microsoft dynamics erp", "dynamics 365", "dynamics gp", "dynamics nav",
    "epicor erp", "epicor kinetic", "acumatica erp",
    "infor erp", "infor cloudsuite", "workday financial management",
    "oracle erp cloud", "oracle fusion",
]

# Entry-level accounting tools — the "outgrown" side of the Campfire pitch.
ENTRY_STACK_SYSTEMS = [
    "quickbooks online", "quickbooks desktop", "quickbooks", "xero",
]

# ── Disqualifier: already on a modern Campfire competitor ──────────────────
# If a company just adopted one of these, they've already solved the problem
# (likely with a competitor) — a weak lead right now.
MODERN_COMPETITOR_SYSTEMS = [
    "rillet", "puzzle finance", "puzzle.io", "mosaic.tech",
    "runway financial", "zeni.ai", "airbase", "vic.ai", "numeric.io",
    "ledge.co", "digits accounting",
]

# ── Open finance/accounting job titles (careers-page / ATS enrichment) ──────
# Matched against real job-posting titles pulled from a prospect's public
# Greenhouse/Lever/Ashby job board (see enrichment.py). Broader than the
# exec-hire title list — an open req for a Staff Accountant or AP Specialist
# is a headcount-growth signal in its own right, not just the CFO seat.
FINANCE_ROLE_TITLE_KEYWORDS = [
    "chief financial officer", "cfo", "chief accounting officer",
    "vp finance", "vp of finance", "vice president of finance",
    "vice president, finance", "svp finance", "evp finance",
    "head of finance", "head of accounting", "head of fp&a",
    "director of finance", "director of accounting",
    "finance director", "finance manager",
    "controller", "corporate controller", "assistant controller",
    "accounting manager", "accounting supervisor",
    "staff accountant", "senior accountant", "revenue accountant",
    "technical accounting", "tax accountant", "tax manager",
    "accounts payable", "accounts receivable", "ap specialist", "ar specialist",
    "payroll specialist", "payroll manager", "payroll coordinator",
    "fp&a", "financial planning and analysis", "financial analyst",
    "treasury analyst", "treasury manager", "billing specialist",
    "billing manager", "bookkeeper",
]

# ── Billing-model detection ──────────────────────────────────────────────────
# Billing complexity (subscription, usage-based, or both) is core to
# Campfire's revenue-automation wedge — the equivalent of "channel mix" for a
# CPG-focused tool.
SUBSCRIPTION_KEYWORDS = [
    "subscription revenue", "recurring revenue", "saas subscription",
    "subscription-based", "subscription model", "arr growth",
    "annual recurring revenue",
]
USAGE_BASED_KEYWORDS = [
    "usage-based billing", "usage-based pricing", "consumption-based",
    "pay-as-you-go pricing", "metered billing", "usage-based revenue",
    "consumption-based pricing",
]

# ── Campfire-adjacent integration / stack partners ───────────────────────────
# A prospect whose press already names one of these has a concrete, visible
# finance/RevOps/GTM stack — useful for outreach regardless of whether the
# term is a "we're replacing this" signal (NetSuite, QuickBooks) or a "we
# already run on this" signal (Stripe, Salesforce, Ramp).
INTEGRATION_KEYWORDS = {
    # Legacy / entry ERP & accounting
    "netsuite":            "NetSuite",
    "sage intacct":         "Sage Intacct",
    "sap business one":    "SAP Business One",
    "sap s/4hana":         "SAP S/4HANA",
    "microsoft dynamics":  "Microsoft Dynamics",
    "dynamics 365":        "Dynamics 365",
    "quickbooks online":   "QuickBooks Online",
    "quickbooks":          "QuickBooks",
    "xero":                "Xero",
    "acumatica":           "Acumatica",
    "epicor":              "Epicor",
    "workday financial management": "Workday Financials",
    # Billing / subscription management
    "stripe billing":      "Stripe Billing",
    "stripe":              "Stripe",
    "chargebee":           "Chargebee",
    "zuora":               "Zuora",
    "recurly":             "Recurly",
    "maxio":               "Maxio",
    "saasoptics":          "SaaSOptics",
    "bill.com":            "Bill.com",
    "billtrust":           "Billtrust",
    # CRM / RevOps
    "salesforce":          "Salesforce",
    "hubspot":             "HubSpot",
    "gong":                "Gong",
    "clari":               "Clari",
    # Spend / expense / payroll
    "ramp":                "Ramp",
    "brex":                "Brex",
    "expensify":           "Expensify",
    "gusto":               "Gusto",
    "rippling":            "Rippling",
    "deel":                "Deel",
    "navan":               "Navan",
    "airbase":             "Airbase",
    # Cap table / legal
    "carta":               "Carta",
    "ironclad":            "Ironclad",
    "docusign":            "DocuSign",
    # Data / BI
    "snowflake":           "Snowflake",
    "looker":              "Looker",
    "tableau":             "Tableau",
    # Compliance / trust
    "vanta":               "Vanta",
    "drata":               "Drata",
    "secureframe":         "Secureframe",
}

# ── ERP "entry" phrasing ─────────────────────────────────────────────────────
# Signals that an article is about a company MOVING AWAY FROM a legacy/entry
# system rather than being a story about that system's own vendor — the
# mirror of DOSS's RETAIL_ENTRY_SIGNALS.
ERP_ENTRY_SIGNALS = [
    "migrates off", "migrating off", "migrates from", "migrating from",
    "switches from", "switching from", "replaces", "replacing",
    "rips out", "ripping out", "ditches", "ditching",
    "outgrew", "outgrowing", "graduated from",
    "moves off", "moving off", "moved off", "drops", "dropping",
    "implements", "implementing", "selects", "selected",
    "adopts", "adopting", "deploys", "deploying", "rolls out",
    "partners with", "partnership with", "announces integration with",
    "goes live on", "rip and replace",
]

# ── Disqualifying sectors (ICP doc) ──────────────────────────────────────────
DISQUALIFYING_SECTOR_SIGNALS = [
    # Government / public sector
    "government contract", "federal agency", "department of defense",
    "government procurement", "public sector", "municipal", "city government",
    "state government", "government agency",
    # Care delivery / drug development (distinct from health-tech software)
    "hospital system", "health system", "hospital network", "hospital chain",
    "pharmaceutical company", "pharma company", "drug company",
    "clinical stage", "fda approval", "fda clearance",
    "prescription drug", "rx drug", "medical center", "nursing home operator",
    # Real estate
    "real estate developer", "real estate company", "property developer",
    "reit ", "real estate investment trust", "commercial real estate",
    "residential real estate", "homebuilder",
    # Restaurants / foodservice
    "restaurant chain", "restaurant group", "restaurant franchise",
    "fast food chain", "casual dining", "quick service restaurant",
    # Traditional financial institutions (not fintech software vendors)
    "regional bank", "commercial bank", "insurance carrier", "credit union",
    # VC / PE firms (the investors, not the portfolio companies)
    "venture capital firm", "venture capital fund", "vc firm",
    "private equity firm", "private equity fund", "pe firm",
    "investment firm raises", "fund closes", "fund raises",
    # Staffing (not HR software)
    "staffing agency", "recruiting agency",
]

# ── Weak-fit signal ──────────────────────────────────────────────────────────
# Campfire's GTM and pricing target venture-backed companies with board
# reporting and audit obligations — a bootstrapped, self-funded company is a
# weaker (not disqualifying) fit.
WEAK_FIT_SIGNALS = [
    "bootstrapped and profitable", "no outside investors", "self-funded",
    "never raised venture capital", "family-owned business",
]

# ── Sector classification (Campfire ICP slices) ─────────────────────────────
SECTOR_LABELS = {
    "ai_ml":               "AI / Machine Learning",
    "horizontal_saas":     "Horizontal / B2B SaaS",
    "vertical_saas":       "Vertical SaaS",
    "fintech":             "Fintech",
    "devtools_infra":      "Developer Tools & Infrastructure",
    "cybersecurity":       "Cybersecurity",
    "martech_adtech":      "Martech / Adtech",
    "healthtech_software": "Health-Tech Software",
    "hr_people_software":  "HR / People Software",
    "ecommerce_software":  "E-Commerce & Retail Software",
    "other_tech":          "Technology (Other)",
}

SECTOR_KEYWORDS = {
    "ai_ml": [
        "artificial intelligence", "ai-native", "ai-powered", "ai model",
        "generative ai", "genai", "machine learning", "deep learning",
        "large language model", " llm ", " llms ", "foundation model",
        "ai agent", "ai copilot", "ai assistant startup",
    ],
    "horizontal_saas": [
        "b2b saas", "enterprise software", "enterprise saas",
        "software-as-a-service", "saas platform", "saas company",
        "workflow automation", "productivity software", "collaboration software",
    ],
    "vertical_saas": [
        "vertical saas", "industry-specific software", "practice management software",
        "restaurant software" , "construction software", "logistics software platform",
        "legal tech", "legaltech", "proptech", "insurtech", "edtech",
        "agtech software", "govtech",
    ],
    "fintech": [
        "fintech", "neobank", "payments platform", "embedded finance",
        "banking-as-a-service", "regtech", "digital banking startup",
        "payments infrastructure", "lending platform",
    ],
    "devtools_infra": [
        "developer platform", "developer tool", "api platform", "devops",
        "cloud infrastructure", "data infrastructure", "observability platform",
        "developer tooling", "infrastructure startup", "no-code platform",
        "low-code platform",
    ],
    "cybersecurity": [
        "cybersecurity", "cyber security", "security platform startup",
        "threat detection", "identity security", "endpoint security",
    ],
    "martech_adtech": [
        "martech", "adtech", "marketing automation platform",
        "advertising technology", "customer data platform",
    ],
    "healthtech_software": [
        "healthtech", "health-tech", "digital health platform",
        "telehealth platform", "clinical software", "health software startup",
    ],
    "hr_people_software": [
        "hr software", "hr tech", "hrtech", "people analytics platform",
        "workforce management software", "payroll software startup",
    ],
    "ecommerce_software": [
        "e-commerce platform", "ecommerce software", "retail software platform",
        "commerce infrastructure",
    ],
}

RSS_CATEGORY_TO_SECTOR = {
    "ai / machine learning":       "ai_ml",
    "saas / enterprise software":  "horizontal_saas",
    "fintech":                     "fintech",
    "developer tools":             "devtools_infra",
    "cybersecurity":               "cybersecurity",
    "finance & accounting press":  "other_tech",
    "startup / vc news":           "other_tech",
}


class BaseScraper(ABC):

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.get("scraper", {}).get(
                "user_agent",
                "Mozilla/5.0 (compatible; CampfireSignalSearch/1.0)",
            )
        })
        self.timeout = config.get("scraper", {}).get("timeout", 30)
        self.request_delay = config.get("scraper", {}).get("request_delay", 1.5)

        keywords = config.get("keywords", {})
        self.kw_funding      = [k.lower() for k in keywords.get("funding", [])]
        self.kw_finance_hire = [k.lower() for k in keywords.get("finance_exec_hire", [])]
        self.kw_erp_change   = [k.lower() for k in keywords.get("erp_change_signal", [])]
        self.kw_compliance   = [k.lower() for k in keywords.get("compliance_signal", [])]
        self.kw_finance_team_hiring = [k.lower() for k in keywords.get("finance_team_hiring", [])]

        filters = config.get("territory", {}).get("company_filters", {})
        self.exclude_public = filters.get("exclude_public_companies", True)
        extra_mega_tech = [c.lower() for c in filters.get("excluded_public_companies", [])]
        extra_subjects = [c.lower() for c in filters.get("excluded_mega_subjects", [])]
        self._excluded_mega_tech = EXCLUDED_MEGA_TECH + extra_mega_tech
        self._excluded_subjects = EXCLUDED_MEGA_SUBJECTS + extra_subjects

        # ICP size band — Campfire targets ~$20M-$300M ARR. Press rarely
        # discloses ARR directly (though tech press does more than CPG press
        # discloses revenue), so total funding raised and employee count are
        # the fallback proxies.
        size_band = filters.get("size_band", {})
        self.arr_min_usd     = float(size_band.get("arr_min_usd", 20_000_000))
        self.arr_max_usd     = float(size_band.get("arr_max_usd", 300_000_000))
        self.funding_min_usd = float(size_band.get("funding_min_usd", 20_000_000))
        self.funding_max_usd = float(size_band.get("funding_max_usd", 500_000_000))
        self.employee_min    = int(size_band.get("employee_min", 50))
        self.employee_max    = int(size_band.get("employee_max", 1_500))
        self.employee_hard_max = int(size_band.get("employee_hard_max", 3_000))

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def scrape(self) -> list[TriggerEvent]:
        pass

    # ── Event construction helpers ────────────────────────────────────────────

    def _make_event(
        self,
        title: str,
        url: str,
        description: str,
        source_name: str,
        published_date: datetime,
        event_type: Optional[EventType] = None,
        query: Optional[str] = None,
        sector_hint: Optional[str] = None,
    ) -> Optional[TriggerEvent]:
        """
        Build and validate a TriggerEvent. Returns None if the event fails
        ICP filters (already-public mega-cap, non-tech sector). Location is
        TAGGED (US vs International) rather than filtered — international
        companies are kept but scored lower so the US pipeline stays on top.
        """
        original   = f"{title}\n{description or ''}"
        combined   = original.lower()
        company    = self._extract_company(title)

        if self.exclude_public and self._is_public_company(combined):
            return None

        # Large platforms are only disqualifying when they're the SUBJECT of
        # the article. A scaling SaaS company migrating off NetSuite or onto
        # Salesforce is a valid signal.
        if self._is_excluded_subject(title, company, combined):
            return None

        if event_type is None:
            event_type = self._classify(combined)

        keywords_hit = self._matched_keywords(combined, event_type)

        has_tech_sector = (
            self._has_tech_sector_signal(combined)
            or bool(self._hint_to_sector(sector_hint))
        )

        # Reject clearly non-tech sectors (CPG, retail, real estate,
        # restaurants, biotech, ...) unless the article ALSO has a concrete
        # tech-sector signal ("AI-powered fintech for restaurants").
        if self._is_non_tech_sector(combined) and not has_tech_sector:
            return None

        # Require a POSITIVE tech signal. An event-type keyword alone
        # ("raises", "Series B", "hires CFO") is not enough — every industry's
        # funding/hire news matches those.
        if not (has_tech_sector or self._is_tech_relevant(combined)):
            return None

        is_us, country     = self._detect_country(original, combined)
        sector              = self._classify_sector(combined, sector_hint)
        founder            = self._extract_founder(original)

        # Outreach enrichment
        website            = self._extract_website(original, url)
        company_linkedin   = self._extract_linkedin_company(original)
        founder_linkedin   = self._extract_linkedin_profile(original)
        hq_city, hq_state  = self._extract_city_state(original)

        # Viability signals
        founding_year      = self._extract_founding_year(original)
        employee_count     = self._extract_employee_count(original)
        total_funding      = self._extract_total_funding(original)
        arr                = self._extract_arr(original)
        legacy_systems     = self._extract_legacy_systems(combined)

        # Campfire fit signals
        erp_pain           = self._has_erp_pain(combined)
        tech_stack         = self._extract_tech_stack(combined)
        legacy_erp         = self._has_legacy_erp(combined)
        entry_stack        = self._has_entry_stack(combined)
        integration_match  = self._extract_integrations(combined)
        billing_model       = self._detect_billing_model(combined)

        # ICP disqualifier signals
        has_modern_competitor = self._has_modern_competitor(combined)
        has_disq_sector        = self._has_disqualifying_sector(combined)
        has_weak_fit            = self._has_weak_fit(combined)

        score = self._relevance_score(
            combined, event_type, keywords_hit, is_us,
            erp_pain=erp_pain, legacy_erp=legacy_erp,
            entry_stack=entry_stack,
            integration_count=len(integration_match),
            legacy_system_count=len(legacy_systems),
            billing_model=billing_model,
            total_funding=total_funding,
            arr=arr,
            employee_count=employee_count,
            has_modern_competitor=has_modern_competitor,
            has_disq_sector=has_disq_sector,
            has_weak_fit=has_weak_fit,
        )

        from ..models import EventSource
        source_enum = EventSource.OTHER

        return TriggerEvent(
            id=self._generate_id(url, title),
            title=title.strip(),
            event_type=event_type,
            source=source_enum,
            url=url,
            published_date=published_date,
            source_name=source_name,
            company_name=company,
            company_country=country,
            is_us_company=is_us,
            description=description[:2000] if description else "",
            sector=sector,
            company_website=website,
            company_linkedin=company_linkedin,
            founder_linkedin=founder_linkedin,
            hq_city=hq_city,
            hq_state=hq_state,
            founding_year=founding_year,
            employee_count=employee_count,
            total_funding=total_funding,
            arr=arr,
            legacy_systems=legacy_systems,
            erp_pain_signal=erp_pain,
            tech_stack=tech_stack,
            legacy_erp_mention=legacy_erp,
            entry_stack_mention=entry_stack,
            integration_match=integration_match,
            billing_model=billing_model,
            person_name=self._extract_person(title, event_type),
            person_title=self._extract_person_title(title, event_type),
            founder_name=founder,
            funding_round=self._extract_funding_round(combined),
            funding_amount=self._extract_funding_amount(combined),
            matched_keywords=keywords_hit,
            relevance_score=score,
            query=query,
        )

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _is_public_company(self, text: str) -> bool:
        """True if the article is clearly about an already-public company."""
        if PUBLIC_TICKER_REGEX.search(text):
            return True
        for indicator in PUBLIC_COMPANY_INDICATORS:
            if indicator in text:
                return True
        padded = f" {text} "
        for company in self._excluded_mega_tech:
            if company in padded:
                return True
        return False

    def _is_excluded_subject(
        self, title: str, company: str, text: str
    ) -> bool:
        """
        True if the leading subject of the article is a large platform whose
        OWN news isn't a Campfire signal. Preserves articles where a scaling
        company mentions migrating off/onto one of these (the signal we want).
        """
        title_lower = (title or "").lower()
        company_lower = (company or "").lower().strip()

        has_entry_signal = any(sig in text for sig in ERP_ENTRY_SIGNALS)
        if has_entry_signal:
            return False

        for subject in self._excluded_subjects:
            if company_lower and subject in company_lower:
                return True
            leading = title_lower[:60]
            if subject in leading:
                return True
        return False

    def _is_excluded_location(self, text: str) -> bool:
        """Preserved for backwards compatibility — always returns False now.
        Location is tagged via `_detect_country`, not filtered."""
        return False

    def _detect_country(
        self, original_text: str, lower_text: str
    ) -> tuple[Optional[bool], Optional[str]]:
        """
        Classify a signal as US / International / Unknown. US signals take
        priority — a US-based company expanding to Europe should still be
        tagged US. Canada is treated as in-ICP territory (same tier as US).
        """
        padded = f" {lower_text} "

        for sig in US_SIGNALS:
            if sig in padded:
                return True, "US"

        for state in US_STATES:
            if f" {state} " in padded or f" {state}," in padded:
                return True, "US"

        if US_CITY_STATE_REGEX.search(original_text):
            return True, "US"

        for sig in CANADA_SIGNALS:
            if sig in padded:
                return True, "Canada"

        for sig in INTERNATIONAL_SIGNALS:
            if sig in padded:
                return False, "International"

        return None, None

    def _classify_sector(
        self, text: str, hint: Optional[str] = None
    ) -> str:
        """Return a sector key (e.g. 'ai_ml'). Falls back to a source-provided
        hint (RSS feed category) and finally 'other_tech'."""
        scores = {
            key: sum(1 for kw in kws if kw in text)
            for key, kws in SECTOR_KEYWORDS.items()
        }
        best_key = max(scores, key=lambda k: scores[k])
        if scores[best_key] > 0:
            return best_key
        mapped = self._hint_to_sector(hint)
        if mapped:
            return mapped
        return "other_tech"

    @staticmethod
    def _hint_to_sector(hint: Optional[str]) -> Optional[str]:
        """Map an RSS feed category hint to a sector key, or None."""
        if not hint:
            return None
        return RSS_CATEGORY_TO_SECTOR.get(hint.strip().lower())

    def _has_tech_sector_signal(self, text: str) -> bool:
        """True if the text matches concrete tech-sector vocabulary (AI,
        SaaS, fintech, devtools, ...) — the strong positive signal that an
        article is actually about a software/tech company, as opposed to
        merely matching a generic funding/hire keyword."""
        if not text:
            return False
        return any(
            kw in text
            for kws in SECTOR_KEYWORDS.values()
            for kw in kws
        )

    def _is_non_tech_sector(self, text: str) -> bool:
        """True if the article is clearly about a non-tech sector — CPG,
        retail, real estate, restaurants, biotech care delivery, etc."""
        if not text:
            return False
        padded = f" {text} "
        return any(kw in padded for kw in NON_TECH_SECTOR_KEYWORDS)

    def _is_tech_relevant(self, text: str) -> bool:
        tech_terms = [
            "software", "platform", "startup", "tech company", "technology company",
            "saas", "cloud", "app", "application", "api", "engineering team",
            "product-led", "b2b", "enterprise", "venture capital", "venture-backed",
            "series a", "series b", "series c", "seed round",
            "cfo", "controller", "vp finance", "chief financial officer",
            "finance team", "accounting team", "erp", "general ledger",
            "netsuite", "quickbooks", "xero", "sage intacct", "sap",
        ]
        return any(t in text for t in tech_terms)

    # ── Classification ────────────────────────────────────────────────────────

    def _classify(self, text: str) -> EventType:
        scores = {
            EventType.FINANCE_EXEC_HIRE: sum(1 for k in self.kw_finance_hire if k in text),
            EventType.ERP_CHANGE_SIGNAL: sum(1 for k in self.kw_erp_change   if k in text),
            EventType.FUNDING:           sum(1 for k in self.kw_funding      if k in text),
            EventType.COMPLIANCE_SIGNAL: sum(1 for k in self.kw_compliance   if k in text),
            EventType.FINANCE_TEAM_HIRING_SIGNAL: sum(1 for k in self.kw_finance_team_hiring if k in text),
        }
        best = max(scores, key=lambda e: scores[e])
        return best if scores[best] > 0 else EventType.OTHER

    def _matched_keywords(self, text: str, event_type: EventType) -> list[str]:
        mapping = {
            EventType.FUNDING:           self.kw_funding,
            EventType.FINANCE_EXEC_HIRE: self.kw_finance_hire,
            EventType.ERP_CHANGE_SIGNAL: self.kw_erp_change,
            EventType.COMPLIANCE_SIGNAL: self.kw_compliance,
            EventType.FINANCE_TEAM_HIRING_SIGNAL: self.kw_finance_team_hiring,
        }
        kws = mapping.get(event_type, [])
        return [k for k in kws if k in text]

    # ── Relevance scoring ─────────────────────────────────────────────────────

    def _relevance_score(
        self,
        text: str,
        event_type: EventType,
        keywords_hit: list[str],
        is_us: Optional[bool] = None,
        erp_pain: bool = False,
        legacy_erp: bool = False,
        entry_stack: bool = False,
        integration_count: int = 0,
        legacy_system_count: int = 0,
        billing_model: Optional[str] = None,
        total_funding: Optional[str] = None,
        arr: Optional[str] = None,
        employee_count: Optional[str] = None,
        has_modern_competitor: bool = False,
        has_disq_sector: bool = False,
        has_weak_fit: bool = False,
    ) -> float:
        score = min(len(keywords_hit) * 15, 60)  # up to 60 from keyword hits

        # A concrete tech-sector match (AI/SaaS/fintech/devtools/...) is the
        # clearest sign this is actually our ICP.
        if self._has_tech_sector_signal(text):
            score += 22
        else:
            score -= 12

        # Explicit software/tech framing is a further strong signal.
        if any(t in text for t in (
            "saas", "b2b software", "enterprise software", "ai-native",
            "software company", "software platform", "cloud platform",
        )):
            score += 12

        # Bonus for target-stage signals
        if any(s in text for s in TARGET_SIZE_SIGNALS):
            score += 20

        # ERP-change stories — every named legacy system adds fit signal
        if event_type == EventType.ERP_CHANGE_SIGNAL and legacy_system_count > 0:
            score += min(legacy_system_count * 8, 24)

        # Penalty for very generic / low-signal articles — but don't punish a
        # confirmed tech company just because its phrasing didn't match our
        # trigger-keyword lists (the categorical sector filter already vouched for it).
        if len(keywords_hit) == 0 and not self._has_tech_sector_signal(text):
            score -= 20

        # Territory bias: Campfire sells into US finance teams first.
        if is_us is True:
            score += 15
        elif is_us is False:
            score -= 25

        # Campfire fit: ERP/close pain is the strongest buying signal we can
        # derive from press copy. A named legacy ERP is an even stronger
        # signal — it's the exact system Campfire is built to replace.
        if erp_pain:
            score += 15
        if legacy_erp:
            score += 18
        if entry_stack:
            score += 14
        # An ERP-change story that also names the legacy/entry system being
        # replaced is the Campfire sweet spot.
        if event_type == EventType.ERP_CHANGE_SIGNAL and (legacy_erp or entry_stack):
            score += 15
        if integration_count > 0:
            score += min(integration_count * 5, 15)
        # Billing complexity (subscription / usage-based) is core to
        # Campfire's revenue-automation wedge.
        if billing_model:
            score += 10

        # ── Size-band signals ($20M-$300M ARR) ─────────────────────────────
        # ARR is a much more direct proxy than funding raised — use it first
        # and only fall back to the funding-raised band when ARR isn't disclosed.
        arr_usd = self._parse_money_usd(arr)
        if arr_usd is not None:
            if self.arr_min_usd <= arr_usd <= self.arr_max_usd:
                score += 25
            elif arr_usd > self.arr_max_usd:
                score -= 10
            elif arr_usd > 0:
                score -= 8
        else:
            funding_usd = self._parse_money_usd(total_funding)
            if funding_usd is not None:
                if self.funding_min_usd <= funding_usd <= self.funding_max_usd:
                    score += 15
                elif funding_usd > self.funding_max_usd:
                    score -= 15
                elif funding_usd > 0:
                    score -= 5

        emp_count = self._parse_employee_count(employee_count)
        if emp_count is not None:
            if self.employee_min <= emp_count <= self.employee_max:
                score += 10
            elif emp_count > self.employee_hard_max:
                score -= 20
            elif emp_count > self.employee_max:
                score -= 5

        # ── ICP disqualifier penalties ─────────────────────────────────────
        # Already on a modern Campfire competitor → weaker lead right now.
        if has_modern_competitor:
            score -= 25
        # Disqualifying sector (govt, care delivery, real estate, restaurants, VC/PE, banks).
        if has_disq_sector:
            score -= 35
        # Bootstrapped/self-funded → weaker (not disqualifying) fit.
        if has_weak_fit:
            score -= 15

        return min(max(score, 0), 100)

    @staticmethod
    def _parse_money_usd(money_str: Optional[str]) -> Optional[float]:
        """Convert "$25 Million" / "$1.2 Billion" → float dollars. None if unparseable."""
        if not money_str:
            return None
        m = re.search(
            r"\$?\s*([\d,]+(?:\.\d+)?)\s*(million|billion|m|b)\b",
            money_str,
            re.IGNORECASE,
        )
        if not m:
            return None
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            return None
        unit = m.group(2).lower()
        multiplier = 1_000_000_000 if unit in ("billion", "b") else 1_000_000
        return amount * multiplier

    @staticmethod
    def _parse_employee_count(emp_str: Optional[str]) -> Optional[int]:
        """Best-effort parse of employee_count strings like "40", "100" → int."""
        if not emp_str:
            return None
        digits = re.search(r"(\d[\d,]*)", emp_str)
        if not digits:
            return None
        try:
            return int(digits.group(1).replace(",", ""))
        except ValueError:
            return None

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _extract_company(self, title: str) -> str:
        if not title:
            return ""
        clean = re.sub(r"\s+-\s+[^-]+$", "", title)  # strip " - Source Name"
        clean = re.sub(r"\s+\|\s+[^|]+$", "", clean)  # strip " | Source"
        action_verbs = [
            " raises ", " announces ", " launches ", " unveils ",
            " acquires ", " hires ", " appoints ", " names ", " secures ",
            " closes ", " taps ", " expands ", " partners ", " debuts ",
            " introduces ", " nets ", " welcomes ", " promotes ",
            " invests ", " enters ", " joins ", " signs ", " migrates ",
            " implements ", " selects ", " adopts ", " deploys ",
            " ripping out ", " rips out ", " migrating off ", " migrating from ",
            " switching from ", " switches from ", " replacing ", " replaces ",
            " outgrowing ", " outgrew ", " graduated from ", " moving off ",
            " moves off ", " ditching ", " ditches ", " rolling out ", " rolls out ",
        ]
        lower, cut = clean.lower(), len(clean)
        for v in action_verbs:
            idx = lower.find(v)
            if 0 < idx < cut:
                cut = idx
        company = clean[:cut].strip(" ,;:")
        return company if 2 <= len(company) <= 80 else ""

    def _extract_person(self, title: str, event_type: EventType) -> Optional[str]:
        if event_type != EventType.FINANCE_EXEC_HIRE:
            return None
        m = re.search(
            r"(?:names?|appoints?|hires?|welcomes?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+(?:as|to)",
            title,
        )
        return m.group(1) if m else None

    def _extract_person_title(self, title: str, event_type: EventType) -> Optional[str]:
        if event_type != EventType.FINANCE_EXEC_HIRE:
            return None
        title_keywords = [
            "cfo", "chief financial officer", "vp finance", "vice president finance",
            "vp of finance", "controller", "chief accounting officer",
            "head of finance", "head of accounting", "head of fp&a",
            "vp fp&a", "director of finance", "director of accounting",
            "svp finance", "evp finance",
        ]
        lower = title.lower()
        for kw in title_keywords:
            idx = lower.find(kw)
            if idx >= 0:
                return title[idx : idx + 60].split(",")[0].strip()
        return None

    def _extract_website(self, text: str, article_url: str) -> Optional[str]:
        """Return the first plausible company domain found in the article.

        Skips press-wire / aggregator / social domains (which host the
        article, not the company). Also skips the article URL's own domain.
        """
        article_host = ""
        if article_url:
            m = _URL_REGEX.search(article_url)
            if m:
                article_host = m.group(1).lower()

        for m in _URL_REGEX.finditer(text or ""):
            host = m.group(1).lower().rstrip(".,);:")
            if not host or "." not in host:
                continue
            apex = ".".join(host.split(".")[-2:])
            if apex in _NON_COMPANY_DOMAINS:
                continue
            if host == article_host or apex == article_host:
                continue
            return host
        return None

    def _extract_linkedin_company(self, text: str) -> Optional[str]:
        m = _LINKEDIN_COMPANY_REGEX.search(text or "")
        return f"linkedin.com/company/{m.group(1)}" if m else None

    def _extract_linkedin_profile(self, text: str) -> Optional[str]:
        m = _LINKEDIN_PROFILE_REGEX.search(text or "")
        return f"linkedin.com/in/{m.group(1)}" if m else None

    def _extract_city_state(
        self, text: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (city, 2-letter state) from "City, ST" pattern, or (None, None)."""
        m = _CITY_STATE_CAPTURE_REGEX.search(text or "")
        if not m:
            return None, None
        return m.group("city"), m.group("state")

    def _extract_founding_year(self, text: str) -> Optional[int]:
        if not text:
            return None
        for rx in _FOUNDING_YEAR_REGEXES:
            m = rx.search(text)
            if not m:
                continue
            try:
                year = int(m.group(1))
            except ValueError:
                continue
            if 1970 <= year <= datetime.utcnow().year:
                return year
        return None

    def _extract_employee_count(self, text: str) -> Optional[str]:
        if not text:
            return None
        for rx in _EMPLOYEE_COUNT_REGEXES:
            m = rx.search(text)
            if m:
                return m.group(1).replace(",", "")
        return None

    def _extract_total_funding(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = _TOTAL_FUNDING_REGEX.search(text)
        if not m:
            return None
        unit = m.group(2).capitalize()
        if unit == "M":
            unit = "Million"
        elif unit == "B":
            unit = "Billion"
        return f"${m.group(1)} {unit}"

    def _extract_arr(self, text: str) -> Optional[str]:
        if not text:
            return None
        for rx in _ARR_REGEXES:
            m = rx.search(text)
            if not m:
                continue
            unit = m.group(2).capitalize()
            if unit == "M":
                unit = "Million"
            elif unit == "B":
                unit = "Billion"
            return f"${m.group(1)} {unit} ARR"
        return None

    def _extract_legacy_systems(self, text: str) -> list[str]:
        """Distinct named legacy/entry ERP or accounting systems mentioned."""
        if not text:
            return []
        found = []
        for kw in LEGACY_SYSTEM_KEYWORDS:
            if kw in text and kw not in found:
                found.append(kw)
        return found

    def _has_erp_pain(self, text: str) -> bool:
        return any(kw in text for kw in ERP_PAIN_KEYWORDS) if text else False

    def _extract_tech_stack(self, text: str) -> list[str]:
        if not text:
            return []
        return [kw for kw in TECH_STACK_KEYWORDS if kw in text]

    def _has_legacy_erp(self, text: str) -> bool:
        return any(kw in text for kw in LEGACY_ERP_SYSTEMS) if text else False

    def _has_entry_stack(self, text: str) -> bool:
        return any(kw in text for kw in ENTRY_STACK_SYSTEMS) if text else False

    def _extract_integrations(self, text: str) -> list[str]:
        """Return the list of canonical Campfire-adjacent stack product names found in text."""
        if not text:
            return []
        found: list[str] = []
        for needle, label in INTEGRATION_KEYWORDS.items():
            if needle in text and label not in found:
                found.append(label)
        return found

    def _detect_billing_model(self, text: str) -> Optional[str]:
        if not text:
            return None
        has_sub = any(kw in text for kw in SUBSCRIPTION_KEYWORDS)
        has_usage = any(kw in text for kw in USAGE_BASED_KEYWORDS)
        if has_sub and has_usage:
            return "SUBSCRIPTION_PLUS_USAGE"
        if has_sub:
            return "SUBSCRIPTION"
        if has_usage:
            return "USAGE_BASED"
        return None

    def _has_modern_competitor(self, text: str) -> bool:
        return any(kw in text for kw in MODERN_COMPETITOR_SYSTEMS) if text else False

    def _has_disqualifying_sector(self, text: str) -> bool:
        return any(kw in text for kw in DISQUALIFYING_SECTOR_SIGNALS) if text else False

    def _has_weak_fit(self, text: str) -> bool:
        return any(kw in text for kw in WEAK_FIT_SIGNALS) if text else False

    def _extract_founder(self, text: str) -> Optional[str]:
        """Find a founder name in the article (title + description). Runs for
        all event types — a funding or hire article that mentions the
        founder/CEO gives us a contact point at earlier-stage companies."""
        if not text:
            return None
        for rx in _FOUNDER_REGEXES:
            m = rx.search(text)
            if not m:
                continue
            name = m.group(1).strip()
            first_token = name.split()[0] if name else ""
            if first_token in _FOUNDER_NAME_BLOCKLIST:
                continue
            if 4 <= len(name) <= 60:
                return name
        return None

    def _extract_funding_round(self, text: str) -> Optional[str]:
        for label in ["series e", "series d", "series c", "series b", "series a", "seed round", "pre-seed"]:
            if label in text:
                return label.title()
        return None

    def _extract_funding_amount(self, text: str) -> Optional[str]:
        m = re.search(
            r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|M\b|B\b)",
            text,
            re.IGNORECASE,
        )
        if m:
            return f"${m.group(1)} {m.group(2).capitalize()}"
        return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_id(url: str, title: str) -> str:
        key = f"{url}|{title}".lower().strip()
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        if not date_str:
            return datetime.utcnow()
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                pass
        return datetime.utcnow()

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text or "").strip()

    def _sleep(self) -> None:
        time.sleep(self.request_delay)
