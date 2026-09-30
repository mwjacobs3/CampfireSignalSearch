# CampfireSignalSearch

Alert system that surfaces **buying-signal / trigger events for [Campfire](https://campfire.ai)**
so you can find accounts to reach out to. Campfire is the AI-native ERP and
general ledger for venture-backed SaaS/AI companies that have outgrown
QuickBooks or Xero and resent NetSuite, Sage Intacct, or SAP.

Monitors five categories every 4 hours:

| 💰 | **Funding Rounds** — Series B/C/D+ raises at SaaS/AI companies |
| 👤 | **Finance Leadership Hires** — new CFO / VP Finance / Controller hires |
| 🔧 | **ERP / Accounting-Stack Change Signals** — outgrowing QuickBooks/Xero, evaluating or ripping out NetSuite/Sage Intacct/SAP |
| 📋 | **Audit / Compliance Readiness** — SOC 2, IPO/S-1 filings, first audit |
| 🧑‍💼 | **Finance / Accounting Team Hiring** — press coverage of a growing finance team, *plus* real open reqs (Staff Accountant, AP/AR, Payroll, FP&A, …) found on the company's own public job board |

Results land in **Supabase**, email **digests ship every 4 hours**, and a
**Streamlit dashboard** lets you triage leads (mark as Added to Lead List,
Campfire Customer/Prospect, or Not Relevant).

## Architecture

```
┌────────────────────────┐                 ┌──────────────────────────────┐
│  GitHub Actions cron   │──┐              │       src.main               │
│  0 */4 * * *           │  │              │   ┌────────────────────┐     │
└────────────────────────┘  │              │   │ GoogleNewsScraper  │──┐  │
                            ├─────────────▶│   │ RSSFeedScraper     │  │  │
┌────────────────────────┐  │              │   │ FundingFeedScraper │──┼──┼──▶ Supabase
│  Local CLI             │──┘              │   │ ExecHireScraper    │  │  │    ├─ events
│  python -m src.main    │                 │   └────────────────────┘  │  │    └─ source_status
└────────────────────────┘                 │            │              │  │
                                           │   ICP filter + dedupe ◀───┘  │
                                           └────────────┬─────────────────┘
                                                        │
                                       ┌────────────────┴─────────────────┐
                                       ▼                                  ▼
                               ┌──────────────┐                  ┌────────────────┐
                               │ src.alerts   │                  │  dashboard.py  │
                               │ email digest │                  │  (Streamlit)   │
                               └──────────────┘                  └────────────────┘
```

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/mwjacobs3/CampfireSignalSearch.git
cd CampfireSignalSearch
pip install -r requirements.txt
cp .env.example .env
```

### 2. Set up Supabase

1. Create a project at [app.supabase.com](https://app.supabase.com).
2. SQL Editor → paste [`supabase/schema.sql`](supabase/schema.sql) → Run. This one
   file is the **complete, idempotent schema**. Run it on a new *or* existing
   project to bring it fully up to date — it only adds what's missing and
   never drops data.
   > ⚠️ The scraper writes ~35 columns; if even one is missing, **every insert
   > fails silently** and the table stops growing. `schema.sql` exists so this
   > can't happen. (The scraper also self-checks on startup via `verify_schema()`.)
3. Grab the project URL, the **anon key** (dashboard), and the **service_role key** (scraper).
4. Fill them into `.env`. The dashboard's `SUPABASE_URL`/`SUPABASE_KEY` **must
   point at the same project** as the scraper's `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`.

### 3. Run locally

```bash
cp config.example.yaml config.yaml   # customize ICP filters / queries if desired
python -m src.main                    # one-shot scrape
python -m src.main --daemon           # runs on the interval in config.yaml
streamlit run dashboard.py            # open the triage UI
```

### 4. Deploy the 4-hour cron to GitHub Actions

In your repo **Settings → Secrets and variables → Actions** add:

| Secret | Required | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service role key (bypasses RLS) |
| `EMAIL_SENDER` | ✅ | Gmail address |
| `EMAIL_PASSWORD` | ✅ | [Gmail App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_RECIPIENTS` | ✅ | Comma-separated addresses |
| `SMTP_HOST` | ⬜ | Defaults to `smtp.gmail.com` |
| `SMTP_PORT` | ⬜ | Defaults to `587` |
| `NEWS_API_KEY` | ⬜ | [newsapi.org](https://newsapi.org) — broader coverage |
| `SERP_API_KEY` | ⬜ | [serpapi.com](https://serpapi.com) |
| `ANTHROPIC_API_KEY` | ⬜ | Enables Claude relevance scoring |

The `.github/workflows/scraper.yml` workflow runs on cron `0 */4 * * *`
(every 4 hours) and on-demand via **Actions → Campfire Trigger Event Scraper → Run workflow**.

### 5. Deploy the dashboard to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and connect this repo.
2. Main file: `dashboard.py`. Python version is pinned to 3.11 via `runtime.txt`.
3. Under **Advanced settings → Secrets**, paste (use the **anon key**, not service_role):
   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-anon-key"
   ```
4. Deploy. Theme + server settings are pre-configured in `.streamlit/config.toml`.

## Repository layout

```
CampfireSignalSearch/
├── dashboard.py                     # Streamlit triage UI
├── main.py                          # thin shim → src.main
├── config.example.yaml              # scraper config template (ICP, queries, filters)
├── requirements.txt
├── runtime.txt                      # Python 3.11 pin for Streamlit Cloud
├── .env.example
├── .streamlit/config.toml           # dashboard theme + server settings
├── .github/workflows/scraper.yml    # cron: every 4 hours
├── supabase/
│   └── schema.sql                  # ⭐ complete idempotent schema — run this one
└── src/
    ├── main.py                      # orchestrator + scheduler + Supabase sync
    ├── models.py                    # TriggerEvent dataclass
    ├── database.py                  # Supabase client + upserts
    ├── alerts.py                    # HTML + plain-text email digest
    ├── enrichment.py                # website + stack-fingerprint enrichment
    └── scrapers/
        ├── base.py                  # shared scraper helpers + Campfire ICP scoring
        ├── rss_scraper.py           # SaaS/startup/finance trade press
        ├── news_scraper.py          # Google News RSS (no API key)
        ├── funding_feed_scraper.py  # TechCrunch / Crunchbase / VentureBeat / FinSMEs
        └── exec_hire_scraper.py     # BusinessWire / PR Newswire finance-hire announcements
```

## What is the Campfire ICP?

Campfire ([campfire.ai](https://campfire.ai)) is an AI-native ERP and general
ledger built for venture-backed **SaaS and AI-native companies roughly $20M–
$300M ARR** — companies that have **outgrown QuickBooks or Xero** but "resent
everything about NetSuite" (and, by extension, Sage Intacct and SAP). Its
core wedge is revenue automation (ASC 606, subscription and usage-based
billing), multi-entity/multi-currency consolidation, continuous close, and an
AI assistant (Ember) that answers finance questions in plain English.

That means the strongest buying signals are **not** product launches or
retail expansion (the CPG-focused predecessor this project's scaffolding was
adapted from) — they're:

- A **fresh funding round** (Series B+), which triggers board-reporting and
  audit-readiness pressure long before the finance stack is ready for it.
- A **new finance leader** (CFO, VP Finance, Controller, Head of FP&A) — the
  single highest-signal trigger, since a new hire almost always re-evaluates
  the accounting stack in their first 90 days.
- A **growing finance/accounting team below the exec seat** — open reqs for
  Staff/Senior Accountant, AP/AR, Payroll, FP&A Analyst, or Accounting Manager
  signal scaling finance ops even before a new CFO is named.
- **Named legacy/entry systems** in press or job copy — NetSuite, Sage
  Intacct, SAP, QuickBooks, Xero — especially alongside "outgrew," "ripping
  out," "migrating off," or "implementing" language.
- **Audit/compliance milestones** — SOC 2 Type II, an S-1 filing, or a first
  annual audit — that suddenly demand investor-ready financials.

**LOW ICP fit** (flag and note, but still score honestly):
- Pure hardware/CPG/physical-goods companies with no software product
- Companies already on a modern Campfire competitor (Rillet, Puzzle, Mosaic, …)
- Already-public enterprise software giants (Salesforce, Workday, Oracle, …)
- Bootstrapped/self-funded companies with no board-reporting pressure

## Sources monitored

Every 4-hour run pulls from **four** scrapers. All sources are filtered by
the Campfire ICP rules in `config.yaml` (venture-backed SaaS/AI, excludes
already-public mega-caps and non-tech sectors like CPG/retail/real estate).
Region is **tagged, not filtered** — US companies are flagged 🇺🇸 and boosted
in the relevance score, while international leads are kept visible (but
scored lower). Founders are auto-extracted from article copy so the lead
card points straight at a contact for earlier-stage companies.

### Per-lead enrichment

Each event is parsed on three axes so sales can qualify before clicking through:

| Axis | Fields |
|---|---|
| **Outreach** | `company_website` · `company_linkedin` · `founder_linkedin` · `hq_city` · `hq_state` |
| **Viability** | `founding_year` · `employee_count` · `total_funding` (cumulative raised) · `arr` (when disclosed) |
| **Campfire fit** | `erp_pain_signal` · `legacy_erp_mention` · `entry_stack_mention` · `integration_match` · `billing_model` |
| **Hiring signal** | `hiring_finance_roles` · `open_finance_roles` · `careers_page_url` |

| Signal | Detects | Score bonus |
|---|---|---|
| `erp_pain_signal` | Close/reconciliation/reporting pain language | +15 |
| `legacy_erp_mention` | Named full ERP (NetSuite, Sage Intacct, SAP, Oracle, Dynamics, …) — the exact system Campfire replaces | +18 |
| `entry_stack_mention` | QuickBooks or Xero named — the "outgrown" side of the pitch | +14 |
| `integration_match` | A tool in Campfire's adjacent stack (Stripe, Salesforce, Ramp, Carta, Vanta, …) — or a legacy system it replaces | +5 per hit (cap +15) |
| `billing_model` | Subscription and/or usage-based billing complexity — Campfire's revenue-automation wedge | +10 |

An ERP-change story that also names the legacy/entry system being replaced
gets an additional bonus — the Campfire sweet spot.

### Careers-page / job-board enrichment (best-effort, no API key needed)

For every fit lead that clears the ICP filters, we also check the company's
own public Greenhouse/Lever/Ashby job board for open accounting/finance reqs
(Staff Accountant, AP/AR, Payroll, FP&A Analyst, Controller, …). Unlike
LinkedIn or Indeed, these ATS boards are unauthenticated JSON APIs meant to
power a company's own careers widget, so they don't block bots — we get a
real, current headcount signal instead of relying on press coverage, which
almost never reports individual-contributor hires.

The board is found by scanning the homepage HTML already fetched for stack
enrichment (below) for a `boards.greenhouse.io` / `jobs.lever.co` /
`jobs.ashbyhq.com` link; if none is embedded there, a few common `/careers`
paths are probed as a fallback. Any hit sets `hiring_finance_roles = true`,
records the matched titles in `open_finance_roles`, and adds a relevance-score
bonus — same best-effort, try/except-wrapped pattern as the rest of
enrichment, so a missing board or failed fetch never blocks ingestion.

### Website-stack enrichment (best-effort, no API key needed)

A B2B SaaS marketing homepage rarely reveals a company's internal ERP
choice, but it often leaks adjacent signals: a Stripe Checkout embed, a
HubSpot tracking script, a Vanta/Drata/Secureframe trust-center badge (a SOC
2 program in progress — a strong compliance signal), or a
Greenhouse/Lever/Ashby careers-board embed (a headcount-growth proxy). After
scraping + dedup, each lead's `company_website` is fetched once and
fingerprinted for those tells, merged into `tech_stack`, and re-evaluated
against the Campfire-adjacent-stack list.

The whole step is wrapped in try/except — enrichment is strictly best-effort
and never blocks event ingestion. Toggle in `config.yaml`:

```yaml
enrichment:
  enabled: true
  timeout_seconds: 6
```

### Lead quality controls

Two knobs in `config.yaml` decide which leads survive each cycle:

| Setting | Default | Purpose |
|---|---|---|
| `scraper.min_relevance_score` | `40` | Drops weak candidates *before* save. `0` keeps everything; raise to `50`–`60` for stricter pipelines. |
| `scraper.max_age_hours` | `48` | Drops articles whose `published_date` is older than this. `0` disables (use only when seeding the DB). |

Each run prints how many candidates were skipped on each gate, so you can
re-tune from real numbers.

### ICP size band ($20M–$300M ARR)

Campfire targets venture-backed SaaS/AI companies roughly $20M–$300M ARR.
ARR is parsed directly from press when disclosed (tech press reports it far
more often than CPG press reports revenue); total funding raised and
employee count are the fallback proxies:

| Signal | Bonus / penalty |
|---|---|
| ARR parses to **$20M–$300M** | **+25** |
| ARR > **$300M** | **−10** |
| ARR disclosed but < $20M | **−8** |
| *(no ARR found)* Total funding parses to **$20M–$500M** | **+15** |
| *(no ARR found)* Total funding > **$500M** | **−15** |
| Employee count in **50–1500** | **+10** |
| Employee count > **3000** | **−20** |
| Employee count 1500–3000 | **−5** |

The band is tunable in `territory.company_filters.size_band`.

### 1. Trade-press RSS (`RSSScraper`, feeds from `config.yaml`)

TechCrunch · VentureBeat · Axios Pro Rata · Inc. · Fortune Term Sheet ·
SaaStr Blog · The SaaS News · CFO Dive · Accounting Today · Journal of
Accountancy · CFO Brew · BusinessWire/PR Newswire/GlobeNewswire/EIN
Presswire/AccessWire (technology categories).

### 2. Google News (`GoogleNewsScraper`, queries from `config.yaml`)

Every query is expanded to a Google News RSS feed. Grouped by event type:
funding, finance leadership hires, ERP/accounting-stack change signals,
audit/compliance readiness, finance/accounting team hiring, plus a
stack-footprint bucket (companies naming a legacy/entry system or a modern
finance/RevOps tool) and sector-specific
funding queries (AI/ML, fintech, dev tools, cybersecurity).

### 3. Funding feeds (`FundingFeedScraper`)

TechCrunch Startups · VentureBeat · Crunchbase News · FinSMEs · Inc. ·
CFO Dive · SaaStr — unlike the CPG-focused predecessor this scaffolding was
adapted from (which *dropped* these feeds because AI/SaaS/fintech rounds are
off-ICP for a physical-goods seller), Campfire's ICP *is* AI/SaaS/fintech, so
these are core sources here.

### 4. Finance-hire press wires (`ExecHireScraper`, BusinessWire + PR Newswire)

Monitors press-release wires for finance-leadership appointment
announcements, then filters for the Campfire ICP: CFO, Chief Accounting
Officer, VP/SVP/EVP Finance, Head of Finance/Accounting/FP&A, Controller.
Press-release wires are more reliable than scraping job boards (which block bots).

## Lead triage workflow

The dashboard shows `NEW` signals first. Mark each as:

- ✅ **Added to Lead List** — queued for outreach
- 💼 **Campfire Customer / Prospect** — already in the pipeline
- 🚫 **Not Relevant** — noise; deletes from DB

Bulk actions are in the sidebar.

## Background

Adapted from [CPGTriggerEventSearch](https://github.com/mwjacobs3/CPGTriggerEventSearch)
(which itself was repurposed from [TriggerEventSearch](https://github.com/mwjacobs3/TriggerEventSearch),
which targeted CFOs, finance hires, and PE funding — interestingly, closer to
Campfire's actual ICP than the CPG detour in between). Same scaffolding —
scrapers, Supabase sync, Streamlit dashboard, 4-hour GitHub Actions cron —
but every search query, keyword list, and scoring rule is retargeted at
venture-backed SaaS/AI finance buyers.

**A note on RSS feed URLs:** several of the trade-press and press-wire feed
URLs in `config.example.yaml` (BusinessWire category codes, GlobeNewswire
subject codes, individual publication feeds) were selected from public
documentation and common usage rather than live-verified from this
environment's sandbox (outbound requests to most external domains are
blocked here). Spot-check them after cloning — `python -m src.main` prints a
`success` / `partial` / `error` status per source on every run, and the
dashboard's **Source Health** panel surfaces the same thing over time — and
swap out anything that's gone stale.
