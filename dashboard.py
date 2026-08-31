#!/usr/bin/env python3
"""
Campfire Trigger Events Dashboard

Interactive Streamlit dashboard for managing Campfire trigger event alerts.
Reads from Supabase for online access.

Usage:
    streamlit run dashboard.py
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

try:
    from src.scrapers.base import SECTOR_LABELS
except Exception:
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

st.set_page_config(
    page_title="Campfire Trigger Events",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    /* ── Campfire-aligned palette: ember hero, warm orange accent ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --cf-ink:        #1A1207;  /* near-black hero, warm undertone */
        --cf-ink-2:      #241B0E;  /* card dark text */
        --cf-accent:     #EA580C;  /* ember orange accent */
        --cf-accent-2:   #F59E0B;  /* amber secondary */
        --cf-surface:    #FBF9F6;  /* warm off-white app bg */
        --cf-border:     #E7E2D9;
        --cf-muted:      #6B6355;
        --cf-muted-2:    #9A9284;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        background: var(--cf-surface);
        color: var(--cf-ink-2);
    }

    .main-header {
        background: var(--cf-ink);
        padding: 2.5rem 2.75rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        border: 1px solid #000;
        position: relative;
        overflow: hidden;
    }
    .main-header::after {
        content: "";
        position: absolute; inset: auto -40px -40px auto;
        width: 220px; height: 220px; border-radius: 50%;
        background: radial-gradient(circle, rgba(234,88,12,0.28) 0%, rgba(234,88,12,0) 70%);
        pointer-events: none;
    }
    .main-header h1 {
        color: #FFFFFF; font-size: 2.1rem; font-weight: 800; margin: 0;
        letter-spacing: -0.8px;
    }
    .main-header .eyebrow {
        color: var(--cf-accent-2); font-size: 0.75rem; font-weight: 700;
        letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.5rem;
    }
    .main-header p { color: rgba(255,255,255,0.72); font-size: 0.98rem; margin-top: 0.65rem; max-width: 720px; }

    .metric-card {
        background: #FFFFFF; border-radius: 14px; padding: 1.4rem;
        border: 1px solid var(--cf-border);
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .metric-card:hover { transform: translateY(-1px); border-color: var(--cf-ink); }
    .metric-icon {
        width: 40px; height: 40px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.25rem; margin-bottom: 0.9rem;
    }
    .metric-value { font-size: 1.9rem; font-weight: 700; color: var(--cf-ink); line-height: 1; letter-spacing: -0.5px; }
    .metric-label { font-size: 0.78rem; color: var(--cf-muted); margin-top: 0.5rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }

    .event-card-inner { padding: 0.25rem 0; }
    .event-card-header { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }

    .event-type-badge {
        padding: 0.3rem 0.7rem; border-radius: 6px;
        font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.6px; white-space: nowrap;
    }
    .badge-funding    { background: #FFF3D9; color: #7A4900; }
    .badge-hire       { background: #EBE5FA; color: #4C1D95; }
    .badge-erp        { background: #E0EAFB; color: #1E3A8A; }
    .badge-compliance { background: #E8F5EC; color: #0F5132; }
    .badge-other      { background: #EEEEEA; color: #3F3F3F; }

    .status-badge {
        padding: 0.22rem 0.55rem; border-radius: 6px;
        font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.4px;
    }
    .status-new          { background: var(--cf-ink); color: #FFFFFF; }
    .status-added        { background: #FFE4D6; color: #B0440D; }
    .status-customer     { background: #D6F0E0; color: #0F5132; }
    .status-not-relevant { background: #EEEEEA; color: #6B6B6B; }

    .sector-badge {
        padding: 0.22rem 0.55rem; border-radius: 6px;
        font-size: 0.68rem; font-weight: 600;
        background: #F3F1EC; color: var(--cf-ink-2);
        border: 1px solid var(--cf-border);
    }

    .region-badge {
        padding: 0.22rem 0.55rem; border-radius: 6px;
        font-size: 0.68rem; font-weight: 700;
        letter-spacing: 0.3px;
    }
    .region-us   { background: #DCEAFB; color: #1E3A8A; }
    .region-intl { background: #F3E8FF; color: #6B21A8; }
    .region-unk  { background: #EEEEEA; color: #6B6B6B; }

    .fit-badge {
        padding: 0.22rem 0.55rem; border-radius: 6px;
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.3px;
    }
    .fit-pain    { background: #FFE4D6; color: #B0440D; }    /* ERP/close pain */
    .fit-legacy  { background: #E0EAFB; color: #1E3A8A; }    /* legacy ERP mention */
    .fit-entry   { background: #FEF3C7; color: #854D0E; }    /* QuickBooks/Xero */
    .fit-integration { background: #D1FAE5; color: #065F46; }/* stack match */
    .fit-billing { background: #F3F1EC; color: var(--cf-ink-2); border: 1px solid var(--cf-border); }

    .enrich-panel {
        background: #FBF9F6; border: 1px solid var(--cf-border);
        border-radius: 8px; padding: 0.9rem 1.1rem; margin-top: 0.6rem;
        font-size: 0.82rem; color: var(--cf-ink-2);
    }
    .enrich-panel .row { display: flex; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 0.3rem; }
    .enrich-panel .k   { color: var(--cf-muted); font-weight: 600; margin-right: 0.35rem; }
    .enrich-panel a    { color: var(--cf-accent); text-decoration: none; font-weight: 600; }
    .enrich-panel a:hover { text-decoration: underline; }

    .score-badge {
        padding: 0.22rem 0.55rem; border-radius: 6px;
        font-size: 0.68rem; font-weight: 700;
        font-variant-numeric: tabular-nums;
    }
    .score-hot  { background: var(--cf-accent); color: #FFFFFF; }
    .score-warm { background: #FFE4D6; color: #B0440D; }
    .score-cool { background: #EEEEEA; color: #4A4A4A; }

    .event-title {
        font-size: 1.02rem; font-weight: 600; color: var(--cf-ink);
        margin: 0.65rem 0 0.4rem; line-height: 1.4; letter-spacing: -0.1px;
    }
    .event-company { display: flex; align-items: center; gap: 0.5rem;
                     color: var(--cf-muted); font-size: 0.875rem; }
    .event-meta    { display: flex; gap: 1rem; margin-top: 0.75rem;
                     font-size: 0.78rem; color: var(--cf-muted-2); }

    .search-container {
        background: #FFFFFF; border-radius: 10px; padding: 0.4rem;
        border: 1px solid var(--cf-border);
        margin-bottom: 1.5rem;
    }

    .section-header {
        display: flex; align-items: center; gap: 0.75rem;
        margin: 1.5rem 0 1rem; padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--cf-border);
    }
    .section-header h2 { font-size: 1.2rem; font-weight: 700; color: var(--cf-ink); margin: 0; letter-spacing: -0.3px; }
    .section-count {
        background: var(--cf-ink); padding: 0.2rem 0.65rem; border-radius: 6px;
        font-size: 0.72rem; font-weight: 700; color: #FFFFFF;
    }

    section[data-testid="stSidebar"] {
        background: #FFFFFF; border-right: 1px solid var(--cf-border);
    }
    section[data-testid="stSidebar"] h3 { color: var(--cf-ink); font-weight: 700; }

    .stButton > button {
        border-radius: 8px; font-weight: 600; transition: all 0.15s ease;
        border: 1px solid var(--cf-ink); background: var(--cf-ink); color: #FFFFFF;
    }
    .stButton > button:hover {
        background: var(--cf-accent); border-color: var(--cf-accent);
        color: #FFFFFF; transform: translateY(-1px);
    }

    hr { border: none; height: 1px; background: var(--cf-border); margin: 1.5rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Event type configurations (Campfire-specific) ──────────────────────────
EVENT_TYPES = {
    "funding": {
        "label": "Funding",
        "full_label": "Funding Rounds",
        "color": "#f59e0b",
        "gradient": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        "icon": "💰",
        "badge_class": "badge-funding",
        "bg_color": "#fef3c7",
    },
    "finance_exec_hire": {
        "label": "Finance Hire",
        "full_label": "Finance Leadership Hires",
        "color": "#8b5cf6",
        "gradient": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        "icon": "👤",
        "badge_class": "badge-hire",
        "bg_color": "#ede9fe",
    },
    "erp_change_signal": {
        "label": "ERP Change",
        "full_label": "ERP / Accounting-Stack Change Signals",
        "color": "#3b82f6",
        "gradient": "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",
        "icon": "🔧",
        "badge_class": "badge-erp",
        "bg_color": "#dbeafe",
    },
    "compliance_signal": {
        "label": "Compliance",
        "full_label": "Audit / Compliance Readiness",
        "color": "#10b981",
        "gradient": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        "icon": "📋",
        "badge_class": "badge-compliance",
        "bg_color": "#dcfce7",
    },
    "other": {
        "label": "Other",
        "full_label": "Other Events",
        "color": "#6b7280",
        "gradient": "linear-gradient(135deg, #6b7280 0%, #4b5563 100%)",
        "icon": "📌",
        "badge_class": "badge-other",
        "bg_color": "#f3f4f6",
    },
}

# ── Lead workflow — simplified to 3 actionable outcomes for Campfire sales ──
LEAD_STATUSES = [
    "NEW",
    "ADDED TO LEAD LIST",
    "CAMPFIRE CUSTOMER / PROSPECT",
    "NOT RELEVANT",
]

STATUS_CONFIG = {
    "NEW":                          {"icon": "🆕", "class": "status-new",          "label": "New"},
    "ADDED TO LEAD LIST":           {"icon": "✅", "class": "status-added",        "label": "Added to Lead List"},
    "CAMPFIRE CUSTOMER / PROSPECT": {"icon": "💼", "class": "status-customer",     "label": "Campfire Customer / Prospect"},
    "NOT RELEVANT":                 {"icon": "🚫", "class": "status-not-relevant", "label": "Not Relevant"},
}


# ── User-applied sector tag (sales-controlled, separate from auto `sector`)
USER_SECTOR_OPTIONS = [
    "AI / ML",
    "Horizontal SaaS",
    "Vertical SaaS",
    "Fintech",
    "Dev Tools / Infra",
    "Cybersecurity",
]


@st.cache_resource
def get_supabase_client():
    try:
        from supabase import create_client
    except ImportError:
        st.error("Supabase not installed. Run: pip install supabase")
        return None

    url = (
        st.secrets.get("SUPABASE_URL")
        if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets
        else os.environ.get("SUPABASE_URL")
    )
    key = (
        st.secrets.get("SUPABASE_KEY")
        if hasattr(st, "secrets") and "SUPABASE_KEY" in st.secrets
        else os.environ.get("SUPABASE_KEY")
    )

    if not url or not key:
        return None

    return create_client(url, key)


def _supabase_url() -> str | None:
    """The SUPABASE_URL the dashboard is actually connecting to — used in
    diagnostics so a project/credentials mismatch is obvious."""
    return (
        st.secrets.get("SUPABASE_URL")
        if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets
        else os.environ.get("SUPABASE_URL")
    )


def _events_overview() -> dict:
    """Total event count + latest discovered_at, ignoring any date window.
    Distinguishes 'connected to an empty/stale project' from 'no rows in the
    selected time range'."""
    client = get_supabase_client()
    if not client:
        return {"total": 0, "latest": None}
    try:
        count_resp = (
            client.table("events").select("id", count="exact").limit(1).execute()
        )
        latest_resp = (
            client.table("events")
            .select("discovered_at")
            .order("discovered_at", desc=True)
            .limit(1)
            .execute()
        )
        latest = latest_resp.data[0]["discovered_at"] if latest_resp.data else None
        return {"total": count_resp.count or 0, "latest": latest}
    except Exception:
        return {"total": 0, "latest": None}


@st.cache_data(ttl=300, show_spinner="Loading leads from Supabase…")
def _fetch_events(days: int) -> pd.DataFrame:
    """Fetch raw events from Supabase. Cached for 5 minutes to avoid
    refetching on every filter/selectbox interaction."""
    client = get_supabase_client()
    if not client:
        return pd.DataFrame()

    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        response = (
            client.table("events")
            .select("*")
            .gte("discovered_at", cutoff_date)
            .order("discovered_at", desc=True)
            .limit(2000)
            .execute()
        )
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as exc:
        st.error(f"Error loading events: {exc}")
        return pd.DataFrame()


def load_events(days: int = 30, search: str | None = None) -> pd.DataFrame:
    df = _fetch_events(days).copy()
    if df.empty:
        return df

    if search:
        search_lower = search.lower()
        mask = (
            df["title"].fillna("").str.lower().str.contains(search_lower, na=False)
            | df["company_name"].fillna("").str.lower().str.contains(search_lower, na=False)
            | df["description"].fillna("").str.lower().str.contains(search_lower, na=False)
        )
        df = df[mask]

    df = df.rename(columns={"source_url": "url", "discovered_at": "discovered_date"})
    df["lead_status"] = df["lead_status"].fillna("NEW")
    if "relevance_score" in df.columns:
        df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0)
    else:
        df["relevance_score"] = 0
    return df


def load_source_statuses() -> pd.DataFrame:
    client = get_supabase_client()
    if not client:
        return pd.DataFrame()
    try:
        resp = (
            client.table("source_status")
            .select("*")
            .order("source_type")
            .order("source_name")
            .execute()
        )
        if not resp.data:
            return pd.DataFrame()
        return pd.DataFrame(resp.data)
    except Exception:
        return pd.DataFrame()


def update_lead_status(
    event_id: str,
    status: str,
    notes: str = "",
    user_sector: str | None = None,
) -> bool:
    client = get_supabase_client()
    if not client:
        return False
    try:
        if status == "NOT RELEVANT":
            client.table("events").delete().eq("id", event_id).execute()
        else:
            data: dict = {"lead_status": status}
            if notes is not None:
                data["notes"] = notes
            # Empty string clears the tag; None leaves the column untouched.
            if user_sector is not None:
                data["user_sector"] = user_sector or None
            client.table("events").update(data).eq("id", event_id).execute()
        _fetch_events.clear()  # bust cache so the card disappears on rerun
        return True
    except Exception as exc:
        st.error(f"Error updating status: {exc}")
        return False


def _score_badge(score: float) -> str:
    """Return HTML for a Campfire priority badge. ≥75 = hot, 50-74 = warm, <50 = cool."""
    try:
        s = float(score or 0)
    except (TypeError, ValueError):
        s = 0
    cls = "score-hot" if s >= 75 else "score-warm" if s >= 50 else "score-cool"
    return f'<span class="score-badge {cls}">🎯 {int(s)}</span>'


def render_metric_card(icon: str, value: int, label: str, color: str) -> None:
    bg_gradient = f"linear-gradient(135deg, {color}28 0%, {color}10 100%)"
    html = (
        '<div class="metric-card">'
        f'<div class="metric-icon" style="background: {bg_gradient};">{icon}</div>'
        f'<div class="metric-value">{value:,}</div>'
        f'<div class="metric-label">{label}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _is_null(value) -> bool:
    """True if value is None, NaN, pd.NA, or otherwise missing.

    Belt-and-suspenders wrapper: pd.isna(pd.NA) returns True but
    `pd.NA == ""` / `bool(pd.NA)` raise TypeError, so we can't rely on the
    usual `value is None or value == ""` shortcut.
    """
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def _safe_str(value, default: str = "") -> str:
    """Coerce a row value to a display string, treating None/NaN/pd.NA as default.

    pandas converts SQL NULLs to float('nan') (or pd.NA for nullable dtypes),
    and `NaN or ""` returns NaN (NaN is truthy in Python) — so the usual
    `row.get("x", "") or ""` pattern leaks null into str ops downstream.
    """
    if _is_null(value):
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _safe_bool(value) -> bool:
    """Coerce a row value to a real bool. None / NaN / pd.NA / '' → False."""
    if _is_null(value):
        return False
    if isinstance(value, str):
        return value.lower() in ("true", "t", "1", "yes")
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def _safe_tribool(value):
    """Normalize to strict True / False / None for the 3-state region badge."""
    if _is_null(value):
        return None
    if value is True or value in ("true", "True", "TRUE", 1, "1"):
        return True
    if value is False or value in ("false", "False", "FALSE", 0, "0"):
        return False
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return None


def _link(url: str, label: str) -> str:
    """Render an external-link <a> tag for the enrichment panel."""
    href = url if url.startswith("http") else f"https://{url}"
    return f'<a href="{href}" target="_blank">{label}</a>'


def render_event_card(row, event_config) -> None:
    status = _safe_str(row.get("lead_status"), "NEW") or "NEW"
    title = _safe_str(row.get("title"))[:140]
    company = _safe_str(row.get("company_name")) or "Unknown Company"
    location = _safe_str(row.get("company_location"))
    country = _safe_str(row.get("company_country"))
    is_us = _safe_tribool(row.get("is_us_company"))
    person_name = _safe_str(row.get("person_name"))
    person_title = _safe_str(row.get("person_title"))
    founder_name = _safe_str(row.get("founder_name"))
    funding_round = _safe_str(row.get("funding_round"))
    funding_amount = _safe_str(row.get("funding_amount"))
    sector_key = _safe_str(row.get("sector"))
    user_sector = _safe_str(row.get("user_sector"))
    published = row.get("published_date", "")

    website          = _safe_str(row.get("company_website"))
    company_linkedin = _safe_str(row.get("company_linkedin"))
    founder_linkedin = _safe_str(row.get("founder_linkedin"))
    hq_city          = _safe_str(row.get("hq_city"))
    hq_state         = _safe_str(row.get("hq_state"))
    founding_year_raw = row.get("founding_year", None)
    founding_year: int | None = None
    if not _is_null(founding_year_raw):
        try:
            founding_year = int(founding_year_raw)
        except (TypeError, ValueError):
            founding_year = None
    employee_count   = _safe_str(row.get("employee_count"))
    total_funding    = _safe_str(row.get("total_funding"))
    arr              = _safe_str(row.get("arr"))
    legacy_systems_raw = _safe_str(row.get("legacy_systems"))
    erp_pain         = _safe_bool(row.get("erp_pain_signal"))
    tech_stack_raw   = _safe_str(row.get("tech_stack"))
    legacy_erp       = _safe_bool(row.get("legacy_erp_mention"))
    entry_stack      = _safe_bool(row.get("entry_stack_mention"))
    integration_raw  = _safe_str(row.get("integration_match"))
    billing_model    = _safe_str(row.get("billing_model"))

    date_display = ""
    if published:
        try:
            dt = (
                datetime.fromisoformat(published.replace("Z", "+00:00"))
                if isinstance(published, str)
                else published
            )
            date_display = dt.strftime("%b %d, %Y")
        except Exception:
            date_display = str(published)[:10]

    status_cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["NEW"])
    badge_class = event_config.get("badge_class", "badge-other")
    score_badge_html = _score_badge(row.get("relevance_score", 0))
    sector_label = SECTOR_LABELS.get(sector_key, "") if sector_key else ""
    sector_html = (
        f'<span class="sector-badge">🏷 {sector_label}</span>' if sector_label else ""
    )
    user_sector_html = (
        f'<span class="sector-badge" style="background:#FFE4D6;color:#B0440D;border-color:#FFD0B6;">'
        f'🎯 {user_sector}</span>'
        if user_sector else ""
    )

    # Region badge: 🇺🇸 US vs 🌍 International vs unknown
    if is_us is True:
        region_html = '<span class="region-badge region-us">🇺🇸 US</span>'
    elif is_us is False:
        region_html = f'<span class="region-badge region-intl">🌍 {country or "International"}</span>'
    else:
        region_html = '<span class="region-badge region-unk">🌐 Unknown</span>'

    # Campfire-fit badges
    fit_parts: list[str] = []
    if erp_pain:
        fit_parts.append('<span class="fit-badge fit-pain">🔥 ERP/Close Pain</span>')
    if legacy_erp:
        fit_parts.append('<span class="fit-badge fit-legacy">🗂 Legacy ERP</span>')
    if entry_stack:
        fit_parts.append('<span class="fit-badge fit-entry">📇 QuickBooks/Xero</span>')
    if integration_raw:
        integration_count = len([i for i in integration_raw.split(",") if i.strip()])
        fit_parts.append(
            f'<span class="fit-badge fit-integration">🔌 Stack Match ({integration_count})</span>'
        )
    if billing_model:
        billing_label = {
            "SUBSCRIPTION": "📅 Subscription",
            "USAGE_BASED": "📊 Usage-Based",
            "SUBSCRIPTION_PLUS_USAGE": "🔄 Sub + Usage",
        }.get(billing_model, billing_model)
        fit_parts.append(f'<span class="fit-badge fit-billing">{billing_label}</span>')
    fit_html = "".join(fit_parts)

    # Supplemental lines stack: founder (if present), then hire/funding/location.
    extras: list[str] = []
    if founder_name:
        extras.append(
            f'<div class="event-company"><span>🌱</span><span>Founder: {founder_name}</span></div>'
        )
    if person_name:
        extras.append(
            f'<div class="event-company"><span>👤</span><span>{person_name}'
            f'{" — " + person_title if person_title else ""}</span></div>'
        )
    elif funding_round or funding_amount:
        label = " · ".join(filter(None, [funding_round, funding_amount]))
        extras.append(f'<div class="event-company"><span>💰</span><span>{label}</span></div>')
    elif location:
        extras.append(f'<div class="event-company"><span>📍</span><span>{location}</span></div>')
    extra_html = "".join(extras)

    # Keep this markdown flush left — Streamlit uses CommonMark, which treats
    # content indented 4+ spaces as a code block and prints raw HTML to the UI.
    card_html = (
        '<div class="event-card-inner">'
        '<div class="event-card-header">'
        f'<span class="event-type-badge {badge_class}">{event_config["icon"]} {event_config["label"]}</span>'
        f'<span class="status-badge {status_cfg["class"]}">{status_cfg["label"]}</span>'
        f'{region_html}'
        f'{sector_html}'
        f'{user_sector_html}'
        f'{score_badge_html}'
        f'{fit_html}'
        '</div>'
        f'<div class="event-title">{title}</div>'
        f'<div class="event-company"><span>🏢</span><span>{company}</span></div>'
        f'{extra_html}'
        f'<div class="event-meta"><span>📅 {date_display}</span></div>'
        '</div>'
    )

    with st.container(border=True):
        st.markdown(card_html, unsafe_allow_html=True)

        with st.expander("📝 Details & Actions"):
            col1, col2 = st.columns([2, 1])

            with col1:
                # ── Enrichment panel ──────────────────────────────────────
                enrich_rows: list[str] = []

                hq_line = ""
                if hq_city and hq_state:
                    hq_line = f"{hq_city}, {hq_state}"
                elif hq_city:
                    hq_line = hq_city
                elif hq_state:
                    hq_line = hq_state

                outreach_parts = []
                if website:
                    outreach_parts.append(_link(website, website))
                if company_linkedin:
                    outreach_parts.append(_link(company_linkedin, "Company"))
                if founder_linkedin:
                    outreach_parts.append(_link(founder_linkedin, "Founder"))
                if outreach_parts:
                    enrich_rows.append(
                        '<div class="row"><span class="k">Outreach:</span> '
                        + " · ".join(outreach_parts) + "</div>"
                    )
                if hq_line:
                    enrich_rows.append(
                        f'<div class="row"><span class="k">HQ:</span> {hq_line}</div>'
                    )

                viability_bits = []
                if founding_year:
                    try:
                        viability_bits.append(f"Founded {int(founding_year)}")
                    except (TypeError, ValueError):
                        pass
                if employee_count:
                    viability_bits.append(f"{employee_count} employees")
                if arr:
                    viability_bits.append(arr)
                if total_funding:
                    viability_bits.append(f"{total_funding} raised to date")
                if viability_bits:
                    enrich_rows.append(
                        '<div class="row"><span class="k">Viability:</span> '
                        + " · ".join(viability_bits) + "</div>"
                    )

                if legacy_systems_raw:
                    systems = ", ".join(s.strip().title() for s in legacy_systems_raw.split(",") if s.strip())
                    enrich_rows.append(
                        f'<div class="row"><span class="k">Legacy systems:</span> {systems}</div>'
                    )
                if tech_stack_raw:
                    stack = ", ".join(t.strip().title() for t in tech_stack_raw.split(",") if t.strip())
                    enrich_rows.append(
                        f'<div class="row"><span class="k">Tech stack:</span> {stack}</div>'
                    )
                if integration_raw:
                    integrations = ", ".join(
                        i.strip() for i in integration_raw.split(",") if i.strip()
                    )
                    enrich_rows.append(
                        f'<div class="row"><span class="k">Campfire-adjacent stack:</span> {integrations}</div>'
                    )

                if enrich_rows:
                    st.markdown(
                        '<div class="enrich-panel">' + "".join(enrich_rows) + "</div>",
                        unsafe_allow_html=True,
                    )

                desc = row.get("description", "")
                if desc:
                    st.markdown("**Description**")
                    text = str(desc)
                    st.caption(text[:500] + ("…" if len(text) > 500 else ""))

                url = row.get("url", "")
                if url:
                    st.link_button("🔗 View Source", url, use_container_width=False)

            with col2:
                current_status = status
                new_status = st.selectbox(
                    "Status",
                    LEAD_STATUSES,
                    index=LEAD_STATUSES.index(current_status) if current_status in LEAD_STATUSES else 0,
                    key=f"status_{row['id']}",
                    label_visibility="collapsed",
                )
                sector_choices = ["— Sector tag —"] + USER_SECTOR_OPTIONS
                current_sector = user_sector if user_sector in USER_SECTOR_OPTIONS else ""
                sector_index = (
                    USER_SECTOR_OPTIONS.index(current_sector) + 1
                    if current_sector else 0
                )
                new_user_sector = st.selectbox(
                    "Sector tag",
                    sector_choices,
                    index=sector_index,
                    key=f"user_sector_{row['id']}",
                    label_visibility="collapsed",
                    help="Sales-applied sector bucket — separate from the auto-detected sector.",
                )
                notes = st.text_area(
                    "Notes",
                    value=row.get("notes") or "",
                    key=f"notes_{row['id']}",
                    height=80,
                    placeholder="Add notes…",
                )
                if st.button("💾 Save", key=f"save_{row['id']}", use_container_width=True):
                    sector_to_save = (
                        new_user_sector
                        if new_user_sector in USER_SECTOR_OPTIONS
                        else ""
                    )
                    if update_lead_status(
                        row["id"], new_status, notes,
                        user_sector=sector_to_save,
                    ):
                        if new_status == "NOT RELEVANT":
                            st.success("✓ Event removed!")
                        else:
                            st.success("✓ Saved!")
                        st.rerun()


def render_event_section(df, event_type, event_config) -> None:
    type_df = df[df["event_type"] == event_type]
    # Campfire priority: US first, then hottest signals, recency as tiebreaker.
    if not type_df.empty and "relevance_score" in type_df.columns:
        sort_df = type_df.copy()
        if "is_us_company" in sort_df.columns:
            sort_df["_us_rank"] = sort_df["is_us_company"].apply(
                lambda v: 0 if _safe_tribool(v) is True
                else (2 if _safe_tribool(v) is False else 1)
            )
            type_df = sort_df.sort_values(
                by=["_us_rank", "relevance_score", "discovered_date"],
                ascending=[True, False, False],
            ).drop(columns=["_us_rank"])
        else:
            type_df = sort_df.sort_values(
                by=["relevance_score", "discovered_date"],
                ascending=[False, False],
            )
    full_label = event_config.get("full_label", event_config["label"])

    header_html = (
        '<div class="section-header">'
        f'<span style="font-size: 1.5rem;">{event_config["icon"]}</span>'
        f'<h2>{full_label}</h2>'
        f'<span class="section-count">{len(type_df)}</span>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    if type_df.empty:
        st.info(f"No {full_label.lower()} found matching your filters.")
        return

    for _, row in type_df.iterrows():
        render_event_card(row, event_config)


def render_source_status_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No source status data available. Run the scraper to populate.")
        return

    total = len(df)
    success = len(df[df["status"] == "success"])
    errors = len(df[df["status"] == "error"])
    partial = len(df[df["status"] == "partial"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sources", total)
    col2.metric("Working", success)
    col3.metric("Partial", partial)
    col4.metric("Failed", errors)

    def icon(status: str) -> str:
        return {"success": "🟢", "partial": "🟡"}.get(status, "🔴")

    display = []
    for _, row in df.iterrows():
        last = row.get("last_check", "")
        if last:
            try:
                dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                last = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        display.append(
            {
                "Status": icon(row["status"]),
                "Source": row["source_name"],
                "Events": row.get("events_found", 0),
                "Last Check": last,
                "Error": row.get("error_message") or "",
            }
        )
    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)


def main() -> None:
    hero_html = (
        '<div class="main-header">'
        '<div class="eyebrow">Campfire · Sales Intelligence</div>'
        '<h1>Campfire Trigger Events</h1>'
        '<p>Venture-backed SaaS and AI company signals — funding rounds, finance '
        'leadership hires, ERP/accounting-stack change signals, and audit/compliance '
        'readiness — mapped to Campfire’s ideal customer profile.</p>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    client = get_supabase_client()
    if not client:
        st.warning("⚠️ Supabase not configured")
        st.info(
            """
        **To connect to Supabase:**

        Add to Streamlit secrets:
        ```
        SUPABASE_URL = "https://your-project.supabase.co"
        SUPABASE_KEY = "your-anon-key"
        ```

        And run `supabase/schema.sql` in the Supabase SQL editor.
            """
        )
        return

    # Sidebar filters
    st.sidebar.markdown("### Filters")
    days = st.sidebar.slider("Time Range (days)", 1, 90, 30)
    if st.sidebar.button("🔄 Refresh data", use_container_width=True, help="Bypass the 5-min cache"):
        _fetch_events.clear()
        st.rerun()

    st.markdown('<div class="search-container">', unsafe_allow_html=True)
    search = st.text_input(
        "Search",
        placeholder="🔍 Search by company, sector, or keyword…",
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    df = load_events(days=days, search=search or None)

    if df.empty:
        # Distinguish "wrong/empty project" from "no rows in this time window"
        # so a Supabase project/credentials mismatch isn't mistaken for no data.
        overview = _events_overview()
        host = (_supabase_url() or "").replace("https://", "").rstrip("/")
        if overview["total"] == 0:
            st.warning(
                f"📭 Connected to Supabase project **{host or 'unknown'}**, "
                "but it has **0 events**. The scraper is likely writing to a "
                "*different* Supabase project than this dashboard reads from. "
                "Point the dashboard's `SUPABASE_URL` / `SUPABASE_KEY` secrets "
                "at the same project the scraper/email alerts use, then refresh."
            )
        else:
            st.info(
                f"📭 No events in the last **{days} days**, but this project "
                f"(**{host or 'unknown'}**) has **{overview['total']}** events "
                f"total (latest: {overview['latest']}). Widen the *Time Range* "
                "slider, or check that the scraper is still running."
            )
        return

    # Region filter — Campfire prioritizes US leads but keeps international visible.
    if "is_us_company" in df.columns:
        st.sidebar.markdown("### Region")
        region_choice = st.sidebar.radio(
            "Region",
            options=["US priority", "US only", "International only", "All"],
            index=0,
            label_visibility="collapsed",
            help=(
                "‘US priority’ shows everything but sorts US companies first. "
                "‘US only’ hides international. ‘International only’ shows only "
                "non-US leads. ‘All’ treats all regions equally."
            ),
        )
        if region_choice == "US only":
            df = df[df["is_us_company"].apply(_safe_tribool) == True]  # noqa: E712
        elif region_choice == "International only":
            df = df[df["is_us_company"].apply(_safe_tribool) == False]  # noqa: E712
    else:
        region_choice = "All"

    if df.empty:
        st.info("📭 No events match the selected region filter.")
        return

    # Sector filter — slice Campfire's ICP by vertical
    sector_options = [
        (key, SECTOR_LABELS.get(key, key))
        for key in SECTOR_LABELS
        if "sector" in df.columns and (df["sector"] == key).any()
    ]
    selected_sectors: list[str] = []
    if sector_options:
        st.sidebar.markdown("### Sector")
        selected_labels = st.sidebar.multiselect(
            "Filter by sector",
            options=[label for _, label in sector_options],
            default=[],
            label_visibility="collapsed",
            placeholder="All sectors",
        )
        label_to_key = {label: key for key, label in sector_options}
        selected_sectors = [label_to_key[label] for label in selected_labels]
        if selected_sectors:
            df = df[df["sector"].isin(selected_sectors)]

    if df.empty:
        st.info("📭 No events match the selected sector filter.")
        return

    # Campfire fit filters — broken out by user-applied sector tag.
    # Reps tag each lead from the card dropdown; this section filters on those tags.
    st.sidebar.markdown("### Campfire Fit · Sector Tag")
    if "user_sector" in df.columns:
        tag_counts = (
            df["user_sector"].dropna().replace("", pd.NA).dropna().value_counts().to_dict()
        )
    else:
        tag_counts = {}
    available_tags = [t for t in USER_SECTOR_OPTIONS if tag_counts.get(t, 0) > 0]
    untagged_count = len(df) - sum(tag_counts.get(t, 0) for t in USER_SECTOR_OPTIONS)
    selected_user_sectors = st.sidebar.multiselect(
        "Filter by sector tag",
        options=USER_SECTOR_OPTIONS,
        default=[],
        format_func=lambda t: f"{t} ({tag_counts.get(t, 0)})",
        label_visibility="collapsed",
        placeholder="All tagged sectors",
        help=(
            "Filters by the per-lead sector tag set from the card dropdown. "
            "Leads without a tag are hidden when any filter is selected."
        ),
    )
    show_untagged = st.sidebar.checkbox(
        f"Include untagged ({untagged_count})",
        value=False,
        help="Also show leads that haven’t been tagged by sector yet.",
    )
    if selected_user_sectors and "user_sector" in df.columns:
        mask = df["user_sector"].isin(selected_user_sectors)
        if show_untagged:
            mask = mask | df["user_sector"].isna() | (df["user_sector"] == "")
        df = df[mask]
    if available_tags:
        st.sidebar.caption(
            "Tagged: "
            + " · ".join(f"{t} {tag_counts[t]}" for t in available_tags)
        )

    # Campfire-fit signal filters — show only leads that exhibit a given signal.
    st.sidebar.markdown("### Campfire Fit Signals")
    if "erp_pain_signal" in df.columns:
        pain_count = int(df["erp_pain_signal"].fillna(False).astype(bool).sum())
        if st.sidebar.checkbox(
            f"🔥 Only ERP/close-pain leads ({pain_count})",
            value=False,
            help="Article mentions close, reconciliation, or reporting pain.",
        ):
            df = df[df["erp_pain_signal"].fillna(False).astype(bool)]
    if not df.empty and "legacy_erp_mention" in df.columns:
        legacy_count = int(df["legacy_erp_mention"].fillna(False).astype(bool).sum())
        if st.sidebar.checkbox(
            f"🗂 Only legacy-ERP leads ({legacy_count})",
            value=False,
            help="Company names NetSuite, Sage Intacct, SAP, or a similar full ERP.",
        ):
            df = df[df["legacy_erp_mention"].fillna(False).astype(bool)]
    if not df.empty and "entry_stack_mention" in df.columns:
        entry_count = int(df["entry_stack_mention"].fillna(False).astype(bool).sum())
        if st.sidebar.checkbox(
            f"📇 Only QuickBooks/Xero leads ({entry_count})",
            value=False,
            help="Company names QuickBooks or Xero (outgrowing entry-level tools).",
        ):
            df = df[df["entry_stack_mention"].fillna(False).astype(bool)]
    if not df.empty and "integration_match" in df.columns:
        int_count = int(
            df["integration_match"].fillna("").astype(str).str.strip().ne("").sum()
        )
        if st.sidebar.checkbox(
            f"🔌 Only stack-match leads ({int_count})",
            value=False,
            help="Company mentions a tool in Campfire's adjacent stack (Stripe, Salesforce, Ramp…).",
        ):
            df = df[
                df["integration_match"].fillna("").astype(str).str.strip().ne("")
            ]

    if df.empty:
        st.info("📭 No events match the selected Campfire-fit signal filters.")
        return

    if "billing_model" in df.columns:
        billing_options = [
            c for c in ["SUBSCRIPTION", "USAGE_BASED", "SUBSCRIPTION_PLUS_USAGE"]
            if (df["billing_model"] == c).any()
        ]
        if billing_options:
            billing_labels = {
                "SUBSCRIPTION": "📅 Subscription",
                "USAGE_BASED": "📊 Usage-Based",
                "SUBSCRIPTION_PLUS_USAGE": "🔄 Sub + Usage",
            }
            selected_billing = st.sidebar.multiselect(
                "Billing model",
                options=[billing_labels[c] for c in billing_options],
                default=[],
                placeholder="All billing models",
            )
            chosen = [
                c for c in billing_options
                if billing_labels[c] in selected_billing
            ]
            if chosen:
                df = df[df["billing_model"].isin(chosen)]

    if df.empty:
        st.info("📭 No events match the selected Campfire-fit filters.")
        return

    # US-priority sort: US leads float above international when "US priority"
    # is the active region mode. Downstream render_event_section preserves
    # the order via stable sort on relevance_score.
    if region_choice == "US priority" and "is_us_company" in df.columns:
        df = df.copy()
        df["_us_rank"] = df["is_us_company"].apply(
            lambda v: 0 if _safe_tribool(v) is True
            else (2 if _safe_tribool(v) is False else 1)
        )
        df = df.sort_values(
            by=["_us_rank", "relevance_score", "discovered_date"],
            ascending=[True, False, False],
        ).drop(columns=["_us_rank"])

    # Metrics — Campfire palette (ink + ember)
    type_counts = df["event_type"].value_counts().to_dict()
    new_count = len(df[df["lead_status"] == "NEW"])
    top_sector_label = "—"
    if "sector" in df.columns and not df["sector"].dropna().empty:
        top_key = df["sector"].replace("", pd.NA).dropna().value_counts().idxmax()
        top_sector_label = SECTOR_LABELS.get(top_key, top_key)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_metric_card("📊", len(df), "Total Signals", "#1A1207")
    with col2:
        render_metric_card("🆕", new_count, "New Leads", "#EA580C")
    with col3:
        render_metric_card("💰", type_counts.get("funding", 0), "Funding Rounds", "#F59E0B")
    with col4:
        render_metric_card("👤", type_counts.get("finance_exec_hire", 0), "Finance Hires", "#4C1D95")
    with col5:
        render_metric_card(
            "🔧",
            type_counts.get("erp_change_signal", 0) + type_counts.get("compliance_signal", 0),
            "ERP / Compliance",
            "#1E3A8A",
        )

    st.sidebar.markdown("---")
    st.sidebar.caption(f"🏷 Top sector: **{top_sector_label}**")

    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("📡 Source Health", expanded=False):
        render_source_status_table(load_source_statuses())

    st.markdown("<br>", unsafe_allow_html=True)

    new_df = df[df["lead_status"] == "NEW"]
    classified_df = df[df["lead_status"] != "NEW"]

    # New Leads
    new_header_html = (
        '<div class="section-header">'
        '<span style="font-size: 1.5rem;">🆕</span>'
        '<h2>New Leads</h2>'
        f'<span class="section-count">{len(new_df)}</span>'
        '</div>'
    )
    st.markdown(new_header_html, unsafe_allow_html=True)

    if new_df.empty:
        st.info("No new leads to review. Nice work!")
    else:
        n_funding = len(new_df[new_df["event_type"] == "funding"])
        n_hire    = len(new_df[new_df["event_type"] == "finance_exec_hire"])
        n_erp     = len(new_df[new_df["event_type"] == "erp_change_signal"])
        n_comp    = len(new_df[new_df["event_type"] == "compliance_signal"])

        tab_funding, tab_hire, tab_erp, tab_comp = st.tabs([
            f"💰 Funding ({n_funding})",
            f"👤 Finance Hires ({n_hire})",
            f"🔧 ERP Change ({n_erp})",
            f"📋 Compliance ({n_comp})",
        ])

        with tab_funding:
            render_event_section(new_df, "funding", EVENT_TYPES["funding"])
        with tab_hire:
            render_event_section(new_df, "finance_exec_hire", EVENT_TYPES["finance_exec_hire"])
        with tab_erp:
            render_event_section(new_df, "erp_change_signal", EVENT_TYPES["erp_change_signal"])
        with tab_comp:
            render_event_section(new_df, "compliance_signal", EVENT_TYPES["compliance_signal"])

    st.markdown("<br>", unsafe_allow_html=True)

    # Classified Leads
    classified_header_html = (
        '<div class="section-header">'
        '<span style="font-size: 1.5rem;">📋</span>'
        '<h2>Classified Leads</h2>'
        f'<span class="section-count">{len(classified_df)}</span>'
        '</div>'
    )
    st.markdown(classified_header_html, unsafe_allow_html=True)

    if classified_df.empty:
        st.info("No classified leads yet. Review new leads above to classify them.")
    else:
        classified_statuses = [s for s in LEAD_STATUSES if s not in ("NEW", "NOT RELEVANT")]
        tab_labels, tab_keys = [], []
        for s in classified_statuses:
            count = len(classified_df[classified_df["lead_status"] == s])
            if count > 0:
                cfg = STATUS_CONFIG.get(s, {"icon": "📋", "label": s})
                tab_labels.append(f"{cfg['icon']} {cfg['label']} ({count})")
                tab_keys.append(s)

        if tab_labels:
            tabs = st.tabs(tab_labels)
            for tab, status_key in zip(tabs, tab_keys):
                with tab:
                    status_df = classified_df[classified_df["lead_status"] == status_key]
                    if "relevance_score" in status_df.columns:
                        status_df = status_df.sort_values(
                            by=["relevance_score", "discovered_date"],
                            ascending=[False, False],
                        )
                    for _, row in status_df.iterrows():
                        cfg = EVENT_TYPES.get(row.get("event_type", "other"), EVENT_TYPES["other"])
                        render_event_card(row, cfg)

    st.markdown("<br>", unsafe_allow_html=True)

    # All Events Table + Export
    with st.expander("📊 All Events Table", expanded=False):
        cols = [
            "event_type", "sector", "user_sector", "company_name",
            "company_country", "hq_city", "hq_state", "founder_name",
            "founding_year", "arr", "total_funding", "billing_model",
            "erp_pain_signal", "legacy_erp_mention", "entry_stack_mention",
            "integration_match", "legacy_systems", "tech_stack",
            "company_website", "title", "published_date", "lead_status",
        ]
        available = [c for c in cols if c in df.columns]
        display = df[available].copy()
        rename_map = {
            "event_type": "Type",
            "sector": "Sector (auto)",
            "user_sector": "Sector (tag)",
            "company_name": "Company",
            "company_country": "Region",
            "hq_city": "HQ City",
            "hq_state": "HQ State",
            "founder_name": "Founder",
            "founding_year": "Founded",
            "arr": "ARR",
            "total_funding": "Total Raised",
            "billing_model": "Billing Model",
            "erp_pain_signal": "ERP/Close Pain",
            "legacy_erp_mention": "Legacy ERP",
            "entry_stack_mention": "QuickBooks/Xero",
            "integration_match": "Stack Match",
            "legacy_systems": "Legacy Systems",
            "tech_stack": "Tech Stack",
            "company_website": "Website",
            "title": "Title",
            "published_date": "Published",
            "lead_status": "Status",
        }
        display.columns = [rename_map[c] for c in available]
        if "Sector (auto)" in display.columns:
            display["Sector (auto)"] = display["Sector (auto)"].map(
                lambda k: SECTOR_LABELS.get(k, "") if k else ""
            )
        st.dataframe(display, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Export CSV",
            csv,
            file_name=f"campfire_trigger_events_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    # Sidebar bulk actions
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Bulk Actions")
    st.sidebar.caption("Apply to all NEW leads:")

    bulk_options = [s for s in LEAD_STATUSES if s != "NEW"]
    bulk_status = st.sidebar.selectbox(
        "Mark all new as:",
        ["Select status…"] + bulk_options,
        label_visibility="collapsed",
    )
    if (
        bulk_status
        and bulk_status != "Select status…"
        and st.sidebar.button("✓ Apply to All New", use_container_width=True)
    ):
        updated = 0
        for event_id in new_df["id"].tolist():
            try:
                if bulk_status == "NOT RELEVANT":
                    client.table("events").delete().eq("id", event_id).execute()
                else:
                    client.table("events").update({"lead_status": bulk_status}).eq(
                        "id", event_id
                    ).execute()
                updated += 1
            except Exception:
                pass
        st.sidebar.success(f"✓ Updated {updated} events!")
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("🔥 CampfireSignalSearch — Campfire Sales Intel")


if __name__ == "__main__":
    main()
