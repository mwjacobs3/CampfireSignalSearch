"""
Loads the Account Watch pipeline's company list from a HubSpot CSV export.

No HubSpot API credentials needed: in HubSpot, filter the Companies view to
your owned accounts and use Export > CSV. Replace `owned_accounts.csv` (see
`owned_accounts.example.csv` for the expected shape) on whatever cadence you
like (e.g. weekly) — each scheduled run just reads whatever's currently on
disk, no live HubSpot connection required.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

# HubSpot's default "Companies" export uses headers like "Company name",
# "Company Domain Name", and "Record ID". Matching is case/punctuation
# insensitive so the export can be dropped in without renaming columns.
_NAME_HEADERS = {"companyname", "name"}
_DOMAIN_HEADERS = {"companydomainname", "domain", "website", "websiteurl", "companydomain"}
_ID_HEADERS = {"recordid", "recordidcompany", "companyid", "hubspotid", "id"}


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def load_owned_companies_csv(path: str, portal_id: str = "") -> list[dict]:
    """Parse a HubSpot companies CSV export into the scraper's company shape:
    {"id", "name", "domain", "hubspot_url"}. Rows without a company name are
    skipped. Raises FileNotFoundError if `path` doesn't exist, or ValueError
    if no recognizable company-name column is found.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(path)

    companies: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return companies
        header_map = {_normalize(h): h for h in reader.fieldnames}

        def _col(headers: set[str]) -> Optional[str]:
            for h in headers:
                if h in header_map:
                    return header_map[h]
            return None

        name_col = _col(_NAME_HEADERS)
        domain_col = _col(_DOMAIN_HEADERS)
        id_col = _col(_ID_HEADERS)

        if not name_col:
            raise ValueError(
                f"{path}: couldn't find a company-name column among "
                f"{reader.fieldnames} — expected a header like 'Company name'."
            )

        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            company_id = (row.get(id_col) or "").strip() if id_col else ""
            companies.append({
                "id": company_id,
                "name": name,
                "domain": (row.get(domain_col) or "").strip() if domain_col else "",
                "hubspot_url": (
                    f"https://app.hubspot.com/contacts/{portal_id}/record/0-2/{company_id}"
                    if portal_id and company_id else None
                ),
            })

    return companies
