"""STRATOS MCP wrapper around the vendored HAB_Predictor simulator."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities import func_metadata as _fastmcp_func_metadata
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from vendor.hab_predictor.astra.available_balloons_parachutes import (
    balloons,
    parachutes,
)


def _patch_fastmcp_for_pydantic_v2() -> None:
    try:
        create_model("_FastMCPCompatProbe", result=str)
        return
    except Exception:
        pass

    def _create_wrapped_model_compat(
        func_name: str,
        annotation: Any,
    ) -> type[BaseModel]:
        model_name = f"{func_name}Output"
        field_type = type(None) if annotation is None else annotation
        return create_model(model_name, result=(field_type, ...))

    _fastmcp_func_metadata._create_wrapped_model = _create_wrapped_model_compat


_patch_fastmcp_for_pydantic_v2()
mcp = FastMCP("astra_mcp")
STANDARD_CONDITIONS_NOTE = (
    "Calculated at standard sea-level conditions (15C, 1013.25 mbar). "
    "Actual values will differ with launch site conditions."
)
VALID_GAS_TYPES = ("Helium", "Hydrogen")
_BRIDGE_MODULE = "vendor.hab_predictor.mcp_bridge"


class ListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_format: str = Field(
        default="json",
        description="Output format: json or markdown.",
    )

    @field_validator("response_format")
    @classmethod
    def validate_response_format(cls, value: str) -> str:
        if value not in ("json", "markdown"):
            raise ValueError("response_format must be 'json' or 'markdown'")
        return value


class NozzleLiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    balloon_model: str = Field(..., description="Balloon model name")
    gas_type: str = Field(..., description="Helium or Hydrogen")
    payload_weight_kg: float = Field(..., gt=0.0, le=50.0)
    ascent_rate_ms: float = Field(default=5.0, gt=0.0, le=20.0)

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon_model(cls, value: str) -> str:
        if value not in balloons:
            raise ValueError(
                f"Unknown balloon model '{value}'. Call astra_list_balloons to see valid options."
            )
        return value

    @field_validator("gas_type")
    @classmethod
    def validate_gas_type(cls, value: str) -> str:
        if value not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return value


class BalloonVolumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    balloon_model: str = Field(..., description="Balloon model name")
    gas_type: str = Field(..., description="Helium or Hydrogen")
    nozzle_lift_kg: float = Field(..., gt=0.0, le=100.0)
    payload_weight_kg: float = Field(..., gt=0.0, le=50.0)

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon_model(cls, value: str) -> str:
        if value not in balloons:
            raise ValueError(
                f"Unknown balloon model '{value}'. Call astra_list_balloons to see valid options."
            )
        return value

    @field_validator("gas_type")
    @classmethod
    def validate_gas_type(cls, value: str) -> str:
        if value not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return value


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    launch_lat: float = Field(..., ge=-90.0, le=90.0)
    launch_lon: float = Field(..., ge=-180.0, le=180.0)
    launch_elevation_m: float = Field(..., ge=0.0, le=5000.0)
    launch_datetime: str = Field(
        ...,
        description="ISO 8601 UTC launch datetime.",
    )
    balloon_model: str = Field(..., description="Balloon model name")
    gas_type: str = Field(..., description="Helium or Hydrogen")
    nozzle_lift_kg: float = Field(..., gt=0.0, le=100.0)
    payload_weight_kg: float = Field(..., gt=0.0, le=50.0)
    parachute_model: str | None = Field(default=None)
    num_runs: int = Field(default=5, ge=1, le=20)
    floating_flight: bool = Field(default=False)
    floating_altitude_m: float | None = Field(default=None, gt=0.0, le=50000.0)
    cutdown: bool = Field(default=False)
    cutdown_altitude_m: float | None = Field(default=None, gt=0.0, le=50000.0)
    force_low_res: bool = Field(default=False)

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon_model(cls, value: str) -> str:
        if value not in balloons:
            raise ValueError(
                f"Unknown balloon model '{value}'. Call astra_list_balloons to see valid options."
            )
        return value

    @field_validator("gas_type")
    @classmethod
    def validate_gas_type(cls, value: str) -> str:
        if value not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return value

    @field_validator("parachute_model")
    @classmethod
    def validate_parachute_model(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in parachutes:
            raise ValueError(
                f"Unknown parachute model '{value}'. Call astra_list_parachutes to see valid options."
            )
        return value


async def _run_bridge_tool(tool_name: str, payload: dict[str, Any]) -> str:
    settings = get_settings()
    env = os.environ.copy()
    env["ASTRA_GFS_CACHE_DIR"] = str(
        Path(settings.astra_gfs_cache_dir).expanduser().resolve()
    )

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        _BRIDGE_MODULE,
        "--tool",
        tool_name,
        "--payload",
        json.dumps(payload),
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode("utf-8", errors="replace").strip()
    if process.returncode == 0 and output:
        return output
    error_text = stderr.decode("utf-8", errors="replace").strip()
    return f"Error: RuntimeError: HAB bridge failed ({error_text or 'no output'})"


@mcp.tool(name="astra_list_balloons")
async def astra_list_balloons(response_format: str = "json") -> str:
    try:
        params = ListInput(response_format=response_format)
        return await _run_bridge_tool("astra_list_balloons", params.model_dump())
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(name="astra_list_parachutes")
async def astra_list_parachutes(response_format: str = "json") -> str:
    try:
        params = ListInput(response_format=response_format)
        return await _run_bridge_tool("astra_list_parachutes", params.model_dump())
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(name="astra_calculate_nozzle_lift")
async def astra_calculate_nozzle_lift(
    balloon_model: str,
    gas_type: str,
    payload_weight_kg: float,
    ascent_rate_ms: float = 5.0,
) -> str:
    try:
        params = NozzleLiftInput(
            balloon_model=balloon_model,
            gas_type=gas_type,
            payload_weight_kg=payload_weight_kg,
            ascent_rate_ms=ascent_rate_ms,
        )
        return await _run_bridge_tool(
            "astra_calculate_nozzle_lift",
            params.model_dump(),
        )
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(name="astra_calculate_balloon_volume")
async def astra_calculate_balloon_volume(
    balloon_model: str,
    gas_type: str,
    nozzle_lift_kg: float,
    payload_weight_kg: float,
) -> str:
    try:
        params = BalloonVolumeInput(
            balloon_model=balloon_model,
            gas_type=gas_type,
            nozzle_lift_kg=nozzle_lift_kg,
            payload_weight_kg=payload_weight_kg,
        )
        return await _run_bridge_tool(
            "astra_calculate_balloon_volume",
            params.model_dump(),
        )
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(name="astra_run_simulation")
async def astra_run_simulation(
    launch_lat: float,
    launch_lon: float,
    launch_elevation_m: float,
    launch_datetime: str,
    balloon_model: str,
    gas_type: str,
    nozzle_lift_kg: float,
    payload_weight_kg: float,
    parachute_model: str | None = None,
    num_runs: int = 5,
    floating_flight: bool = False,
    floating_altitude_m: float | None = None,
    cutdown: bool = False,
    cutdown_altitude_m: float | None = None,
    force_low_res: bool = False,
) -> str:
    try:
        params = SimulationInput(
            launch_lat=launch_lat,
            launch_lon=launch_lon,
            launch_elevation_m=launch_elevation_m,
            launch_datetime=launch_datetime,
            balloon_model=balloon_model,
            gas_type=gas_type,
            nozzle_lift_kg=nozzle_lift_kg,
            payload_weight_kg=payload_weight_kg,
            parachute_model=parachute_model,
            num_runs=num_runs,
            floating_flight=floating_flight,
            floating_altitude_m=floating_altitude_m,
            cutdown=cutdown,
            cutdown_altitude_m=cutdown_altitude_m,
            force_low_res=force_low_res,
        )
        return await _run_bridge_tool("astra_run_simulation", params.model_dump())
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    mcp.run()
