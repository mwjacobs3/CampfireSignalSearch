"""Email alert manager — sends HTML digests grouped by Campfire event type."""

from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from jinja2 import Template

from .models import EventType, TriggerEvent

_CATEGORY_META = {
    EventType.FUNDING:           {"icon": "💰", "label": "Funding Rounds"},
    EventType.FINANCE_EXEC_HIRE: {"icon": "👤", "label": "Finance Leadership Hires"},
    EventType.ERP_CHANGE_SIGNAL: {"icon": "🔧", "label": "ERP / Accounting-Stack Change Signals"},
    EventType.COMPLIANCE_SIGNAL: {"icon": "📋", "label": "Audit / Compliance Readiness"},
    EventType.OTHER:              {"icon": "📌", "label": "Other"},
}

_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
           color: #222; max-width: 680px; margin: 0 auto; }
    .header { background: linear-gradient(135deg, #ea580c 0%, #7c2d12 100%);
              padding: 1.75rem 2rem; border-radius: 14px; margin-bottom: 1.5rem; }
    .header h1 { color: #fff; margin: 0; font-size: 1.6rem; font-weight: 700; }
    .header p  { color: rgba(255,255,255,.85); margin: .4rem 0 0; font-size: .9rem; }
    h2 { font-size: 1rem; text-transform: uppercase; letter-spacing: .8px;
         color: #1a1a2e; margin: 1.75rem 0 .75rem; border-bottom: 2px solid #f1f5f9;
         padding-bottom: .5rem; }
    .card { border-left: 4px solid #ea580c; padding: .7rem 1rem;
            margin-bottom: .9rem; background: #f7f9fc; border-radius: 0 8px 8px 0; }
    .card a { color: #ea580c; font-weight: 600; font-size: .95rem;
               text-decoration: none; }
    .meta { font-size: .75rem; color: #6b7280; margin-top: .3rem; }
    .company { font-size: .8rem; color: #374151; margin-top: .25rem; }
    .summary { font-size: .8rem; color: #555; margin-top: .4rem; }
    .badge { display: inline-block; padding: .2rem .55rem; border-radius: 50px;
             font-size: .65rem; font-weight: 700; text-transform: uppercase;
             letter-spacing: .4px; margin-right: .4rem; }
    .badge-funding { background: #fef3c7; color: #92400e; }
    .badge-hire    { background: #ede9fe; color: #5b21b6; }
    .badge-erp     { background: #dbeafe; color: #1e40af; }
    .badge-compliance { background: #dcfce7; color: #166534; }
    .footer { font-size: .7rem; color: #9ca3af; margin-top: 2rem;
              border-top: 1px solid #e5e7eb; padding-top: .75rem; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🔥 {{ heading }}</h1>
    <p>{{ date }} &nbsp;·&nbsp; <strong>{{ total }}</strong> new signals</p>
  </div>

  {% for etype, meta in categories.items() %}
  {% set items = grouped[etype] %}
  {% if items %}
  <h2>{{ meta.icon }} {{ meta.label }} ({{ items|length }})</h2>
  {% for e in items %}
  <div class="card">
    <a href="{{ e.url }}" target="_blank">{{ e.title[:120] }}</a>
    {% if e.company_name %}<div class="company">🏢 {{ e.company_name }}{% if e.is_us_company == True %} &nbsp;·&nbsp; 🇺🇸 US{% elif e.is_us_company == False %} &nbsp;·&nbsp; 🌍 {{ e.company_country or 'International' }}{% endif %}{% if e.hq_city and e.hq_state %} &nbsp;·&nbsp; 📍 {{ e.hq_city }}, {{ e.hq_state }}{% endif %}{% if e.funding_round %} &nbsp;·&nbsp; {{ e.funding_round }}{% endif %}{% if e.funding_amount %} &nbsp;·&nbsp; {{ e.funding_amount }}{% endif %}</div>{% endif %}
    {% if e.founder_name %}<div class="company">🌱 Founder: {{ e.founder_name }}{% if e.founder_linkedin %} &nbsp;·&nbsp; <a href="https://{{ e.founder_linkedin }}">LinkedIn</a>{% endif %}</div>{% endif %}
    {% if e.person_name %}<div class="company">👤 {{ e.person_name }}{% if e.person_title %} — {{ e.person_title }}{% endif %}</div>{% endif %}
    {% if e.founding_year or e.total_funding or e.arr or e.employee_count %}<div class="company">📈
      {% if e.founding_year %}Founded {{ e.founding_year }}{% endif %}
      {% if e.employee_count %} &nbsp;·&nbsp; {{ e.employee_count }} employees{% endif %}
      {% if e.arr %} &nbsp;·&nbsp; {{ e.arr }}{% endif %}
      {% if e.total_funding %} &nbsp;·&nbsp; {{ e.total_funding }} raised to date{% endif %}
    </div>{% endif %}
    {% if e.erp_pain_signal or e.legacy_erp_mention or e.entry_stack_mention or e.billing_model %}<div class="company">🎯
      {% if e.erp_pain_signal %}<span class="badge badge-hire">Close/ERP Pain</span>{% endif %}
      {% if e.legacy_erp_mention %}<span class="badge badge-erp">Legacy ERP</span>{% endif %}
      {% if e.entry_stack_mention %}<span class="badge badge-funding">QuickBooks/Xero</span>{% endif %}
      {% if e.billing_model %}<span class="badge badge-compliance">{{ e.billing_model|replace('_PLUS_', ' + ')|replace('_', ' ') }}</span>{% endif %}
    </div>{% endif %}
    {% if e.legacy_systems %}<div class="company">🗂 Stack: {{ e.legacy_systems|join(', ') }}</div>{% endif %}
    {% if e.company_website %}<div class="company">🔗 <a href="https://{{ e.company_website }}">{{ e.company_website }}</a></div>{% endif %}
    {% if e.hubspot_company_url %}<div class="company">🧡 <a href="{{ e.hubspot_company_url }}">View in HubSpot</a></div>{% endif %}
    <div class="meta">{{ e.source_name }} &nbsp;·&nbsp; {{ e.published_date.strftime('%b %d, %Y') if e.published_date else '' }}</div>
    {% if e.description %}<div class="summary">{{ e.description[:200] }}{% if e.description|length > 200 %}…{% endif %}</div>{% endif %}
  </div>
  {% endfor %}
  {% endif %}
  {% endfor %}

  <div class="footer">CampfireSignalSearch &nbsp;·&nbsp; Selling Campfire to venture-backed SaaS/AI finance teams</div>
</body>
</html>
"""

_TEXT_TEMPLATE = """{{ heading|upper }}
{{ date }} | {{ total }} new signals
{% for etype, meta in categories.items() %}{% set items = grouped[etype] %}{% if items %}
{{ meta.icon }} {{ meta.label|upper }} ({{ items|length }})
{% for e in items %}• {{ e.title }}
  {{ e.url }}
  {{ e.source_name }} | {{ e.published_date.strftime('%b %d, %Y') if e.published_date else '' }}
{% if e.company_name %}  Company: {{ e.company_name }}{% if e.is_us_company == True %} [US]{% elif e.is_us_company == False %} [{{ e.company_country or 'International' }}]{% endif %}{% endif %}
{% if e.founder_name %}  Founder: {{ e.founder_name }}{% endif %}
{% if e.hubspot_company_url %}  HubSpot: {{ e.hubspot_company_url }}{% endif %}
{% endfor %}{% endif %}{% endfor %}"""


class AlertManager:

    def __init__(self, config: dict[str, Any]):
        email_cfg = config.get("alerts", {}).get("email", {})
        self.enabled    = email_cfg.get("enabled", False)
        self.sender     = email_cfg.get("sender_email") or os.environ.get("EMAIL_SENDER", "")
        self.password   = email_cfg.get("sender_password") or os.environ.get("EMAIL_PASSWORD", "")
        raw_recipients  = email_cfg.get("recipient_emails") or []
        env_recips      = [r.strip() for r in os.environ.get("EMAIL_RECIPIENTS", "").split(",") if r.strip()]
        # Merge config recipients with the EMAIL_RECIPIENTS secret so a baseline
        # recipient set in config always gets the digest even when the secret is
        # unset — de-duplicated, order-preserving (config first).
        self.recipients = list(dict.fromkeys([*raw_recipients, *env_recips]))
        self.smtp_host  = email_cfg.get("smtp_host") or os.environ.get("SMTP_HOST") or "smtp.gmail.com"
        self.smtp_port  = int(email_cfg.get("smtp_port") or os.environ.get("SMTP_PORT") or "587")

    def send_alerts(
        self,
        events: list[TriggerEvent],
        heading: str = "Campfire Trigger Events — Campfire ICP",
        subject_label: str = "Campfire Alert",
    ) -> int:
        if not events:
            return 0
        handlers = 0
        if self.enabled and self.sender and self.recipients:
            if self._send_email(events, heading=heading, subject_label=subject_label):
                handlers += 1
        return handlers

    def _send_email(
        self,
        events: list[TriggerEvent],
        heading: str = "Campfire Trigger Events — Campfire ICP",
        subject_label: str = "Campfire Alert",
    ) -> bool:
        grouped: dict[EventType, list[TriggerEvent]] = {et: [] for et in EventType}
        for e in events:
            grouped[e.event_type].append(e)

        # Campfire priority: US leads first in every section, then by relevance.
        def _rank(ev: TriggerEvent) -> tuple[int, float]:
            us_rank = 0 if ev.is_us_company is True else (2 if ev.is_us_company is False else 1)
            return (us_rank, -(ev.relevance_score or 0))

        for et in grouped:
            grouped[et].sort(key=_rank)

        date_str   = datetime.now().strftime("%B %d, %Y %H:%M")
        categories = _CATEGORY_META

        ctx = {"date": date_str, "total": len(events), "heading": heading,
               "grouped": grouped, "categories": categories}

        html = Template(_HTML_TEMPLATE).render(**ctx)
        text = Template(_TEXT_TEMPLATE).render(**ctx)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{subject_label} — {datetime.now().strftime('%b %d')} ({len(events)} signals)"
        msg["From"]    = self.sender
        msg["To"]      = ", ".join(self.recipients)
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        print(f"  [Email] Connecting to {self.smtp_host}:{self.smtp_port} as {self.sender}")
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            try:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipients, msg.as_string())
                print(f"  [Email] Digest sent → {self.recipients} ({len(events)} events)")
                return True
            finally:
                try:
                    server.quit()
                except Exception:
                    pass
        except Exception as exc:
            print(f"  [Email] Failed: {exc}")
            return False
