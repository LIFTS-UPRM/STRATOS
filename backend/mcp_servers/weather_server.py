"""Weather MCP server — Surface weather + Winds aloft.

Can be run as a standalone MCP server:
    python -m mcp_servers.weather_server

Tool functions are also importable directly for agent dispatch.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx
from fastmcp import FastMCP

mcp = FastMCP("liftoff-weather")

_OM_BASE = "https://api.open-meteo.com/v1/forecast"

# ── Launch thresholds (PRD §7.1) ─────────────────────────────────────────────
_WIND_CAUTION   = 7.0    # m/s
_WIND_NO_GO     = 10.0   # m/s
_GUST_NO_GO     = 12.0   # m/s
_CLOUD_CAUTION  = 80     # %
_PRECIP_CAUTION = 30     # %
_CAPE_NO_GO     = 500    # J/kg
_VIS_NO_GO      = 3000   # m

# Pressure levels to fetch for winds aloft (hPa)
_LEVELS = [1000, 925, 850, 700, 500, 400, 300, 250, 200]


def _safe(lst: list, i: int, default: float = 0.0) -> float:
    """Return lst[i] or default when out-of-range or None."""
    v = lst[i] if i < len(lst) else default
    return v if v is not None else default


def _normalise_dt(s: str) -> str:
    """Return 'YYYY-MM-DDTHH:MM' in UTC from any ISO 8601 string."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _obs_links(lat: float, lon: float) -> dict[str, str]:
    return {
        "windy":     f"https://www.windy.com/?{lat},{lon},8",
        "noaa":      f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}",
        "lightning": f"https://www.lightningmaps.org/?lat={lat}&lon={lon}&zoom=8",
    }


async def _call_open_meteo(params: dict) -> dict:
    """Call Open-Meteo; raise httpx.HTTPStatusError on non-2xx."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(_OM_BASE, params=params)
        r.raise_for_status()
        return r.json()


def _assess_hour(
    wind: float, gust: float, cloud: float,
    precip: float, cape: float, vis: float,
) -> str:
    """Return 'NO-GO: <reasons>', 'CAUTION: <reasons>', or 'GO' for one hour."""
    no_go, caution = [], []

    if wind > _WIND_NO_GO:
        no_go.append(f"surface wind {wind:.1f} m/s > {_WIND_NO_GO} m/s")
    elif wind >= _WIND_CAUTION:
        caution.append(f"surface wind {wind:.1f} m/s (threshold {_WIND_CAUTION} m/s)")

    if gust > _GUST_NO_GO:
        no_go.append(f"gusts {gust:.1f} m/s > {_GUST_NO_GO} m/s")

    if cloud > _CLOUD_CAUTION:
        caution.append(f"cloud cover {cloud:.0f}% > {_CLOUD_CAUTION}%")

    if precip > _PRECIP_CAUTION:
        caution.append(f"precip probability {precip:.0f}% > {_PRECIP_CAUTION}%")

    if cape > _CAPE_NO_GO:
        no_go.append(f"CAPE {cape:.0f} J/kg > {_CAPE_NO_GO} J/kg")

    if vis < _VIS_NO_GO:
        no_go.append(f"visibility {vis:.0f} m < {_VIS_NO_GO} m")

    if no_go:
        return "NO-GO: " + "; ".join(no_go)
    if caution:
        return "CAUTION: " + "; ".join(caution)
    return "GO"


@mcp.tool()
async def get_surface_weather(
    latitude: float,
    longitude: float,
    forecast_hours: int = 24,
) -> dict[str, Any]:
    """Fetch surface weather and GO/CAUTION/NO-GO assessment for a launch site.

    Args:
        latitude: Launch site latitude (-90 to 90).
        longitude: Launch site longitude (-180 to 180).
        forecast_hours: Hours ahead to forecast (1-72). Default 24.

    Returns:
        Dict with hourly_conditions, overall_assessment, and observation_links.
    """
    forecast_hours = max(1, min(72, forecast_hours))
    params = {
        "latitude":  latitude,
        "longitude": longitude,
        "hourly":    (
            "temperature_2m,windspeed_10m,windgusts_10m,"
            "cloudcover,precipitation_probability,visibility,cape,weathercode"
        ),
        "wind_speed_unit": "ms",
        "forecast_hours":  forecast_hours,
        "timezone":        "auto",
    }

    try:
        data = await _call_open_meteo(params)
    except httpx.HTTPError as exc:
        return {"error": str(exc), "source": "open-meteo"}

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    winds  = hourly.get("windspeed_10m", [])
    gusts  = hourly.get("windgusts_10m", [])
    clouds = hourly.get("cloudcover", [])
    precip = hourly.get("precipitation_probability", [])
    capes  = hourly.get("cape", [])
    viss   = hourly.get("visibility", [])
    temps  = hourly.get("temperature_2m", [])

    conditions = []
    for i, t in enumerate(times):
        w  = _safe(winds, i)
        g  = _safe(gusts, i)
        c  = _safe(clouds, i)
        p  = _safe(precip, i)
        cp = _safe(capes, i)
        v  = _safe(viss, i, 9999.0)
        conditions.append({
            "time":            t,
            "temperature_c":   temps[i] if i < len(temps) else None,
            "wind_ms":         w,
            "gust_ms":         g,
            "cloud_pct":       c,
            "precip_prob_pct": p,
            "cape_jkg":        cp,
            "visibility_m":    v,
            "assessment":      _assess_hour(w, g, c, p, cp, v),
        })

    no_go_count     = sum(1 for c in conditions if c["assessment"].startswith("NO-GO"))
    caution_count   = sum(1 for c in conditions if c["assessment"].startswith("CAUTION"))
    go_count        = len(conditions) - no_go_count - caution_count
    overall         = "NO-GO" if no_go_count else ("CAUTION" if caution_count else "GO")

    return {
        "location":           {"latitude": latitude, "longitude": longitude},
        "forecast_hours":     forecast_hours,
        "overall_assessment": overall,
        "go_windows":         go_count,
        "caution_windows":    caution_count,
        "no_go_windows":      no_go_count,
        "hourly_conditions":  conditions,
        "data_freshness_ms":  data.get("generationtime_ms"),
        "observation_links":  _obs_links(latitude, longitude),
    }


@mcp.tool()
async def get_winds_aloft(
    latitude: float,
    longitude: float,
    forecast_datetime: str,
) -> dict[str, Any]:
    """Fetch winds aloft profile at 9 pressure levels for a launch site.

    Args:
        latitude: Launch site latitude (-90 to 90).
        longitude: Launch site longitude (-180 to 180).
        forecast_datetime: ISO 8601 datetime (e.g. '2026-03-15T12:00:00Z').

    Returns:
        Dict with wind_profile (9 levels), jet_stream_alert, and observation_links.
    """
    hourly_vars = []
    for lvl in _LEVELS:
        hourly_vars.extend([
            f"windspeed_{lvl}hPa",
            f"winddirection_{lvl}hPa",
            f"geopotential_height_{lvl}hPa",
        ])

    params = {
        "latitude":    latitude,
        "longitude":   longitude,
        "hourly":      ",".join(hourly_vars),
        "wind_speed_unit": "ms",
        "forecast_days": 3,
        "timezone":    "UTC",
    }

    try:
        data = await _call_open_meteo(params)
    except httpx.HTTPError as exc:
        return {"error": str(exc), "source": "open-meteo"}

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])

    # Find the index closest to forecast_datetime
    try:
        target_prefix = _normalise_dt(forecast_datetime)
    except (ValueError, OverflowError) as exc:
        return {"error": f"Invalid forecast_datetime: {exc}", "source": "open-meteo"}

    idx = next((i for i, t in enumerate(times) if t[:16] == target_prefix), None)
    if idx is None:
        return {
            "error": f"forecast_datetime '{forecast_datetime}' not found in 3-day window",
            "available_times": times[:6],
            "source": "open-meteo",
        }

    jet_stream_alert = False
    profile = []
    for lvl in _LEVELS:
        speed_list = hourly.get(f"windspeed_{lvl}hPa") or []
        dir_list   = hourly.get(f"winddirection_{lvl}hPa") or []
        hgt_list   = hourly.get(f"geopotential_height_{lvl}hPa") or []

        speed  = speed_list[idx]  if idx < len(speed_list)  else None
        direc  = dir_list[idx]    if idx < len(dir_list)    else None
        height = hgt_list[idx]    if idx < len(hgt_list)    else None

        s = speed if speed is not None else 0.0
        if s > 40.0:
            jet_stream_alert = True

        u, v = None, None
        if speed is not None and direc is not None:
            rad = math.radians(direc)
            u   = round(-s * math.sin(rad), 2)
            v   = round(-s * math.cos(rad), 2)

        profile.append({
            "pressure_hPa":       lvl,
            "altitude_m":         height,
            "wind_speed_ms":      s,
            "wind_direction_deg": direc,
            "u_ms":               u,
            "v_ms":               v,
        })

    jet_levels = [p["pressure_hPa"] for p in profile if (p["wind_speed_ms"] or 0) > 40]
    jet_msg    = f"Jet stream: {', '.join(str(lvl)+'hPa' for lvl in jet_levels)}" if jet_levels else None

    return {
        "location":           {"latitude": latitude, "longitude": longitude},
        "forecast_time":      times[idx] if idx < len(times) else forecast_datetime,
        "wind_profile":       profile,
        "jet_stream_alert":   jet_stream_alert,
        "jet_stream_message": jet_msg,
        "observation_links":  _obs_links(latitude, longitude),
    }


if __name__ == "__main__":
    mcp.run()
