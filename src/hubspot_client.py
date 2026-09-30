"""
Minimal HubSpot REST client for the Account Watch pipeline.

This runs unattended via GitHub Actions cron (not inside a Claude session),
so it authenticates with its own HubSpot private-app access token rather than
any MCP connection. Create a private app at Settings -> Integrations ->
Private Apps with scopes `crm.objects.companies.read` and
`crm.objects.owners.read`, then set HUBSPOT_ACCESS_TOKEN as a GitHub secret.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotError(RuntimeError):
    pass


class HubSpotClient:

    def __init__(self, access_token: Optional[str] = None, timeout: float = 20.0):
        self.token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
        self.portal_id = os.environ.get("HUBSPOT_PORTAL_ID", "")
        self.timeout = timeout
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            })

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def get_owner_id_by_email(self, email: str) -> Optional[str]:
        """Look up a HubSpot owner's ID from their email address."""
        resp = self.session.get(
            f"{HUBSPOT_API_BASE}/crm/v3/owners",
            params={"email": email, "limit": 1},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise HubSpotError(f"GET /crm/v3/owners failed ({resp.status_code}): {resp.text[:300]}")
        results = resp.json().get("results", [])
        return str(results[0]["id"]) if results else None

    def get_owned_companies(
        self, owner_id: str, max_companies: int = 1000
    ) -> list[dict]:
        """Return companies where `hubspot_owner_id` == owner_id.

        Each item: {"id", "name", "domain", "website", "hubspot_url"}.
        Paginates the CRM search API (100 per page) up to `max_companies`.
        """
        companies: list[dict] = []
        after: Optional[str] = None

        while len(companies) < max_companies:
            body: dict = {
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "hubspot_owner_id",
                        "operator": "EQ",
                        "value": str(owner_id),
                    }]
                }],
                "properties": ["name", "domain", "website"],
                "limit": min(100, max_companies - len(companies)),
            }
            if after:
                body["after"] = after

            resp = self.session.post(
                f"{HUBSPOT_API_BASE}/crm/v3/objects/companies/search",
                json=body,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise HubSpotError(
                    f"POST /crm/v3/objects/companies/search failed "
                    f"({resp.status_code}): {resp.text[:300]}"
                )
            payload = resp.json()

            for record in payload.get("results", []):
                props = record.get("properties", {}) or {}
                name = props.get("name")
                if not name:
                    continue
                company_id = record["id"]
                companies.append({
                    "id": company_id,
                    "name": name,
                    "domain": props.get("domain") or props.get("website") or "",
                    "hubspot_url": self._company_url(company_id),
                })

            after = (payload.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break

        return companies

    def _company_url(self, company_id: str) -> Optional[str]:
        if not self.portal_id:
            return None
        return f"https://app.hubspot.com/contacts/{self.portal_id}/record/0-2/{company_id}"
