
import httpx
import structlog
from src.core.settings import settings

log = structlog.get_logger()
NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"


async def get_cve_details(cve_id: str) -> dict:
    """
    Fetches full CVE details from NVD for CVSS >= 7.0 findings.
    Rate limited: 50 req/30s with API key (5 req/30s without).
    Only call this for high/critical severity — not for every CVE found.
    """
    if not cve_id or not cve_id.startswith("CVE-"):
        return {"summary": "No details available", "cwe_id": None, "fixed_version": None}

    headers = {}
    if settings.nvd_api_key:
        headers["apiKey"] = settings.nvd_api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                NVD_BASE,
                params={"cveId": cve_id},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        vulns = data.get("vulnerabilities", [])
        if not vulns:
            return {"summary": f"{cve_id} details not found", "cwe_id": None, "fixed_version": None}

        cve = vulns[0]["cve"]
        description = next(
            (d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"),
            "No description available",
        )
        cwe = next(
            (w["value"] for w in cve.get("weaknesses", [{}])[0].get("description", [])
             if w.get("lang") == "en"),
            None,
        )
        return {
            "summary": description[:500],
            "cwe_id": cwe,
            "fixed_version": None,  # NVD does not reliably provide fixed versions
        }

    except Exception as e:
        log.warning("NVD API error", cve_id=cve_id, error=str(e))
        return {"summary": f"Could not fetch details for {cve_id}", "cwe_id": None, "fixed_version": None}