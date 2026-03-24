# backend/mcp_servers/trajectory/server.py
"""FastMCP tool registration for the Tawhiri trajectory wrapper."""
from __future__ import annotations

import logging
import os

from fastmcp import FastMCP

from . import services
from .errors import TawhiriError, ValidationError, error_response
from .models import StandardProfileRequest

logger = logging.getLogger(__name__)

mcp = FastMCP("trajectory")


@mcp.tool()
async def predict_standard(
    launch_latitude: float,
    launch_longitude: float,
    launch_datetime: str,
    ascent_rate: float,
    burst_altitude: float,
    descent_rate: float,
    launch_altitude: float = 0.0,
) -> dict:
    """Predict high-altitude balloon trajectory using Tawhiri (NOAA GFS winds).

    Returns a structured result with full path, burst/landing summary,
    water landing flag, and direct raw Tawhiri response.
    """
    req = StandardProfileRequest(
        launch_latitude=launch_latitude,
        launch_longitude=launch_longitude,
        launch_datetime=launch_datetime,
        launch_altitude=launch_altitude,
        ascent_rate=ascent_rate,
        burst_altitude=burst_altitude,
        descent_rate=descent_rate,
    )
    try:
        result = await services.predict_standard(req)
        return result.model_dump()
    except ValidationError as exc:
        return error_response("validation", str(exc))
    except TawhiriError as exc:
        return error_response("upstream", str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in predict_standard")
        return error_response("internal", str(exc))


@mcp.tool()
async def health_check() -> dict:
    """Confirm the Tawhiri wrapper is configured and ready."""
    url = os.environ.get("TAWHIRI_BASE_URL", "")
    configured = bool(url)
    return {
        "ok": configured,
        "tawhiri_url": url or "(not configured)",
        "message": "Tawhiri wrapper ready" if configured else "TAWHIRI_BASE_URL not set",
    }


@mcp.tool()
async def get_supported_profiles() -> dict:
    """Return supported trajectory profiles and their required input fields."""
    return {
        "profiles": [
            {
                "name": "standard_profile",
                "description": "Standard ascent-burst-descent balloon trajectory using NOAA GFS winds",
                "required_fields": [
                    "launch_latitude",
                    "launch_longitude",
                    "launch_datetime",
                    "ascent_rate",
                    "burst_altitude",
                    "descent_rate",
                ],
                "optional_fields": ["launch_altitude"],
            }
        ]
    }


if __name__ == "__main__":
    mcp.run()
