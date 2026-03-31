#!/usr/bin/env python3
"""
ASTRA Simulator MCP Server

Exposes the ASTRA high-altitude balloon flight simulator as an MCP server,
allowing LLMs to run flight predictions, query hardware databases, and
calculate balloon physics via tool calls.

University of Southampton ASTRA Simulator — MCP wrapper.
"""

import json
import hashlib
import os
import pickle
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict, create_model
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities import func_metadata as _fastmcp_func_metadata

# ASTRA imports
from astra.available_balloons_parachutes import balloons, parachutes
from astra.flight_tools import (
    liftingGasMass,
    nozzleLiftFixedAscent,
    MIXEDGAS_MOLECULAR_MASS,
)

# Lazy import for simulation (downloads GFS data, expensive)
# imported inside the tool to avoid startup delay


def _patch_fastmcp_for_pydantic_v2() -> None:
    """Patch FastMCP's output wrapper helper for Pydantic v2 compatibility."""
    try:
        create_model("_FastMCPCompatProbe", result=str)
        return
    except Exception:
        pass

    def _create_wrapped_model_compat(func_name: str, annotation: Any) -> type[BaseModel]:
        model_name = f"{func_name}Output"
        field_type = type(None) if annotation is None else annotation
        return create_model(model_name, result=(field_type, ...))

    _fastmcp_func_metadata._create_wrapped_model = _create_wrapped_model_compat


_patch_fastmcp_for_pydantic_v2()
mcp = FastMCP("astra_mcp")

# ── Constants ──────────────────────────────────────────────────────────────────
# Standard sea-level atmospheric conditions used for pre-flight calculations
STD_TEMP_C = 15.0         # ISA sea-level temperature (°C)
STD_PRESS_MBAR = 1013.25  # ISA sea-level pressure (mbar)
STD_CD = 0.47             # Representative balloon drag coefficient (sphere approx)
STD_EXCESS_PRESSURE = 1.0 # Excess pressure coefficient

VALID_GAS_TYPES = ("Helium", "Hydrogen")
GFS_CACHE_ROOT = Path(__file__).resolve().parent / ".cache" / "gfs"


# ── Input models ───────────────────────────────────────────────────────────────

class ListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: str = Field(
        default="markdown",
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable",
    )

    @field_validator("response_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in ("markdown", "json"):
            raise ValueError("response_format must be 'markdown' or 'json'")
        return v


class NozzleLiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    balloon_model: str = Field(
        ...,
        description="Balloon model name (e.g. 'TA800', 'HW1000'). Use astra_list_balloons to see options.",
    )
    gas_type: str = Field(
        ...,
        description="Lifting gas type: 'Helium' or 'Hydrogen'",
    )
    payload_weight_kg: float = Field(
        ...,
        description="Total payload train weight in kilograms (everything below balloon)",
        gt=0.0,
        le=50.0,
    )
    ascent_rate_ms: float = Field(
        default=5.0,
        description="Target ascent rate in metres per second (typical range 3–7 m/s)",
        gt=0.0,
        le=20.0,
    )

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon(cls, v: str) -> str:
        if v not in balloons:
            raise ValueError(
                f"Unknown balloon model '{v}'. Call astra_list_balloons to see valid options."
            )
        return v

    @field_validator("gas_type")
    @classmethod
    def validate_gas(cls, v: str) -> str:
        if v not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return v


class BalloonVolumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    balloon_model: str = Field(
        ...,
        description="Balloon model name (e.g. 'TA800'). Use astra_list_balloons to see options.",
    )
    gas_type: str = Field(
        ...,
        description="Lifting gas type: 'Helium' or 'Hydrogen'",
    )
    nozzle_lift_kg: float = Field(
        ...,
        description="Nozzle lift in kilograms. Use astra_calculate_nozzle_lift to determine this.",
        gt=0.0,
        le=100.0,
    )
    payload_weight_kg: float = Field(
        ...,
        description="Total payload train weight in kilograms",
        gt=0.0,
        le=50.0,
    )

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon(cls, v: str) -> str:
        if v not in balloons:
            raise ValueError(
                f"Unknown balloon model '{v}'. Call astra_list_balloons to see valid options."
            )
        return v

    @field_validator("gas_type")
    @classmethod
    def validate_gas(cls, v: str) -> str:
        if v not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return v


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    launch_lat: float = Field(
        ...,
        description="Launch site latitude in decimal degrees (e.g. 51.5074 for London)",
        ge=-90.0,
        le=90.0,
    )
    launch_lon: float = Field(
        ...,
        description="Launch site longitude in decimal degrees (e.g. -0.1278 for London)",
        ge=-180.0,
        le=180.0,
    )
    launch_elevation_m: float = Field(
        ...,
        description="Launch site elevation above mean sea level in metres",
        ge=0.0,
        le=5000.0,
    )
    launch_datetime: str = Field(
        ...,
        description=(
            "Launch date and time in ISO 8601 format: 'YYYY-MM-DDTHH:MM:SS' "
            "(UTC). Must be within ~7 days of now for GFS forecast availability. "
            "Example: '2026-04-01T12:00:00'"
        ),
    )
    balloon_model: str = Field(
        ...,
        description="Balloon model name. Use astra_list_balloons to see options.",
    )
    gas_type: str = Field(
        ...,
        description="Lifting gas type: 'Helium' or 'Hydrogen'",
    )
    nozzle_lift_kg: float = Field(
        ...,
        description=(
            "Nozzle lift in kilograms. Use astra_calculate_nozzle_lift for "
            "a target ascent rate, or astra_calculate_balloon_volume for volume."
        ),
        gt=0.0,
        le=100.0,
    )
    payload_weight_kg: float = Field(
        ...,
        description="Total payload train weight in kilograms (everything below balloon)",
        gt=0.0,
        le=50.0,
    )
    parachute_model: Optional[str] = Field(
        default=None,
        description="Parachute model name (optional). Use astra_list_parachutes to see options.",
    )
    num_runs: int = Field(
        default=5,
        description="Number of Monte Carlo simulation runs. More runs = better statistics. Range 1–20.",
        ge=1,
        le=20,
    )
    floating_flight: bool = Field(
        default=False,
        description="Set True if the balloon vents gas to float at a target altitude instead of bursting.",
    )
    floating_altitude_m: Optional[float] = Field(
        default=None,
        description="Target floating altitude in metres. Required when floating_flight=True.",
        gt=0.0,
        le=50000.0,
    )
    cutdown: bool = Field(
        default=False,
        description="Set True to trigger forced descent at a specific altitude or time.",
    )
    cutdown_altitude_m: Optional[float] = Field(
        default=None,
        description="Altitude in metres to trigger cutdown. Used when cutdown=True.",
        gt=0.0,
        le=50000.0,
    )
    force_low_res: bool = Field(
        default=False,
        description=(
            "Use 1°×1° GFS resolution instead of the default high-res (0.25°×0.25°). "
            "Faster download but less accurate wind data."
        ),
    )

    @field_validator("balloon_model")
    @classmethod
    def validate_balloon(cls, v: str) -> str:
        if v not in balloons:
            raise ValueError(
                f"Unknown balloon model '{v}'. Call astra_list_balloons to see valid options."
            )
        return v

    @field_validator("gas_type")
    @classmethod
    def validate_gas(cls, v: str) -> str:
        if v not in VALID_GAS_TYPES:
            raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}")
        return v

    @field_validator("parachute_model")
    @classmethod
    def validate_parachute(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in parachutes:
            raise ValueError(
                f"Unknown parachute model '{v}'. Call astra_list_parachutes to see valid options."
            )
        return v

    @field_validator("launch_datetime")
    @classmethod
    def validate_datetime(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                "launch_datetime must be ISO 8601 format: 'YYYY-MM-DDTHH:MM:SS'"
            )
        return v


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _format_balloon_row_md(name: str, spec: tuple) -> str:
    mass_g, burst_d, weibull_l, weibull_k = spec
    return (
        f"- **{name}**: mass={mass_g*1000:.0f}g, "
        f"burst_diameter={burst_d:.1f}m, "
        f"Weibull λ={weibull_l:.4f} k={weibull_k:.4f}"
    )


def _latest_gfs_cycle_datetime(simulation_dt: datetime) -> datetime:
    """Mirror ASTRA's idea of the newest candidate GFS cycle."""
    current_dt = datetime.now()
    if simulation_dt < current_dt:
        current_dt = simulation_dt
    return current_dt.replace(hour=(current_dt.hour // 6) * 6,
                              minute=0, second=0, microsecond=0)


def _forecast_cache_key(
    *,
    launch_lat: float,
    launch_lon: float,
    launch_datetime: datetime,
    force_low_res: bool,
    forecast_duration_h: float,
) -> str:
    key_payload = {
        "launch_lat": round(launch_lat, 6),
        "launch_lon": round(launch_lon, 6),
        "launch_datetime": launch_datetime.isoformat(),
        "force_low_res": force_low_res,
        "forecast_duration_h": forecast_duration_h,
    }
    key_json = json.dumps(key_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(key_json.encode("utf-8")).hexdigest()[:24]


def _forecast_cache_paths(
    *,
    launch_lat: float,
    launch_lon: float,
    launch_datetime: datetime,
    force_low_res: bool,
    forecast_duration_h: float,
) -> tuple[Path, Path, Path]:
    cache_key = _forecast_cache_key(
        launch_lat=launch_lat,
        launch_lon=launch_lon,
        launch_datetime=launch_datetime,
        force_low_res=force_low_res,
        forecast_duration_h=forecast_duration_h,
    )
    cache_dir = GFS_CACHE_ROOT / cache_key
    return cache_dir, cache_dir / "metadata.json", cache_dir / "gfs_module.pkl"


def _load_cache_metadata(metadata_path: Path) -> Optional[dict]:
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_cached_gfs_module(module_path: Path):
    with module_path.open("rb") as f:
        return pickle.load(f)


def _save_gfs_cache(
    *,
    cache_dir: Path,
    metadata_path: Path,
    module_path: Path,
    metadata: dict,
    gfs_module,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_meta = metadata_path.with_suffix(".json.tmp")
    temp_module = module_path.with_suffix(".pkl.tmp")
    temp_meta.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    with temp_module.open("wb") as f:
        pickle.dump(gfs_module, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp_meta, metadata_path)
    os.replace(temp_module, module_path)


def _prime_environment_from_gfs_module(environment) -> None:
    """Configure a forecastEnvironment with an already-downloaded GFS module."""
    from astra import global_tools as tools

    if environment.UTC_offset == 0:
        environment.UTC_offset = tools.getUTCOffset(
            environment.launchSiteLat, environment.launchSiteLon, environment.dateAndTime
        )

    environment._UTC_time = environment.dateAndTime - timedelta(
        seconds=environment.UTC_offset * 3600
    )

    pressureInterpolation, temperatureInterpolation, windDirectionInterpolation, windSpeedInterpolation = (
        environment._GFSmodule.interpolateData("press", "temp", "windrct", "windspd")
    )

    environment.getPressure = lambda lat, lon, alt, time: float(
        pressureInterpolation(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getTemperature = lambda lat, lon, alt, time: float(
        temperatureInterpolation(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getWindDirection = lambda lat, lon, alt, time: float(
        windDirectionInterpolation(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getWindSpeed = lambda lat, lon, alt, time: float(
        windSpeedInterpolation(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )

    air_molec_mass = 0.02896
    gas_constant = 8.31447
    standard_temp_rankine = tools.c2kel(15) * (9.0 / 5.0)
    mu0 = 0.01827
    sutherland_const = 120

    environment.getDensity = lambda lat, lon, alt, time: (
        environment.getPressure(lat, lon, alt, time)
        * 100
        * air_molec_mass
        / (gas_constant * tools.c2kel(environment.getTemperature(lat, lon, alt, time)))
    )

    def viscosity(lat, lon, alt, time):
        temp_rankine = tools.c2kel(environment.getTemperature(lat, lon, alt, time)) * (9.0 / 5.0)
        tto = (temp_rankine / standard_temp_rankine) ** 1.5
        tr = ((0.555 * standard_temp_rankine) + sutherland_const) / (
            (0.555 * temp_rankine) + sutherland_const
        )
        return (mu0 * tto * tr) / 1000.0

    environment.getViscosity = viscosity
    environment._weatherLoaded = True


def _load_or_refresh_forecast_cache(environment) -> dict:
    cache_dir, metadata_path, module_path = _forecast_cache_paths(
        launch_lat=environment.launchSiteLat,
        launch_lon=environment.launchSiteLon,
        launch_datetime=environment.dateAndTime,
        force_low_res=environment.forceNonHD,
        forecast_duration_h=environment.forecastDuration,
    )
    latest_cycle = _latest_gfs_cycle_datetime(environment.dateAndTime)
    latest_cycle_iso = latest_cycle.isoformat()
    metadata = _load_cache_metadata(metadata_path)

    if metadata and metadata.get("latest_cycle_utc") == latest_cycle_iso and module_path.exists():
        try:
            cached_module = _load_cached_gfs_module(module_path)
            cached_utc_offset = metadata.get("utc_offset_hours")
            if cached_utc_offset is not None:
                environment.UTC_offset = cached_utc_offset
            environment._GFSmodule = cached_module
            _prime_environment_from_gfs_module(environment)
            return {
                "source": "cache-hit",
                "latest_cycle_utc": latest_cycle_iso,
                "actual_cycle_utc": metadata.get("actual_cycle_utc"),
                "cache_dir": str(cache_dir),
            }
        except Exception:
            metadata = None

    refresh_error = None
    try:
        environment.load()
        refreshed_metadata = {
            "schema_version": 1,
            "generated_at_utc": datetime.utcnow().isoformat(),
            "latest_cycle_utc": latest_cycle_iso,
            "actual_cycle_utc": (
                environment._GFSmodule.cycleDateTime.isoformat()
                if getattr(environment._GFSmodule, "cycleDateTime", None)
                else None
            ),
            "force_low_res": environment.forceNonHD,
            "forecast_duration_h": environment.forecastDuration,
            "launch_lat": environment.launchSiteLat,
            "launch_lon": environment.launchSiteLon,
            "launch_datetime": environment.dateAndTime.isoformat(),
            "utc_offset_hours": environment.UTC_offset,
        }
        cache_write_error = None
        try:
            _save_gfs_cache(
                cache_dir=cache_dir,
                metadata_path=metadata_path,
                module_path=module_path,
                metadata=refreshed_metadata,
                gfs_module=environment._GFSmodule,
            )
        except Exception as exc:
            cache_write_error = f"{type(exc).__name__}: {exc}"
        return {
            "source": "downloaded" if cache_write_error is None else "downloaded-no-cache",
            "latest_cycle_utc": latest_cycle_iso,
            "actual_cycle_utc": refreshed_metadata["actual_cycle_utc"],
            "cache_dir": str(cache_dir),
            "cache_write_error": cache_write_error,
        }
    except Exception as exc:
        refresh_error = exc

    if metadata and module_path.exists():
        cached_module = _load_cached_gfs_module(module_path)
        cached_utc_offset = metadata.get("utc_offset_hours")
        if cached_utc_offset is not None:
            environment.UTC_offset = cached_utc_offset
        environment._GFSmodule = cached_module
        _prime_environment_from_gfs_module(environment)
        return {
            "source": "cache-fallback",
            "latest_cycle_utc": latest_cycle_iso,
            "actual_cycle_utc": metadata.get("actual_cycle_utc"),
            "cache_dir": str(cache_dir),
            "refresh_error": f"{type(refresh_error).__name__}: {refresh_error}",
        }

    raise refresh_error if refresh_error else RuntimeError("Failed to load forecast cache")


def _extract_profile_summary(profile) -> dict:
    """Extract key scalars from a flightProfile object."""
    return {
        "run": int(profile.flightNumber),
        "landing_lat": float(profile.latitudeProfile[-1]),
        "landing_lon": float(profile.longitudeProfile[-1]),
        "landing_alt_m": float(profile.altitudeProfile[-1]),
        "max_altitude_m": float(profile.highestAltitude),
        "flight_duration_s": float(profile.timeVector[-1]),
        "burst": bool(profile.hasBurst),
    }


def _sample_trajectory(profile, max_points: int = 100) -> list:
    """Return a sampled trajectory from a flightProfile (list of dicts)."""
    n = len(profile.timeVector)
    step = max(1, n // max_points)
    return [
        {
            "time_s": float(profile.timeVector[i]),
            "lat": float(profile.latitudeProfile[i]),
            "lon": float(profile.longitudeProfile[i]),
            "alt_m": float(profile.altitudeProfile[i]),
        }
        for i in range(0, n, step)
    ]


def _aggregate_runs(run_summaries: list) -> dict:
    """Compute aggregate statistics across Monte Carlo runs."""
    lats = [r["landing_lat"] for r in run_summaries]
    lons = [r["landing_lon"] for r in run_summaries]
    alts = [r["max_altitude_m"] for r in run_summaries]
    durations = [r["flight_duration_s"] for r in run_summaries]
    return {
        "landing_lat_mean": statistics.mean(lats),
        "landing_lat_min": min(lats),
        "landing_lat_max": max(lats),
        "landing_lon_mean": statistics.mean(lons),
        "landing_lon_min": min(lons),
        "landing_lon_max": max(lons),
        "max_altitude_m_mean": statistics.mean(alts),
        "max_altitude_m_min": min(alts),
        "max_altitude_m_max": max(alts),
        "flight_duration_s_mean": statistics.mean(durations),
        "flight_duration_s_min": min(durations),
        "flight_duration_s_max": max(durations),
        "burst_rate": sum(1 for r in run_summaries if r["burst"]) / len(run_summaries),
    }


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool(
    name="astra_list_balloons",
    annotations={
        "title": "List Available Balloon Models",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def astra_list_balloons(params: ListInput) -> str:
    """List all balloon models available in the ASTRA hardware database.

    Returns every supported balloon model with its physical specifications:
    mass, expected burst diameter, and Weibull distribution parameters used
    for Monte Carlo burst altitude modelling.

    Balloon families:
    - Totex TA series (TA10 – TA3000): named by gram-weight (e.g. TA800 = 800g)
    - Hwoyee HW series (HW10 – HW2000): named by gram-weight

    Args:
        params (ListInput): Validated input with optional response_format.

    Returns:
        str: Either markdown-formatted list or JSON object mapping balloon
             name → {mass_kg, burst_diameter_m, weibull_lambda, weibull_k}.
    """
    if params.response_format == "json":
        result = {
            name: {
                "mass_kg": spec[0],
                "burst_diameter_m": spec[1],
                "weibull_lambda": spec[2],
                "weibull_k": spec[3],
            }
            for name, spec in sorted(balloons.items())
        }
        return json.dumps(result, indent=2)

    lines = ["# Available Balloon Models\n"]
    totex = {k: v for k, v in balloons.items() if k.startswith("TA")}
    hwoyee = {k: v for k, v in balloons.items() if k.startswith("HW")}
    other = {k: v for k, v in balloons.items() if not k.startswith(("TA", "HW"))}

    if totex:
        lines.append("## Totex TA Series")
        lines.extend(_format_balloon_row_md(n, s) for n, s in sorted(totex.items()))
        lines.append("")
    if hwoyee:
        lines.append("## Hwoyee HW Series")
        lines.extend(_format_balloon_row_md(n, s) for n, s in sorted(hwoyee.items()))
        lines.append("")
    if other:
        lines.append("## Other")
        lines.extend(_format_balloon_row_md(n, s) for n, s in sorted(other.items()))
        lines.append("")

    lines.append(f"*{len(balloons)} models total*")
    return "\n".join(lines)


@mcp.tool(
    name="astra_list_parachutes",
    annotations={
        "title": "List Available Parachute Models",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def astra_list_parachutes(params: ListInput) -> str:
    """List all parachute models available in the ASTRA hardware database.

    Returns every supported parachute with its reference area (m²), which
    directly controls descent rate. Larger reference area → slower descent.

    Parachute families:
    - RCK3, RCK4, RCK5: small rocket/balloon chutes
    - SPH36 – SPH100: spherical parachutes (36–100 inch diameter)
    - TX5012, TX160: Totex flat circular chutes

    Args:
        params (ListInput): Validated input with optional response_format.

    Returns:
        str: Either markdown-formatted list or JSON object mapping chute
             name → {reference_area_m2}.
    """
    if params.response_format == "json":
        result = {
            name: {"reference_area_m2": area}
            for name, area in sorted(parachutes.items())
        }
        return json.dumps(result, indent=2)

    lines = ["# Available Parachute Models\n"]
    lines.append("| Model | Reference Area (m²) | Approx. Diameter |")
    lines.append("|-------|--------------------:|-----------------|")
    for name, area in sorted(parachutes.items()):
        import math
        diameter_m = 2.0 * math.sqrt(area / math.pi)
        lines.append(f"| {name} | {area:.4f} | {diameter_m:.2f} m |")
    lines.append(f"\n*{len(parachutes)} models total*")
    return "\n".join(lines)


@mcp.tool(
    name="astra_calculate_nozzle_lift",
    annotations={
        "title": "Calculate Required Nozzle Lift",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def astra_calculate_nozzle_lift(params: NozzleLiftInput) -> str:
    """Calculate the nozzle lift required to achieve a target ascent rate.

    Uses a force-balance approximation (ASTRA first-order model) at standard
    sea-level atmospheric conditions (15°C, 1013.25 mbar). This is a
    pre-flight planning estimate — actual ascent rate will vary with weather.

    Also returns gas mass, balloon volume, and balloon diameter at inflation.

    Args:
        params (NozzleLiftInput): Validated input containing:
            - balloon_model (str): Balloon model name (e.g. 'TA800')
            - gas_type (str): 'Helium' or 'Hydrogen'
            - payload_weight_kg (float): Total payload train weight in kg
            - ascent_rate_ms (float): Target ascent rate in m/s (default 5.0)

    Returns:
        str: JSON string with keys:
            - nozzle_lift_kg (float): Required nozzle lift in kg
            - gas_mass_kg (float): Mass of lifting gas in kg
            - balloon_volume_m3 (float): Balloon volume at inflation (m³)
            - balloon_diameter_m (float): Balloon diameter at inflation (m)
            - balloon_mass_kg (float): Balloon envelope mass (kg)
            - gas_type (str): Gas used
            - balloon_model (str): Balloon model used
            - ascent_rate_ms (float): Target ascent rate

        Error response: "Error: <message>"
    """
    try:
        balloon_spec = balloons[params.balloon_model]
        balloon_mass_kg = balloon_spec[0]
        gas_mol_mass = MIXEDGAS_MOLECULAR_MASS[params.gas_type]

        nozzle_lift = nozzleLiftFixedAscent(
            ascentRate=params.ascent_rate_ms,
            balloonMass=balloon_mass_kg,
            payloadMass=params.payload_weight_kg,
            ambientTempC=STD_TEMP_C,
            ambientPressMbar=STD_PRESS_MBAR,
            gasMolecularMass=gas_mol_mass,
            excessPressureCoefficient=STD_EXCESS_PRESSURE,
            CD=STD_CD,
        )

        gas_mass, volume, diameter = liftingGasMass(
            nozzleLift=nozzle_lift,
            balloonMass=balloon_mass_kg,
            ambientTempC=STD_TEMP_C,
            ambientPressMbar=STD_PRESS_MBAR,
            gasMolecularMass=gas_mol_mass,
            excessPressureCoefficient=STD_EXCESS_PRESSURE,
        )

        result = {
            "nozzle_lift_kg": round(float(nozzle_lift), 4),
            "gas_mass_kg": round(float(gas_mass), 4),
            "balloon_volume_m3": round(float(volume), 4),
            "balloon_diameter_m": round(float(diameter), 4),
            "balloon_mass_kg": round(float(balloon_mass_kg), 4),
            "gas_type": params.gas_type,
            "balloon_model": params.balloon_model,
            "ascent_rate_ms": params.ascent_rate_ms,
            "note": (
                "Calculated at standard sea-level conditions (15°C, 1013.25 mbar). "
                "Actual values will differ with launch site conditions."
            ),
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="astra_calculate_balloon_volume",
    annotations={
        "title": "Calculate Balloon Gas Volume and Diameter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def astra_calculate_balloon_volume(params: BalloonVolumeInput) -> str:
    """Calculate gas mass, balloon volume, and diameter for a given nozzle lift.

    Useful for determining how much gas to fill and what to expect at inflation.
    Uses standard sea-level conditions (15°C, 1013.25 mbar).

    To determine the nozzle lift from a target ascent rate, use
    astra_calculate_nozzle_lift first.

    Args:
        params (BalloonVolumeInput): Validated input containing:
            - balloon_model (str): Balloon model name (e.g. 'TA800')
            - gas_type (str): 'Helium' or 'Hydrogen'
            - nozzle_lift_kg (float): Nozzle lift in kg
            - payload_weight_kg (float): Total payload train weight in kg

    Returns:
        str: JSON string with keys:
            - gas_mass_kg (float): Mass of lifting gas required (kg)
            - balloon_volume_m3 (float): Balloon volume at inflation (m³)
            - balloon_diameter_m (float): Balloon diameter at inflation (m)
            - free_lift_kg (float): Free lift = nozzle_lift - payload - balloon
            - free_lift_fraction (float): Free lift as fraction of payload weight

        Error response: "Error: <message>"
    """
    try:
        balloon_spec = balloons[params.balloon_model]
        balloon_mass_kg = balloon_spec[0]
        gas_mol_mass = MIXEDGAS_MOLECULAR_MASS[params.gas_type]

        gas_mass, volume, diameter = liftingGasMass(
            nozzleLift=params.nozzle_lift_kg,
            balloonMass=balloon_mass_kg,
            ambientTempC=STD_TEMP_C,
            ambientPressMbar=STD_PRESS_MBAR,
            gasMolecularMass=gas_mol_mass,
            excessPressureCoefficient=STD_EXCESS_PRESSURE,
        )

        free_lift = params.nozzle_lift_kg - params.payload_weight_kg - balloon_mass_kg
        free_lift_fraction = free_lift / params.payload_weight_kg if params.payload_weight_kg else 0.0

        result = {
            "gas_mass_kg": round(float(gas_mass), 4),
            "balloon_volume_m3": round(float(volume), 4),
            "balloon_diameter_m": round(float(diameter), 4),
            "free_lift_kg": round(float(free_lift), 4),
            "free_lift_fraction": round(float(free_lift_fraction), 4),
            "balloon_model": params.balloon_model,
            "balloon_mass_kg": round(float(balloon_mass_kg), 4),
            "gas_type": params.gas_type,
            "nozzle_lift_kg": params.nozzle_lift_kg,
            "note": (
                "Calculated at standard sea-level conditions (15°C, 1013.25 mbar). "
                "Actual values will differ with launch site conditions."
            ),
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="astra_run_simulation",
    annotations={
        "title": "Run ASTRA Flight Simulation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def astra_run_simulation(params: SimulationInput) -> str:
    """Run a complete high-altitude balloon flight simulation using GFS weather forecasts.

    Downloads real-time GFS (Global Forecast System) weather data from NOAA,
    then runs Monte Carlo trajectory simulations. Forecast downloads are cached
    on disk and refreshed when a newer NOAA cycle is available. This tool may
    still take 30–90 seconds on a refresh depending on GFS server load and the
    number of simulation runs.

    GFS forecast availability: data is available for roughly ±7 days from now.
    Use force_low_res=True for faster downloads with slightly lower accuracy.

    For a standard burst flight:
        Set floating_flight=False, cutdown=False (defaults).

    For a floating/zero-pressure balloon:
        Set floating_flight=True, floating_altitude_m=<target altitude>.

    For a cutdown flight (forced early descent):
        Set cutdown=True, cutdown_altitude_m=<trigger altitude>.

    Args:
        params (SimulationInput): Validated input containing launch site, timing,
            balloon/parachute hardware specs, and flight mode options.

    Returns:
        str: JSON string with the following schema:

        Success:
        {
            "status": "success",
            "num_runs": int,
            "runs": [
                {
                    "run": int,
                    "landing_lat": float,        # degrees
                    "landing_lon": float,        # degrees
                    "landing_alt_m": float,      # metres ASL
                    "max_altitude_m": float,     # metres ASL
                    "flight_duration_s": float,  # seconds
                    "burst": bool
                },
                ...
            ],
            "aggregate": {
                "landing_lat_mean": float,
                "landing_lat_min": float,
                "landing_lat_max": float,
                "landing_lon_mean": float,
                "landing_lon_min": float,
                "landing_lon_max": float,
                "max_altitude_m_mean": float,
                "max_altitude_m_min": float,
                "max_altitude_m_max": float,
                "flight_duration_s_mean": float,
                "flight_duration_s_min": float,
                "flight_duration_s_max": float,
                "burst_rate": float              # fraction 0.0–1.0
            },
            "trajectory_run1": [
                {"time_s": float, "lat": float, "lon": float, "alt_m": float},
                ...
            ]
        }

        Error:
        "Error: <message>"

    Examples:
        - Standard burst flight from Daytona Beach:
            launch_lat=29.21, launch_lon=-81.02, launch_elevation_m=4,
            launch_datetime='2026-04-01T12:00:00', balloon_model='TA800',
            gas_type='Helium', nozzle_lift_kg=2.0, payload_weight_kg=0.433,
            parachute_model='SPH36', num_runs=10

        - Floating flight at 25km:
            same as above + floating_flight=True, floating_altitude_m=25000
    """
    # Deferred imports to avoid slow startup
    try:
        from astra.simulator import flight, forecastEnvironment
    except ImportError as e:
        return f"Error: Failed to import ASTRA simulator: {e}"

    try:
        launch_dt = datetime.fromisoformat(params.launch_datetime)
    except ValueError as e:
        return f"Error: Invalid launch_datetime: {e}"

    # Build kwargs for floatingFlight / cutdown modes
    flight_kwargs: dict = {}
    if params.floating_flight:
        flight_kwargs["floatingFlight"] = True
        if params.floating_altitude_m is not None:
            flight_kwargs["floatingAltitude"] = params.floating_altitude_m
        else:
            return "Error: floating_altitude_m is required when floating_flight=True"

    if params.cutdown:
        flight_kwargs["cutdown"] = True
        if params.cutdown_altitude_m is not None:
            flight_kwargs["cutdownAltitude"] = params.cutdown_altitude_m
        else:
            return "Error: cutdown_altitude_m is required when cutdown=True"

    try:
        environment = forecastEnvironment(
            launchSiteLat=params.launch_lat,
            launchSiteLon=params.launch_lon,
            launchSiteElev=params.launch_elevation_m,
            dateAndTime=launch_dt,
            forceNonHD=params.force_low_res,
            debugging=False,
        )
    except Exception as e:
        return f"Error creating forecast environment: {type(e).__name__}: {e}"

    try:
        forecast_info = _load_or_refresh_forecast_cache(environment)
    except Exception as e:
        return f"Error loading forecast data: {type(e).__name__}: {e}"

    try:
        sim = flight(
            environment=environment,
            balloonGasType=params.gas_type,
            balloonModel=params.balloon_model,
            nozzleLift=params.nozzle_lift_kg,
            payloadTrainWeight=params.payload_weight_kg,
            parachuteModel=params.parachute_model,
            numberOfSimRuns=params.num_runs,
            debugging=False,
            **flight_kwargs,
        )
        sim.run()
    except Exception as e:
        return f"Error running simulation: {type(e).__name__}: {e}"

    if not sim.results:
        return "Error: Simulation completed but produced no results."

    run_summaries = [_extract_profile_summary(p) for p in sim.results]
    aggregate = _aggregate_runs(run_summaries)
    trajectory = _sample_trajectory(sim.results[0])

    output = {
        "status": "success",
        "num_runs": len(sim.results),
        "forecast": forecast_info,
        "runs": run_summaries,
        "aggregate": aggregate,
        "trajectory_run1": trajectory,
    }
    return json.dumps(output, indent=2)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()  # stdio transport
