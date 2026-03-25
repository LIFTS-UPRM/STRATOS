# backend/mcp_servers/trajectory/models.py
"""Pydantic models for trajectory MCP request/response."""
from __future__ import annotations

from pydantic import BaseModel


class StandardProfileRequest(BaseModel):
    """Validated input for a standard balloon trajectory prediction."""

    launch_latitude: float
    launch_longitude: float
    launch_datetime: str
    launch_altitude: float = 0.0
    ascent_rate: float
    burst_altitude: float
    descent_rate: float


class TrajectoryPoint(BaseModel):
    """Single point on the flattened trajectory path."""

    datetime: str
    lat: float
    lon: float   # always -180..180 (converted from Tawhiri's 0..360)
    alt: float
    stage: str   # "ascent" | "descent"


class BurstLandingPoint(BaseModel):
    """Key event point (burst or landing) extracted from the trajectory."""

    lat: float
    lon: float
    alt: float
    datetime: str


class PredictionSummary(BaseModel):
    """High-level summary derived from the full trajectory path."""

    launch_time: str
    burst_time: str
    landing_time: str
    burst_point: BurstLandingPoint
    landing_point: BurstLandingPoint
    water_landing: bool


class PredictionResult(BaseModel):
    """Top-level response returned by predict_standard."""

    ok: bool
    profile: str
    request: dict
    summary: PredictionSummary
    path: list[TrajectoryPoint]
    raw: dict
