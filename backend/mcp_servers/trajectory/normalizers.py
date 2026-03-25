# backend/mcp_servers/trajectory/normalizers.py
"""Pure conversion and transformation helpers — no I/O, fully unit-testable."""
from __future__ import annotations

from .models import (
    BurstLandingPoint,
    PredictionSummary,
    StandardProfileRequest,
    TrajectoryPoint,
)


def lon_to_tawhiri(lon: float) -> float:
    """Convert longitude from -180..180 to Tawhiri's 0..360 range."""
    return lon % 360


def lon_from_tawhiri(lon: float) -> float:
    """Convert longitude from Tawhiri's 0..360 back to -180..180."""
    return ((lon + 180) % 360) - 180


def to_tawhiri_params(req: StandardProfileRequest) -> dict:
    """Build the Tawhiri /api/v1/ query parameter dict from a validated request."""
    return {
        "launch_latitude": req.launch_latitude,
        "launch_longitude": lon_to_tawhiri(req.launch_longitude),
        "launch_datetime": req.launch_datetime,
        "launch_altitude": req.launch_altitude,
        "ascent_rate": req.ascent_rate,
        "burst_altitude": req.burst_altitude,
        "descent_rate": req.descent_rate,
        "profile": "standard_profile",
        "dataset": "GFS",
    }


def flatten_path(prediction: list[dict]) -> list[TrajectoryPoint]:
    """Flatten Tawhiri's staged trajectory into a single ordered list.

    Tawhiri returns a list of stage dicts:
      [{"stage": "ascent", "trajectory": [{...}, ...]}, {"stage": "descent", ...}]

    Each trajectory point has: latitude, longitude (0..360), altitude, datetime.
    Longitudes are converted back to -180..180.
    """
    points: list[TrajectoryPoint] = []
    for stage_dict in prediction:
        stage_name: str = stage_dict.get("stage", "ascent")
        for pt in stage_dict.get("trajectory", []):
            points.append(
                TrajectoryPoint(
                    datetime=pt["datetime"],
                    lat=pt["latitude"],
                    lon=lon_from_tawhiri(pt["longitude"]),
                    alt=pt["altitude"],
                    stage=stage_name,
                )
            )
    return points


def extract_summary(path: list[TrajectoryPoint], water_landing: bool) -> PredictionSummary:
    """Derive a human-readable summary from the flattened trajectory path.

    - launch_time  → first point
    - burst_point  → last ascent point
    - landing_point → last descent point
    """
    ascent_points = [p for p in path if p.stage == "ascent"]
    descent_points = [p for p in path if p.stage == "descent"]
    burst = ascent_points[-1]
    landing = descent_points[-1]
    return PredictionSummary(
        launch_time=path[0].datetime,
        burst_time=burst.datetime,
        landing_time=landing.datetime,
        burst_point=BurstLandingPoint(
            lat=burst.lat, lon=burst.lon, alt=burst.alt, datetime=burst.datetime
        ),
        landing_point=BurstLandingPoint(
            lat=landing.lat, lon=landing.lon, alt=landing.alt, datetime=landing.datetime
        ),
        water_landing=water_landing,
    )
