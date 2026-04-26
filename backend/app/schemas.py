from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


McpToolGroupId = Literal["trajectory", "weather", "airspace"]


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any]


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str
    history: list[ChatHistoryMessage] = Field(default_factory=list)
    enabled_tool_groups: list[McpToolGroupId] | None = None


class TrustedConversationState(BaseModel):
    """Server-owned prior tool activity reconstructed from observed execution."""

    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


class TrajectoryArtifactPoint(BaseModel):
    lat: float
    lon: float
    alt_m: float
    time_s: float | None = None


class SondehubRequestSummary(BaseModel):
    profile: str | None = None
    launch_latitude: float | None = None
    launch_longitude: float | None = None
    launch_altitude: float | None = None
    launch_datetime: str | None = None
    ascent_rate: float | None = None
    burst_altitude: float | None = None
    descent_rate: float | None = None


class SondehubTrajectoryReference(BaseModel):
    provider: Literal["sondehub-tawhiri"] = "sondehub-tawhiri"
    status: str
    request: SondehubRequestSummary | None = None
    trajectory: list[TrajectoryArtifactPoint] = Field(default_factory=list)
    burst: TrajectoryArtifactPoint | None = None
    landing: TrajectoryArtifactPoint | None = None


class TrajectoryArtifact(BaseModel):
    launch: TrajectoryArtifactPoint
    mean_trajectory: list[TrajectoryArtifactPoint] = Field(default_factory=list)
    mean_burst: TrajectoryArtifactPoint | None = None
    mean_landing: TrajectoryArtifactPoint | None = None
    landing_uncertainty_sigma_m: float = 0.0
    sondehub_reference: SondehubTrajectoryReference | None = None
    restriction_overlay: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    response: str
    source: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    trajectory_artifact: TrajectoryArtifact | None = None
