"""Airspace hazard MCP server — aviation hazard advisory query.

Can be run as standalone MCP server:
    python -m mcp_servers.notam_server

Tool function is also importable directly for agent dispatch.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastmcp import FastMCP

mcp = FastMCP("liftoff-airspace")

_AW_SIGMET_URL = "https://aviationweather.gov/api/data/sigmet"
_AW_GAIRMET_URL = "https://aviationweather.gov/api/data/gairmet"

# FAA NOTAM API endpoints
_FAA_TOKEN_URL = "https://login.faa.gov/oauth/token"
_FAA_NOTAM_URL = "https://external-api.faa.gov/notamapi/v1/notams"

# Keywords that flag a NOTAM as balloon-relevant (matched case-insensitively)
_KEYWORDS = [
    "BALLOON", "TFR", "RESTRICTED", "PROHIBITED",
    "UAS", "DRONE", "AIRSPACE", "TEMPORARY FLIGHT",
]

# Subset that escalates clearance to MANUAL_CHECK_REQUIRED
_CRITICAL_KEYWORDS = {"TFR", "RESTRICTED", "PROHIBITED"}


async def _call_faa_api(
    client_id: str, client_secret: str,
    lat: float, lon: float, radius_km: float,
) -> list[dict]:
    """Return list of normalised NOTAM dicts from FAA API.

    Raises httpx.HTTPError on any network or HTTP failure.
    Each returned dict: {"id": str, "text": str, "source": "faa"}
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            _FAA_TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        resp = await client.get(
            _FAA_NOTAM_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "locationLatitude":  lat,
                "locationLongitude": lon,
                "locationRadius":    radius_km,
                "notamType":         "DOMESTIC",
            },
        )
        resp.raise_for_status()

        result = []
        for item in resp.json().get("items", []):
            props    = item.get("properties", item)
            core     = props.get("coreNOTAMData", {}).get("notam", {})
            notam_id = core.get("id") or props.get("notamNumber") or str(abs(hash(str(item))))[:8]
            text     = core.get("icaoMessage") or props.get("icaoMessage") or str(item)
            result.append({"id": notam_id, "text": text, "source": "faa"})
        return result


async def _call_sigmet() -> list[dict]:
    """Return normalized SIGMET records from AviationWeather."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_AW_SIGMET_URL, params={"format": "json"})
        resp.raise_for_status()

    raw = resp.json()
    items = raw if isinstance(raw, list) else raw.get("data", [])
    result = []
    for item in items:
        result.append({
            "id": item.get("id") or item.get("airsigmetId") or str(abs(hash(str(item))))[:8],
            "text": item.get("rawText") or item.get("hazard") or str(item),
            "source": "aviationweather_sigmet",
            "raw": item,
        })
    return result


async def _call_gairmet() -> list[dict]:
    """Return normalized G-AIRMET records from AviationWeather."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_AW_GAIRMET_URL, params={"format": "json"})
        resp.raise_for_status()

    raw = resp.json()
    items = raw if isinstance(raw, list) else raw.get("data", [])
    result = []
    for item in items:
        result.append({
            "id": item.get("id") or item.get("airmetId") or str(abs(hash(str(item))))[:8],
            "text": item.get("rawText") or item.get("hazard") or str(item),
            "source": "aviationweather_gairmet",
            "raw": item,
        })
    return result


def _deduplicate(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = item["id"].upper()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _determine_hazard_status(hazards: list[dict], sources_queried: list[str]) -> str:
    if not sources_queried:
        return "MANUAL_CHECK_REQUIRED"
    if hazards:
        return "REVIEW_REQUIRED"
    return "NO_MAJOR_HAZARDS"


@mcp.tool()
async def check_airspace_hazards(
    latitude: float,
    longitude: float,
    radius_km: float = 25.0,
    launch_datetime: str = "",
) -> dict[str, Any]:
    """Check live aviation hazard products for a balloon launch area.

    This is not an official NOTAM clearance tool.
    Manual NOTAM/TFR verification is still required before launch.
    """
    sources_queried: list[str] = []
    hazards: list[dict] = []

    try:
        sigmets = await _call_sigmet()
        hazards.extend(sigmets)
        sources_queried.append("aviationweather_sigmet")
    except httpx.HTTPError:
        pass

    try:
        gairmets = await _call_gairmet()
        hazards.extend(gairmets)
        sources_queried.append("aviationweather_gairmet")
    except httpx.HTTPError:
        pass

    merged = _deduplicate(hazards)

    return {
        "hazard_status": _determine_hazard_status(merged, sources_queried),
        "total_hazards": len(merged),
        "hazards": merged,
        "sources_queried": sources_queried,
        "manual_notam_check_required": True,
        "observation_links": {
            "faa_notam_search": "https://notams.aim.faa.gov/notamSearch/",
            "aviationweather_sigmet": "https://aviationweather.gov/",
            "aviationweather_gairmet": "https://aviationweather.gov/",
        },
        "summary": (
            "Live aviation hazard products were checked. "
            "This does not replace official NOTAM/TFR review."
        ),
    }


if __name__ == "__main__":
    mcp.run()
