"""NOTAM Checker MCP server — dual-source airspace advisory query.

Can be run as standalone MCP server:
    python -m mcp_servers.notam_server

Tool function is also importable directly for agent dispatch.
"""
from __future__ import annotations

import math
from typing import Any

import httpx
from fastmcp import FastMCP

mcp = FastMCP("liftoff-notam")

_FAA_TOKEN_URL = "https://external-api.faa.gov/notamapi/v1/oauth/token"
_FAA_NOTAM_URL = "https://external-api.faa.gov/notamapi/v1/notams"
_AW_NOTAM_URL  = "https://aviationweather.gov/api/data/notam"

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


async def _call_aviationweather(
    lat: float, lon: float, radius_km: float,
) -> list[dict]:
    """Return list of normalised NOTAM dicts from AviationWeather.gov.

    Raises httpx.HTTPError on any network or HTTP failure.
    Each returned dict: {"id": str, "text": str, "source": "aviationweather"}
    """
    delta_lat = radius_km / 111.32
    delta_lon = radius_km / (111.32 * math.cos(math.radians(lat)))
    bbox = f"{lat - delta_lat},{lon - delta_lon},{lat + delta_lat},{lon + delta_lon}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_AW_NOTAM_URL, params={"format": "json", "bbox": bbox})
        resp.raise_for_status()

    raw   = resp.json()
    items = raw if isinstance(raw, list) else raw.get("notams", [])
    result = []
    for item in items:
        if isinstance(item, str):
            result.append({
                "id":     str(abs(hash(item)))[:8],
                "text":   item,
                "source": "aviationweather",
            })
        else:
            notam_id = item.get("notamNumber") or item.get("id") or str(abs(hash(str(item))))[:8]
            text     = item.get("icaoMessage") or item.get("text") or str(item)
            result.append({"id": notam_id, "text": text, "source": "aviationweather"})
    return result


def _scan_keywords(text: str) -> list[str]:
    upper = text.upper()
    return [kw for kw in _KEYWORDS if kw in upper]


def _deduplicate(notams: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for n in notams:
        key = n["id"].upper()
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result


def _determine_clearance(relevant: list[dict]) -> str:
    if not relevant:
        return "NO_CRITICAL_ALERTS"
    for n in relevant:
        if set(n.get("keywords_matched", [])) & _CRITICAL_KEYWORDS:
            return "MANUAL_CHECK_REQUIRED"
    return "REVIEW_REQUIRED"


@mcp.tool()
async def check_notam_airspace(
    latitude: float,
    longitude: float,
    radius_km: float = 25.0,
    launch_datetime: str = "",
    faa_client_id: str = "",
    faa_client_secret: str = "",
) -> dict[str, Any]:
    """Check NOTAMs for balloon launch airspace using FAA + AviationWeather.gov.

    Args:
        latitude: Launch site latitude (-90 to 90).
        longitude: Launch site longitude (-180 to 180).
        radius_km: Search radius in km (default 25).
        launch_datetime: ISO 8601 launch datetime (informational).
        faa_client_id: FAA API client ID (from config, optional).
        faa_client_secret: FAA API client secret (from config, optional).

    Returns:
        Dict with total_notams, relevant_notams, clearance_status,
        sources_queried, observation_links.
    """
    sources_queried: list[str] = []
    all_notams: list[dict] = []

    # ── FAA source ────────────────────────────────────────────────────────────
    if faa_client_id and faa_client_secret:
        try:
            faa_notams = await _call_faa_api(
                faa_client_id, faa_client_secret, latitude, longitude, radius_km,
            )
            all_notams.extend(faa_notams)
            sources_queried.append("faa")
        except httpx.HTTPError:
            pass  # Degrade gracefully

    # ── AviationWeather.gov source ────────────────────────────────────────────
    try:
        aw_notams = await _call_aviationweather(latitude, longitude, radius_km)
        all_notams.extend(aw_notams)
        sources_queried.append("aviationweather")
    except httpx.HTTPError:
        pass

    # ── Merge, deduplicate, filter ────────────────────────────────────────────
    merged   = _deduplicate(all_notams)
    relevant = []
    for n in merged:
        matched = _scan_keywords(n["text"])
        if matched:
            relevant.append({**n, "keywords_matched": matched})

    return {
        "total_notams":     len(merged),
        "relevant_notams":  relevant,
        "clearance_status": _determine_clearance(relevant),
        "sources_queried":  sources_queried,
        "observation_links": {
            "faa_notam_search": "https://notams.aim.faa.gov/notamSearch/",
            "aviationweather":  "https://aviationweather.gov/notam",
        },
    }


if __name__ == "__main__":
    mcp.run()
