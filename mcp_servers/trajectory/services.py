# backend/mcp_servers/trajectory/services.py
"""Business logic: orchestrates validation, Tawhiri call, and response transformation."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .errors import TawhiriError, ValidationError
from .models import PredictionResult, StandardProfileRequest
from .normalizers import extract_summary, flatten_path, to_tawhiri_params
from .tawhiri_client import call_tawhiri

logger = logging.getLogger(__name__)

_OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


def _validate_request(req: StandardProfileRequest) -> None:
    """Raise ValidationError for any invalid field value."""
    if not -90 <= req.launch_latitude <= 90:
        raise ValidationError(
            f"launch_latitude {req.launch_latitude} out of range [-90, 90]"
        )
    if not -180 <= req.launch_longitude <= 180:
        raise ValidationError(
            f"launch_longitude {req.launch_longitude} out of range [-180, 180]"
        )
    if req.ascent_rate <= 0:
        raise ValidationError(f"ascent_rate must be > 0, got {req.ascent_rate}")
    if req.descent_rate <= 0:
        raise ValidationError(f"descent_rate must be > 0, got {req.descent_rate}")
    if req.burst_altitude <= req.launch_altitude:
        raise ValidationError(
            f"burst_altitude ({req.burst_altitude}) must be greater than "
            f"launch_altitude ({req.launch_altitude})"
        )
    try:
        datetime.fromisoformat(req.launch_datetime.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(
            f"launch_datetime '{req.launch_datetime}' is not RFC3339-compatible"
        )


async def _check_water_landing(lat: float, lon: float) -> bool:
    """Return True if the Open-Meteo elevation API reports elevation <= 0 at (lat, lon).

    Defaults to False on any network or parse failure (non-blocking).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _OPEN_METEO_ELEVATION_URL,
                params={"latitude": lat, "longitude": lon},
            )
            resp.raise_for_status()
            data = resp.json()
            elevation = data.get("elevation", [None])[0]
            if elevation is None:
                return False
            return float(elevation) <= 0
    except Exception:
        logger.warning(
            "Water landing check failed for (%s, %s), defaulting to False", lat, lon
        )
        return False


async def predict_standard(req: StandardProfileRequest) -> PredictionResult:
    """Full standard prediction flow.

    1. Validate inputs
    2. Normalize to Tawhiri params
    3. Call Tawhiri
    4. Flatten staged trajectory -> ordered path
    5. Check water landing (non-blocking)
    6. Extract summary
    7. Return PredictionResult

    Raises:
        ValidationError: on invalid input fields.
        TawhiriError: on upstream HTTP failures or malformed response.
    """
    _validate_request(req)

    params = to_tawhiri_params(req)
    raw = await call_tawhiri(params)

    path = flatten_path(raw["prediction"])
    landing = path[-1]
    water_landing = await _check_water_landing(landing.lat, landing.lon)
    summary = extract_summary(path, water_landing)

    return PredictionResult(
        ok=True,
        profile="standard_profile",
        request={
            "launch_latitude": req.launch_latitude,
            "launch_longitude": req.launch_longitude,
            "launch_datetime": req.launch_datetime,
            "launch_altitude": req.launch_altitude,
            "ascent_rate": req.ascent_rate,
            "burst_altitude": req.burst_altitude,
            "descent_rate": req.descent_rate,
        },
        summary=summary,
        path=path,
        raw=raw,
    )
