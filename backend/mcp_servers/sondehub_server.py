"""SondeHub Tawhiri trajectory tool for STRATOS."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import random
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities import func_metadata as _fastmcp_func_metadata
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model


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
mcp = FastMCP("sondehub_mcp")

SONDEHUB_TAWHIRI_ENDPOINT = os.environ.get(
    "SONDEHUB_TAWHIRI_ENDPOINT",
    os.environ.get(
        "ASTRA_SONDEHUB_TAWHIRI_ENDPOINT",
        "https://api.v2.sondehub.org/tawhiri",
    ),
)
SONDEHUB_TIMEOUT_S = float(os.environ.get("SONDEHUB_TIMEOUT_S", "30"))
MEAN_TRAJECTORY_POINTS = 100
SAMPLED_TRAJECTORY_POINTS = 120
PROFILE_FIELDS = ("ascent_rate_ms", "burst_altitude_m", "descent_rate_ms")
LEGACY_HARDWARE_FIELDS = {
    "balloon_model",
    "balloon",
    "gas_type",
    "gas",
    "payload_weight_kg",
    "payload",
    "nozzle_lift_kg",
    "nozzle_lift",
    "parachute_model",
    "parachute",
}


class SondehubSimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    launch_lat: float = Field(..., ge=-90.0, le=90.0)
    launch_lon: float = Field(..., ge=-180.0, le=180.0)
    launch_elevation_m: float = Field(..., ge=0.0, le=5000.0)
    launch_datetime: str = Field(..., description="ISO 8601 UTC launch datetime.")
    ascent_rate_ms: float = Field(..., gt=0.0, le=20.0)
    burst_altitude_m: float = Field(..., gt=0.0, le=60000.0)
    descent_rate_ms: float = Field(..., gt=0.0, le=100.0)
    num_runs: int = Field(..., ge=1, le=20)
    seed: int | None = Field(default=None)
    ascent_rate_stddev_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    burst_altitude_stddev_m: float = Field(default=1000.0, ge=0.0, le=20000.0)
    descent_rate_stddev_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    launch_time_stddev_min: float = Field(default=10.0, ge=0.0, le=240.0)


def _error_payload(
    error_type: str,
    message: str,
    *,
    missing_fields: list[str] | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "tool": "sondehub_run_simulation",
        "error_type": error_type,
        "message": message,
    }
    if missing_fields:
        payload["missing_fields"] = missing_fields
    if details is not None:
        payload["details"] = details
    return payload


def _normalize_longitude_180(lon: float) -> float:
    return ((float(lon) + 180.0) % 360.0) - 180.0


def _normalize_longitude_360(lon: float) -> float:
    return float(lon) % 360.0


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * earth_radius_km * math.asin(math.sqrt(a))


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _datetime_to_rfc3339_utc(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_point_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _parse_datetime(value)
    except ValueError:
        return None


def _mean_longitude_deg(longitudes: list[float]) -> float:
    if not longitudes:
        return 0.0
    radians = [math.radians(lon) for lon in longitudes]
    mean_sin = statistics.mean(math.sin(lon) for lon in radians)
    mean_cos = statistics.mean(math.cos(lon) for lon in radians)
    if mean_sin == 0.0 and mean_cos == 0.0:
        return _normalize_longitude_180(statistics.mean(longitudes))
    return _normalize_longitude_180(math.degrees(math.atan2(mean_sin, mean_cos)))


def _sample_positive(
    rng: random.Random,
    value: float,
    stddev: float,
    minimum: float,
) -> float:
    if stddev <= 0.0:
        return float(value)
    return max(minimum, float(rng.gauss(value, stddev)))


def _seed_from_params(params: SondehubSimulationInput, launch_dt: datetime) -> int:
    seed_payload = params.model_dump()
    seed_payload["launch_datetime"] = _datetime_to_rfc3339_utc(launch_dt)
    seed_json = json.dumps(seed_payload, sort_keys=True, separators=(",", ":"))
    return int(hashlib.sha256(seed_json.encode("utf-8")).hexdigest()[:16], 16)


def _build_sampled_requests(
    params: SondehubSimulationInput,
    launch_dt: datetime,
) -> tuple[int, list[dict[str, Any]]]:
    seed = params.seed if params.seed is not None else _seed_from_params(params, launch_dt)
    rng = random.Random(seed)
    requests = []

    for run_index in range(params.num_runs):
        ascent_rate = _sample_positive(
            rng,
            params.ascent_rate_ms,
            params.ascent_rate_ms * (params.ascent_rate_stddev_pct / 100.0),
            0.1,
        )
        burst_altitude = _sample_positive(
            rng,
            params.burst_altitude_m,
            params.burst_altitude_stddev_m,
            max(params.launch_elevation_m + 100.0, 100.0),
        )
        descent_rate = _sample_positive(
            rng,
            params.descent_rate_ms,
            params.descent_rate_ms * (params.descent_rate_stddev_pct / 100.0),
            0.1,
        )
        launch_offset_s = (
            rng.gauss(0.0, params.launch_time_stddev_min * 60.0)
            if params.launch_time_stddev_min > 0.0
            else 0.0
        )
        sampled_launch_dt = launch_dt + timedelta(seconds=launch_offset_s)

        requests.append(
            {
                "run": run_index + 1,
                "profile": "standard_profile",
                "launch_latitude": params.launch_lat,
                "launch_longitude": _normalize_longitude_360(params.launch_lon),
                "launch_altitude": params.launch_elevation_m,
                "launch_datetime": _datetime_to_rfc3339_utc(sampled_launch_dt),
                "ascent_rate": ascent_rate,
                "burst_altitude": burst_altitude,
                "descent_rate": descent_rate,
                "launch_offset_s": launch_offset_s,
            }
        )

    return seed, requests


async def _fetch_sondehub_prediction(request_params: dict[str, Any]) -> dict[str, Any]:
    query_params = {
        key: value
        for key, value in request_params.items()
        if key not in {"run", "launch_offset_s"}
    }
    async with httpx.AsyncClient(timeout=SONDEHUB_TIMEOUT_S) as client:
        response = await client.get(SONDEHUB_TAWHIRI_ENDPOINT, params=query_params)

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"SondeHub predictor returned non-JSON output: {response.text}") from exc

    if response.status_code >= 400:
        error = payload.get("error") if isinstance(payload, dict) else None
        description = (
            error.get("description")
            if isinstance(error, dict)
            else response.text
        )
        raise RuntimeError(f"SondeHub predictor error: {description}")
    if isinstance(payload, dict) and payload.get("error"):
        error = payload["error"]
        description = error.get("description", "unknown error") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"SondeHub predictor error: {description}")
    if not isinstance(payload, dict):
        raise RuntimeError("SondeHub predictor returned an unexpected payload.")
    return payload


def _normalize_sondehub_point(
    point: dict[str, Any],
    launch_dt: datetime,
) -> dict[str, float]:
    normalized = {
        "lat": float(point["latitude"]),
        "lon": _normalize_longitude_180(float(point["longitude"])),
        "alt_m": float(point["altitude"]),
    }
    point_dt = _parse_point_datetime(point.get("datetime"))
    if point_dt is not None:
        normalized["time_s"] = max(0.0, (point_dt - launch_dt).total_seconds())
    return normalized


def _sample_trajectory(
    trajectory: list[dict[str, float]],
    max_points: int = SAMPLED_TRAJECTORY_POINTS,
) -> list[dict[str, float]]:
    if len(trajectory) <= max_points:
        return trajectory
    step = max(1, len(trajectory) // max_points)
    sampled = trajectory[::step]
    if sampled[-1] is not trajectory[-1]:
        sampled.append(trajectory[-1])
    return sampled


def _build_run_summary(
    payload: dict[str, Any],
    request_params: dict[str, Any],
) -> dict[str, Any]:
    launch_dt = _parse_datetime(str(request_params["launch_datetime"]))
    stages = {stage.get("stage"): stage for stage in payload.get("prediction") or []}
    ascent_stage = stages.get("ascent") or {}
    descent_stage = stages.get("descent") or {}
    ascent_points = ascent_stage.get("trajectory") or []
    descent_points = descent_stage.get("trajectory") or []
    if not ascent_points or not descent_points:
        raise RuntimeError("SondeHub response did not include ascent and descent trajectories.")

    trajectory = [
        _normalize_sondehub_point(point, launch_dt)
        for point in [*ascent_points, *descent_points]
    ]
    burst = _normalize_sondehub_point(ascent_points[-1], launch_dt)
    landing = _normalize_sondehub_point(descent_points[-1], launch_dt)

    peak_time_s = float(burst.get("time_s", 0.0))
    flight_duration_s = float(landing.get("time_s", 0.0))
    return {
        "run": int(request_params["run"]),
        "request": {
            "profile": "standard_profile",
            "launch_latitude": float(request_params["launch_latitude"]),
            "launch_longitude": float(request_params["launch_longitude"]),
            "launch_altitude": float(request_params["launch_altitude"]),
            "launch_datetime": request_params["launch_datetime"],
            "ascent_rate": float(request_params["ascent_rate"]),
            "burst_altitude": float(request_params["burst_altitude"]),
            "descent_rate": float(request_params["descent_rate"]),
            "launch_offset_s": float(request_params["launch_offset_s"]),
        },
        "landing_lat": landing["lat"],
        "landing_lon": landing["lon"],
        "landing_alt_m": landing["alt_m"],
        "max_altitude_m": burst["alt_m"],
        "peak_lat": burst["lat"],
        "peak_lon": burst["lon"],
        "peak_time_s": peak_time_s,
        "flight_duration_s": flight_duration_s,
        "burst": True,
        "trajectory": _sample_trajectory(trajectory),
    }


def _aggregate_runs(run_summaries: list[dict[str, Any]]) -> dict[str, float]:
    lats = [run["landing_lat"] for run in run_summaries]
    lons = [run["landing_lon"] for run in run_summaries]
    altitudes = [run["max_altitude_m"] for run in run_summaries]
    durations = [run["flight_duration_s"] for run in run_summaries]
    mean_lat = statistics.mean(lats)
    mean_lon = _mean_longitude_deg(lons)
    spread_km = max(
        _great_circle_km(run["landing_lat"], run["landing_lon"], mean_lat, mean_lon)
        for run in run_summaries
    )
    return {
        "landing_lat_mean": float(mean_lat),
        "landing_lat_min": float(min(lats)),
        "landing_lat_max": float(max(lats)),
        "landing_lon_mean": float(mean_lon),
        "landing_lon_min": float(min(lons)),
        "landing_lon_max": float(max(lons)),
        "max_altitude_m_mean": float(statistics.mean(altitudes)),
        "max_altitude_m_min": float(min(altitudes)),
        "max_altitude_m_max": float(max(altitudes)),
        "flight_duration_s_mean": float(statistics.mean(durations)),
        "flight_duration_s_min": float(min(durations)),
        "flight_duration_s_max": float(max(durations)),
        "burst_rate": 1.0,
        "landing_spread_km": float(spread_km),
    }


def _mean_location(
    run_summaries: list[dict[str, Any]],
    *,
    lat_key: str,
    lon_key: str,
    alt_key: str,
    time_key: str | None = None,
) -> dict[str, float]:
    point = {
        "lat": float(statistics.mean(run[lat_key] for run in run_summaries)),
        "lon": float(_mean_longitude_deg([run[lon_key] for run in run_summaries])),
        "alt_m": float(statistics.mean(run[alt_key] for run in run_summaries)),
    }
    if time_key is not None:
        point["time_s"] = float(statistics.mean(run[time_key] for run in run_summaries))
    return point


def _point_at_fraction(
    trajectory: list[dict[str, float]],
    fraction: float,
) -> dict[str, float]:
    if len(trajectory) == 1:
        return trajectory[0]
    raw_index = fraction * (len(trajectory) - 1)
    lower = int(math.floor(raw_index))
    upper = min(lower + 1, len(trajectory) - 1)
    weight = raw_index - lower
    if lower == upper:
        return trajectory[lower]

    start = trajectory[lower]
    end = trajectory[upper]
    lon_delta = _normalize_longitude_180(end["lon"] - start["lon"])
    point = {
        "lat": start["lat"] + (end["lat"] - start["lat"]) * weight,
        "lon": _normalize_longitude_180(start["lon"] + lon_delta * weight),
        "alt_m": start["alt_m"] + (end["alt_m"] - start["alt_m"]) * weight,
    }
    if start.get("time_s") is not None and end.get("time_s") is not None:
        point["time_s"] = start["time_s"] + (end["time_s"] - start["time_s"]) * weight
    return point


def _build_mean_trajectory(run_summaries: list[dict[str, Any]]) -> list[dict[str, float]]:
    trajectories = [run["trajectory"] for run in run_summaries if run.get("trajectory")]
    if not trajectories:
        return []

    sample_count = min(
        MEAN_TRAJECTORY_POINTS,
        max(len(trajectory) for trajectory in trajectories),
    )
    if sample_count <= 1:
        sample_count = 1

    mean_trajectory = []
    for index in range(sample_count):
        fraction = 0.0 if sample_count == 1 else index / float(sample_count - 1)
        samples = [_point_at_fraction(trajectory, fraction) for trajectory in trajectories]
        point = {
            "lat": float(statistics.mean(sample["lat"] for sample in samples)),
            "lon": float(_mean_longitude_deg([sample["lon"] for sample in samples])),
            "alt_m": float(statistics.mean(sample["alt_m"] for sample in samples)),
        }
        time_samples = [sample["time_s"] for sample in samples if sample.get("time_s") is not None]
        if time_samples:
            point["time_s"] = float(statistics.mean(time_samples))
        mean_trajectory.append(point)
    return mean_trajectory


def _landing_uncertainty_sigma_m(
    run_summaries: list[dict[str, Any]],
    mean_landing: dict[str, float],
) -> float:
    squared_distances = [
        (
            _great_circle_km(
                run["landing_lat"],
                run["landing_lon"],
                mean_landing["lat"],
                mean_landing["lon"],
            )
            * 1000.0
        )
        ** 2
        for run in run_summaries
    ]
    return float(math.sqrt(statistics.mean(squared_distances))) if squared_distances else 0.0


async def _run_simulation(params: SondehubSimulationInput) -> dict[str, Any]:
    launch_dt = _parse_datetime(params.launch_datetime)
    launch_datetime = _datetime_to_rfc3339_utc(launch_dt)
    seed, sampled_requests = _build_sampled_requests(params, launch_dt)
    responses = await asyncio.gather(
        *[_fetch_sondehub_prediction(request_params) for request_params in sampled_requests]
    )
    run_summaries = [
        _build_run_summary(response, request_params)
        for response, request_params in zip(responses, sampled_requests)
    ]

    aggregate = _aggregate_runs(run_summaries)
    mean_burst = _mean_location(
        run_summaries,
        lat_key="peak_lat",
        lon_key="peak_lon",
        alt_key="max_altitude_m",
        time_key="peak_time_s",
    )
    mean_landing = _mean_location(
        run_summaries,
        lat_key="landing_lat",
        lon_key="landing_lon",
        alt_key="landing_alt_m",
        time_key="flight_duration_s",
    )
    mean_trajectory = _build_mean_trajectory(run_summaries)

    return {
        "status": "success",
        "source": "sondehub-tawhiri",
        "launch": {
            "lat": params.launch_lat,
            "lon": params.launch_lon,
            "elevation_m": params.launch_elevation_m,
            "datetime": launch_datetime,
        },
        "config": {
            "profile": "standard_profile",
            "ascent_rate_ms": params.ascent_rate_ms,
            "burst_altitude_m": params.burst_altitude_m,
            "descent_rate_ms": params.descent_rate_ms,
            "num_runs": params.num_runs,
            "seed": seed,
            "ascent_rate_stddev_pct": params.ascent_rate_stddev_pct,
            "burst_altitude_stddev_m": params.burst_altitude_stddev_m,
            "descent_rate_stddev_pct": params.descent_rate_stddev_pct,
            "launch_time_stddev_min": params.launch_time_stddev_min,
        },
        "forecast": {
            "source": "sondehub-tawhiri",
            "endpoint": SONDEHUB_TAWHIRI_ENDPOINT,
        },
        "num_runs": len(run_summaries),
        "runs": [
            {key: value for key, value in run.items() if key != "trajectory"}
            for run in run_summaries
        ],
        "aggregate": aggregate,
        "trajectory_run1": run_summaries[0]["trajectory"],
        "trajectory_artifact": {
            "launch": {
                "lat": params.launch_lat,
                "lon": params.launch_lon,
                "alt_m": params.launch_elevation_m,
                "time_s": 0.0,
            },
            "mean_trajectory": mean_trajectory,
            "mean_burst": mean_burst,
            "mean_landing": mean_landing,
            "landing_uncertainty_sigma_m": _landing_uncertainty_sigma_m(
                run_summaries,
                mean_landing,
            ),
            "sondehub_reference": None,
        },
    }


async def run_sondehub_simulation_payload(payload: dict[str, Any]) -> str:
    missing_profile = [
        field for field in PROFILE_FIELDS
        if payload.get(field) is None
    ]
    if missing_profile:
        return json.dumps(
            _error_payload(
                "missing_profile",
                (
                    "SondeHub trajectory requires ascent_rate_ms, "
                    "burst_altitude_m, and descent_rate_ms. Provide ascent rate, "
                    "burst altitude, and descent rate before running a prediction."
                ),
                missing_fields=missing_profile,
            )
        )

    try:
        params = SondehubSimulationInput.model_validate(payload)
        result = await _run_simulation(params)
        return json.dumps(result, default=str)
    except ValidationError as exc:
        extra_fields = sorted(set(payload) & LEGACY_HARDWARE_FIELDS)
        if extra_fields:
            return json.dumps(
                _error_payload(
                    "unsupported_hardware_inputs",
                    (
                        "SondeHub-only trajectory prediction does not use balloon, "
                        "gas, payload, nozzle lift, or parachute inputs. Provide "
                        "ascent_rate_ms, burst_altitude_m, descent_rate_ms, and num_runs."
                    ),
                    details={"unsupported_fields": extra_fields},
                )
            )
        return json.dumps(
            _error_payload(
                "validation_error",
                "Invalid SondeHub trajectory input.",
                details=exc.errors(),
            )
        )
    except Exception as exc:
        return json.dumps(
            _error_payload(
                type(exc).__name__,
                str(exc),
            )
        )


@mcp.tool(name="sondehub_run_simulation")
async def sondehub_run_simulation(
    launch_lat: float | None = None,
    launch_lon: float | None = None,
    launch_elevation_m: float | None = None,
    launch_datetime: str | None = None,
    ascent_rate_ms: float | None = None,
    burst_altitude_m: float | None = None,
    descent_rate_ms: float | None = None,
    num_runs: int | None = None,
    seed: int | None = None,
    ascent_rate_stddev_pct: float = 5.0,
    burst_altitude_stddev_m: float = 1000.0,
    descent_rate_stddev_pct: float = 10.0,
    launch_time_stddev_min: float = 10.0,
) -> str:
    return await run_sondehub_simulation_payload(
        {
            "launch_lat": launch_lat,
            "launch_lon": launch_lon,
            "launch_elevation_m": launch_elevation_m,
            "launch_datetime": launch_datetime,
            "ascent_rate_ms": ascent_rate_ms,
            "burst_altitude_m": burst_altitude_m,
            "descent_rate_ms": descent_rate_ms,
            "num_runs": num_runs,
            "seed": seed,
            "ascent_rate_stddev_pct": ascent_rate_stddev_pct,
            "burst_altitude_stddev_m": burst_altitude_stddev_m,
            "descent_rate_stddev_pct": descent_rate_stddev_pct,
            "launch_time_stddev_min": launch_time_stddev_min,
        }
    )


if __name__ == "__main__":
    mcp.run()
