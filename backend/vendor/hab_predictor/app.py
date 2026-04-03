#!/usr/bin/env python3
"""
ASTRA web application.

This replaces the old MCP server with a small Flask app that exposes ASTRA
simulation endpoints and a SondeHub-inspired frontend for launch planning.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request

# Import ASTRA's GFS module before requests so grequests/gevent patches SSL
# first. Importing requests too early can trigger recursive HTTPS failures.
from astra import GFS as _astra_gfs_runtime  # noqa: F401
from astra.available_balloons_parachutes import balloons, parachutes
from astra.flight_tools import (
    MIXEDGAS_MOLECULAR_MASS,
    liftingGasMass,
    nozzleLiftFixedAscent,
)
import requests


STD_TEMP_C = 15.0
STD_PRESS_MBAR = 1013.25
STD_CD = 0.47
STD_EXCESS_PRESSURE = 1.0

VALID_GAS_TYPES = ("Helium", "Hydrogen")
GFS_CACHE_ROOT = Path(__file__).resolve().parent / ".cache" / "gfs"
OPENTOPO_ENDPOINTS = [
    endpoint.strip()
    for endpoint in os.environ.get(
        "ASTRA_ELEVATION_ENDPOINTS",
        ",".join(
            [
                "https://api.opentopodata.org/v1/mapzen",
                "https://api.opentopodata.org/v1/srtm30m",
                "https://api.opentopodata.org/v1/srtm90m",
            ]
        ),
    ).split(",")
    if endpoint.strip()
]
OPEN_METEO_PRESSURE_LEVELS = (
    1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400,
    300, 250, 200, 150, 100, 70, 50, 30, 20, 10,
)
KMH_TO_KNOTS = 0.539956803
SONDEHUB_TAWHIRI_ENDPOINT = os.environ.get(
    "ASTRA_SONDEHUB_TAWHIRI_ENDPOINT",
    "https://api.v2.sondehub.org/tawhiri",
)
SONDEHUB_TIMEOUT_S = 30
DEFAULT_SONDEHUB_ADJUSTMENT_WEIGHT = 1.0


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _datetime_to_rfc3339_utc(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _normalize_longitude_180(lon: float) -> float:
    return ((float(lon) + 180.0) % 360.0) - 180.0


def _normalize_longitude_360(lon: float) -> float:
    return float(lon) % 360.0


def _longitude_delta_deg(from_lon: float, to_lon: float) -> float:
    return _normalize_longitude_180(float(to_lon) - float(from_lon))


def _latest_gfs_cycle_datetime(simulation_dt: datetime) -> datetime:
    current_dt = _utcnow_naive()
    if simulation_dt < current_dt:
        current_dt = simulation_dt
    return current_dt.replace(
        hour=(current_dt.hour // 6) * 6,
        minute=0,
        second=0,
        microsecond=0,
    )


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


def _load_cache_metadata(metadata_path: Path) -> dict[str, Any] | None:
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_cached_gfs_module(module_path: Path):
    with module_path.open("rb") as handle:
        return pickle.load(handle)


def _save_gfs_cache(
    *,
    cache_dir: Path,
    metadata_path: Path,
    module_path: Path,
    metadata: dict[str, Any],
    gfs_module,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_meta = metadata_path.with_suffix(".json.tmp")
    temp_module = module_path.with_suffix(".pkl.tmp")
    temp_meta.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    with temp_module.open("wb") as handle:
        pickle.dump(gfs_module, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp_meta, metadata_path)
    os.replace(temp_module, module_path)


def _prime_environment_from_gfs_module(environment) -> None:
    from astra import global_tools as tools

    if environment.UTC_offset == 0:
        environment.UTC_offset = tools.getUTCOffset(
            environment.launchSiteLat, environment.launchSiteLon, environment.dateAndTime
        )

    environment._UTC_time = environment.dateAndTime - timedelta(
        seconds=environment.UTC_offset * 3600
    )

    pressure_interp, temperature_interp, wind_dir_interp, wind_speed_interp = (
        environment._GFSmodule.interpolateData("press", "temp", "windrct", "windspd")
    )

    environment.getPressure = lambda lat, lon, alt, time: float(
        pressure_interp(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getTemperature = lambda lat, lon, alt, time: float(
        temperature_interp(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getWindDirection = lambda lat, lon, alt, time: float(
        wind_dir_interp(
            lat,
            lon,
            alt,
            environment._GFSmodule.getGFStime(
                time - timedelta(seconds=environment.UTC_offset * 3600)
            ),
        )
    )
    environment.getWindSpeed = lambda lat, lon, alt, time: float(
        wind_speed_interp(
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


def _fetch_open_meteo_weather_profile(environment) -> dict[str, Any]:
    hours_until_launch = max(
        0.0, (environment.dateAndTime - _utcnow_naive()).total_seconds() / 3600.0
    )
    forecast_days = max(
        1,
        min(16, int(math.ceil((hours_until_launch + environment.forecastDuration + 24.0) / 24.0))),
    )

    hourly_fields = []
    for level in OPEN_METEO_PRESSURE_LEVELS:
        hourly_fields.extend(
            [
                f"temperature_{level}hPa",
                f"geopotential_height_{level}hPa",
                f"wind_speed_{level}hPa",
                f"wind_direction_{level}hPa",
            ]
        )

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": environment.launchSiteLat,
            "longitude": environment.launchSiteLon,
            "hourly": ",".join(hourly_fields),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly") or {}
    if not hourly.get("time"):
        raise RuntimeError("Open-Meteo response did not include hourly time coordinates.")
    return payload


def _prime_environment_from_open_meteo(environment, profile: dict[str, Any]) -> None:
    from astra import global_tools as tools

    if environment.UTC_offset == 0:
        environment.UTC_offset = tools.getUTCOffset(
            environment.launchSiteLat, environment.launchSiteLon, environment.dateAndTime
        )

    environment._UTC_time = environment.dateAndTime - timedelta(
        seconds=environment.UTC_offset * 3600
    )

    hourly = profile["hourly"]
    timestamps = np.array(
        [datetime.fromisoformat(value).timestamp() for value in hourly["time"]],
        dtype=float,
    )
    if timestamps.size == 0:
        raise RuntimeError("Open-Meteo hourly profile is empty.")

    valid_levels = []
    temp_rows = []
    height_rows = []
    u_rows = []
    v_rows = []

    for level in OPEN_METEO_PRESSURE_LEVELS:
        temp_values = hourly.get(f"temperature_{level}hPa") or []
        height_values = hourly.get(f"geopotential_height_{level}hPa") or []
        speed_values = hourly.get(f"wind_speed_{level}hPa") or []
        direction_values = hourly.get(f"wind_direction_{level}hPa") or []

        if not (
            len(temp_values)
            == len(height_values)
            == len(speed_values)
            == len(direction_values)
            == len(timestamps)
        ):
            continue

        valid_levels.append(float(level))
        temp_rows.append([float(value) for value in temp_values])
        height_rows.append([float(value) for value in height_values])
        u_level = []
        v_level = []
        for direction, speed in zip(direction_values, speed_values):
            u_component, v_component = tools.dirspeed2uv(
                float(direction),
                float(speed) * KMH_TO_KNOTS,
            )
            u_level.append(float(u_component))
            v_level.append(float(v_component))
        u_rows.append(u_level)
        v_rows.append(v_level)

    if not valid_levels:
        raise RuntimeError("Open-Meteo response did not include any complete pressure levels.")

    pressure_levels = np.array(valid_levels, dtype=float)
    temperature_matrix = np.array(temp_rows, dtype=float).T
    height_matrix = np.array(height_rows, dtype=float).T
    u_matrix = np.array(u_rows, dtype=float).T
    v_matrix = np.array(v_rows, dtype=float).T
    temperature_bounds = (
        float(np.nanmin(temperature_matrix)),
        float(np.nanmax(temperature_matrix)),
    )
    pressure_bounds = (float(np.nanmax(pressure_levels)), float(np.nanmin(pressure_levels)))

    def _profile_at_time_index(time_idx: int, altitude_m: float) -> tuple[float, float, float, float]:
        heights = height_matrix[time_idx]
        temps = temperature_matrix[time_idx]
        u_components = u_matrix[time_idx]
        v_components = v_matrix[time_idx]

        order = np.argsort(heights)
        heights = heights[order]
        temps = temps[order]
        u_components = u_components[order]
        v_components = v_components[order]
        pressures = pressure_levels[order]

        heights, unique_idx = np.unique(heights, return_index=True)
        temps = temps[unique_idx]
        u_components = u_components[unique_idx]
        v_components = v_components[unique_idx]
        pressures = pressures[unique_idx]

        if altitude_m <= heights[0]:
            return float(temps[0]), float(pressures[0]), float(u_components[0]), float(v_components[0])

        if altitude_m >= heights[-1]:
            _, isa_temp, _, isa_pressure, _ = tools.ISAatmosphere(altitude=tools.m2feet(altitude_m))
            return float(isa_temp), float(isa_pressure), float(u_components[-1]), float(v_components[-1])

        return (
            float(np.interp(altitude_m, heights, temps)),
            float(np.interp(altitude_m, heights, pressures)),
            float(np.interp(altitude_m, heights, u_components)),
            float(np.interp(altitude_m, heights, v_components)),
        )

    def _sample_profile(lat: float, lon: float, alt: float, time: datetime) -> tuple[float, float, float, float]:
        _ = lat, lon
        target_time = time - timedelta(seconds=environment.UTC_offset * 3600)
        target_timestamp = float(target_time.timestamp())

        if target_timestamp <= timestamps[0]:
            return _profile_at_time_index(0, alt)
        if target_timestamp >= timestamps[-1]:
            return _profile_at_time_index(len(timestamps) - 1, alt)

        upper_idx = int(np.searchsorted(timestamps, target_timestamp, side="right"))
        lower_idx = max(0, upper_idx - 1)
        upper_idx = min(upper_idx, len(timestamps) - 1)
        lower_sample = _profile_at_time_index(lower_idx, alt)
        upper_sample = _profile_at_time_index(upper_idx, alt)

        if lower_idx == upper_idx:
            return lower_sample

        span = timestamps[upper_idx] - timestamps[lower_idx]
        fraction = 0.0 if span == 0 else (target_timestamp - timestamps[lower_idx]) / span
        return tuple(
            lower_value + fraction * (upper_value - lower_value)
            for lower_value, upper_value in zip(lower_sample, upper_sample)
        )

    def get_temperature(lat, lon, alt, time):
        return float(np.clip(_sample_profile(lat, lon, alt, time)[0], *temperature_bounds))

    def get_pressure(lat, lon, alt, time):
        return float(np.clip(_sample_profile(lat, lon, alt, time)[1], pressure_bounds[1], pressure_bounds[0]))

    def get_wind_direction(lat, lon, alt, time):
        _, _, u_component, v_component = _sample_profile(lat, lon, alt, time)
        direction, _ = tools.uv2dirspeed(u_component, v_component)
        return float(direction)

    def get_wind_speed(lat, lon, alt, time):
        _, _, u_component, v_component = _sample_profile(lat, lon, alt, time)
        _, speed = tools.uv2dirspeed(u_component, v_component)
        return float(speed)

    environment.getTemperature = get_temperature
    environment.getPressure = get_pressure
    environment.getWindDirection = get_wind_direction
    environment.getWindSpeed = get_wind_speed

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


def _load_or_refresh_forecast_cache(environment) -> dict[str, Any]:
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
        if not getattr(environment, "_weatherLoaded", False) or getattr(environment, "_GFSmodule", None) is None:
            raise RuntimeError("GFS environment did not finish loading.")
        refreshed_metadata = {
            "schema_version": 1,
            "generated_at_utc": _utcnow_naive().isoformat(),
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

    open_meteo_error = None
    try:
        open_meteo_profile = _fetch_open_meteo_weather_profile(environment)
        _prime_environment_from_open_meteo(environment, open_meteo_profile)
        return {
            "source": "open-meteo",
            "latest_cycle_utc": latest_cycle_iso,
            "actual_cycle_utc": None,
            "cache_dir": str(cache_dir),
            "refresh_error": f"{type(refresh_error).__name__}: {refresh_error}" if refresh_error else None,
        }
    except Exception as exc:
        open_meteo_error = exc

    if refresh_error:
        raise RuntimeError(
            "Failed to load forecast cache: {}: {}; Open-Meteo fallback failed: {}: {}".format(
                type(refresh_error).__name__,
                refresh_error,
                type(open_meteo_error).__name__ if open_meteo_error else "RuntimeError",
                open_meteo_error if open_meteo_error else "unknown error",
            )
        )
    raise open_meteo_error if open_meteo_error else RuntimeError("Failed to load forecast cache")


def _extract_profile_summary(profile) -> dict[str, Any]:
    return _extract_profile_summary_from_arrays(
        profile,
        latitude_profile=profile.latitudeProfile,
        longitude_profile=profile.longitudeProfile,
        altitude_profile=profile.altitudeProfile,
        time_vector=profile.timeVector,
    )


def _extract_profile_summary_from_arrays(
    profile,
    *,
    latitude_profile,
    longitude_profile,
    altitude_profile,
    time_vector,
) -> dict[str, Any]:
    peak_index = int(np.argmax(profile.altitudeProfile))
    return {
        "run": int(profile.flightNumber),
        "landing_lat": float(latitude_profile[-1]),
        "landing_lon": float(longitude_profile[-1]),
        "landing_alt_m": float(altitude_profile[-1]),
        "max_altitude_m": float(profile.highestAltitude),
        "peak_lat": float(latitude_profile[peak_index]),
        "peak_lon": float(longitude_profile[peak_index]),
        "peak_time_s": float(time_vector[peak_index]),
        "flight_duration_s": float(time_vector[-1]),
        "burst": bool(profile.hasBurst),
    }


def _sample_trajectory(profile, max_points: int = 100) -> list[dict[str, float]]:
    return _sample_trajectory_from_arrays(
        time_vector=profile.timeVector,
        latitude_profile=profile.latitudeProfile,
        longitude_profile=profile.longitudeProfile,
        altitude_profile=profile.altitudeProfile,
        max_points=max_points,
    )


def _sample_trajectory_from_arrays(
    *,
    time_vector,
    latitude_profile,
    longitude_profile,
    altitude_profile,
    max_points: int = 100,
) -> list[dict[str, float]]:
    point_count = len(time_vector)
    step = max(1, point_count // max_points)
    sampled = [
        {
            "time_s": float(time_vector[index]),
            "lat": float(latitude_profile[index]),
            "lon": float(longitude_profile[index]),
            "alt_m": float(altitude_profile[index]),
        }
        for index in range(0, point_count, step)
    ]
    if sampled and sampled[-1]["time_s"] != float(time_vector[-1]):
        sampled.append(
            {
                "time_s": float(time_vector[-1]),
                "lat": float(latitude_profile[-1]),
                "lon": float(longitude_profile[-1]),
                "alt_m": float(altitude_profile[-1]),
            }
        )
    return sampled


def _great_circle_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_km = 6371.0
    lat1 = math.radians(lat_a)
    lat2 = math.radians(lat_b)
    dlat = lat2 - lat1
    dlon = math.radians(lon_b - lon_a)
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(math.sqrt(hav))


def _median_vertical_rate(
    time_vector,
    altitude_profile,
    *,
    positive: bool | None = None,
    max_altitude_m: float | None = None,
) -> float | None:
    rates = []
    for index in range(len(time_vector) - 1):
        dt = float(time_vector[index + 1] - time_vector[index])
        if dt <= 0:
            continue
        altitude_a = float(altitude_profile[index])
        altitude_b = float(altitude_profile[index + 1])
        if max_altitude_m is not None and altitude_a > max_altitude_m and altitude_b > max_altitude_m:
            continue
        rate = (altitude_b - altitude_a) / dt
        if positive is True and rate <= 0:
            continue
        if positive is False and rate >= 0:
            continue
        rates.append(abs(rate) if positive is False else rate)
    if not rates:
        return None
    return float(statistics.median(rates))


def _estimate_sondehub_request(profile) -> dict[str, Any] | None:
    if not profile.hasBurst or profile.highestAltIndex <= 0:
        return None

    ascent_time = profile.timeVector[: profile.highestAltIndex + 1]
    ascent_altitude = profile.altitudeProfile[: profile.highestAltIndex + 1]
    ascent_rate = _median_vertical_rate(ascent_time, ascent_altitude, positive=True)
    if ascent_rate is None:
        return None

    launch_altitude = float(profile.altitudeProfile[0])
    low_altitude_window = max(launch_altitude + 2000.0, 2500.0)
    descent_time = profile.timeVector[profile.highestAltIndex :]
    descent_altitude = profile.altitudeProfile[profile.highestAltIndex :]
    descent_rate = _median_vertical_rate(
        descent_time,
        descent_altitude,
        positive=False,
        max_altitude_m=low_altitude_window,
    )
    if descent_rate is None:
        descent_rate = _median_vertical_rate(descent_time, descent_altitude, positive=False)
    if descent_rate is None:
        return None

    return {
        "profile": "standard_profile",
        "launch_latitude": float(profile.latitudeProfile[0]),
        "launch_longitude": _normalize_longitude_360(profile.longitudeProfile[0]),
        "launch_altitude": launch_altitude,
        "launch_datetime": _datetime_to_rfc3339_utc(profile.launchDateTime),
        "ascent_rate": float(ascent_rate),
        "burst_altitude": float(profile.highestAltitude),
        "descent_rate": float(descent_rate),
    }


def _fetch_sondehub_prediction(request_params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        SONDEHUB_TAWHIRI_ENDPOINT,
        params=request_params,
        timeout=SONDEHUB_TIMEOUT_S,
    )
    payload = response.json()
    if response.status_code >= 400:
        error = payload.get("error") or {}
        description = error.get("description") or response.text
        raise RuntimeError(f"SondeHub predictor error: {description}")
    if payload.get("error"):
        raise RuntimeError(
            f"SondeHub predictor error: {payload['error'].get('description', 'unknown error')}"
        )
    return payload


def _normalize_sondehub_trajectory_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "lat": float(point["latitude"]),
        "lon": _normalize_longitude_180(point["longitude"]),
        "alt_m": float(point["altitude"]),
        "datetime": point["datetime"],
    }


def _sample_sondehub_trajectory(payload: dict[str, Any], max_points: int = 120) -> list[dict[str, Any]]:
    points = []
    for stage in payload.get("prediction") or []:
        for point in stage.get("trajectory") or []:
            normalized = _normalize_sondehub_trajectory_point(point)
            points.append(
                {
                    "stage": stage.get("stage"),
                    "lat": normalized["lat"],
                    "lon": normalized["lon"],
                    "alt_m": normalized["alt_m"],
                    "datetime": normalized["datetime"],
                }
            )
    if not points:
        return []
    step = max(1, len(points) // max_points)
    return points[::step]


def _build_sondehub_reference(payload: dict[str, Any]) -> dict[str, Any] | None:
    stages = {stage.get("stage"): stage for stage in payload.get("prediction") or []}
    ascent_stage = stages.get("ascent")
    descent_stage = stages.get("descent")
    if not ascent_stage or not descent_stage:
        return None

    ascent_trajectory = ascent_stage.get("trajectory") or []
    descent_trajectory = descent_stage.get("trajectory") or []
    if not ascent_trajectory or not descent_trajectory:
        return None

    burst_point = _normalize_sondehub_trajectory_point(ascent_trajectory[-1])
    landing_point = _normalize_sondehub_trajectory_point(descent_trajectory[-1])
    return {
        "burst": burst_point,
        "landing": landing_point,
        "trajectory": _sample_sondehub_trajectory(payload),
        "metadata": payload.get("metadata") or {},
        "request": payload.get("request") or {},
    }


def _build_sondehub_calibration(
    baseline_profile,
    sondehub_payload: dict[str, Any],
    *,
    weight: float,
) -> dict[str, Any] | None:
    reference = _build_sondehub_reference(sondehub_payload)
    if reference is None:
        return None

    astra_burst_lat = float(baseline_profile.latitudeProfile[baseline_profile.highestAltIndex])
    astra_burst_lon = float(baseline_profile.longitudeProfile[baseline_profile.highestAltIndex])
    astra_landing_lat = float(baseline_profile.latitudeProfile[-1])
    astra_landing_lon = float(baseline_profile.longitudeProfile[-1])

    burst_delta_lat = (reference["burst"]["lat"] - astra_burst_lat) * weight
    burst_delta_lon = _longitude_delta_deg(astra_burst_lon, reference["burst"]["lon"]) * weight
    landing_delta_lat = (reference["landing"]["lat"] - astra_landing_lat) * weight
    landing_delta_lon = _longitude_delta_deg(astra_landing_lon, reference["landing"]["lon"]) * weight

    return {
        "provider": "sondehub-tawhiri",
        "weight": float(weight),
        "burst_delta": {"lat": burst_delta_lat, "lon": burst_delta_lon},
        "landing_delta": {"lat": landing_delta_lat, "lon": landing_delta_lon},
        "comparison": {
            "astra_burst_lat": astra_burst_lat,
            "astra_burst_lon": astra_burst_lon,
            "astra_landing_lat": astra_landing_lat,
            "astra_landing_lon": astra_landing_lon,
            "sondehub_burst_lat": reference["burst"]["lat"],
            "sondehub_burst_lon": reference["burst"]["lon"],
            "sondehub_landing_lat": reference["landing"]["lat"],
            "sondehub_landing_lon": reference["landing"]["lon"],
            "burst_delta_km": _great_circle_km(
                astra_burst_lat,
                astra_burst_lon,
                reference["burst"]["lat"],
                reference["burst"]["lon"],
            ),
            "landing_delta_km": _great_circle_km(
                astra_landing_lat,
                astra_landing_lon,
                reference["landing"]["lat"],
                reference["landing"]["lon"],
            ),
        },
        "reference": reference,
    }


def _calibration_offset_for_index(
    index: int,
    *,
    total_points: int,
    burst_index: int | None,
    burst_delta: dict[str, float],
    landing_delta: dict[str, float],
) -> tuple[float, float]:
    if total_points <= 1:
        return 0.0, 0.0

    if burst_index is None or burst_index <= 0 or burst_index >= total_points - 1:
        fraction = index / float(total_points - 1)
        return (
            landing_delta["lat"] * fraction,
            landing_delta["lon"] * fraction,
        )

    if index <= burst_index:
        fraction = index / float(burst_index)
        return (
            burst_delta["lat"] * fraction,
            burst_delta["lon"] * fraction,
        )

    fraction = (index - burst_index) / float(total_points - 1 - burst_index)
    return (
        burst_delta["lat"] + (landing_delta["lat"] - burst_delta["lat"]) * fraction,
        burst_delta["lon"] + (landing_delta["lon"] - burst_delta["lon"]) * fraction,
    )


def _apply_sondehub_calibration(profile, calibration: dict[str, Any]) -> tuple[list[float], list[float]]:
    if not calibration:
        return list(profile.latitudeProfile), list(profile.longitudeProfile)

    burst_index = profile.highestAltIndex if profile.hasBurst else None
    total_points = len(profile.latitudeProfile)
    adjusted_latitudes = []
    adjusted_longitudes = []

    for index, (lat, lon) in enumerate(zip(profile.latitudeProfile, profile.longitudeProfile)):
        delta_lat, delta_lon = _calibration_offset_for_index(
            index,
            total_points=total_points,
            burst_index=burst_index,
            burst_delta=calibration["burst_delta"],
            landing_delta=calibration["landing_delta"],
        )
        adjusted_latitudes.append(float(lat) + delta_lat)
        adjusted_longitudes.append(_normalize_longitude_180(float(lon) + delta_lon))

    return adjusted_latitudes, adjusted_longitudes


def _aggregate_runs(run_summaries: list[dict[str, Any]]) -> dict[str, float]:
    lats = [run["landing_lat"] for run in run_summaries]
    lons = [run["landing_lon"] for run in run_summaries]
    alts = [run["max_altitude_m"] for run in run_summaries]
    durations = [run["flight_duration_s"] for run in run_summaries]
    mean_lat = statistics.mean(lats)
    mean_lon = statistics.mean(lons)
    landing_spread = max(
        _great_circle_km(run["landing_lat"], run["landing_lon"], mean_lat, mean_lon)
        for run in run_summaries
    )
    return {
        "landing_lat_mean": mean_lat,
        "landing_lat_min": min(lats),
        "landing_lat_max": max(lats),
        "landing_lon_mean": mean_lon,
        "landing_lon_min": min(lons),
        "landing_lon_max": max(lons),
        "max_altitude_m_mean": statistics.mean(alts),
        "max_altitude_m_min": min(alts),
        "max_altitude_m_max": max(alts),
        "flight_duration_s_mean": statistics.mean(durations),
        "flight_duration_s_min": min(durations),
        "flight_duration_s_max": max(durations),
        "burst_rate": sum(1 for run in run_summaries if run["burst"]) / len(run_summaries),
        "landing_spread_km": landing_spread,
    }


def _mean_longitude_deg(longitudes: list[float]) -> float:
    if not longitudes:
        return 0.0

    radians = np.radians(np.asarray(longitudes, dtype=float))
    mean_sin = float(np.mean(np.sin(radians)))
    mean_cos = float(np.mean(np.cos(radians)))
    if mean_sin == 0.0 and mean_cos == 0.0:
        return _normalize_longitude_180(statistics.mean(longitudes))

    return _normalize_longitude_180(math.degrees(math.atan2(mean_sin, mean_cos)))


def _build_mean_location(
    run_summaries: list[dict[str, Any]],
    *,
    lat_key: str,
    lon_key: str,
    alt_key: str,
    time_key: str | None = None,
) -> dict[str, float] | None:
    if not run_summaries:
        return None

    point: dict[str, float] = {
        "lat": float(statistics.mean(run[lat_key] for run in run_summaries)),
        "lon": _mean_longitude_deg([run[lon_key] for run in run_summaries]),
        "alt_m": float(statistics.mean(run[alt_key] for run in run_summaries)),
    }
    if time_key is not None:
        point["time_s"] = float(statistics.mean(run[time_key] for run in run_summaries))
    return point


def _landing_uncertainty_sigma_m(
    run_summaries: list[dict[str, Any]],
    mean_landing: dict[str, float] | None,
) -> float:
    if not run_summaries or mean_landing is None:
        return 0.0

    squared_distances = [
        (_great_circle_km(
            run["landing_lat"],
            run["landing_lon"],
            mean_landing["lat"],
            mean_landing["lon"],
        ) * 1000.0) ** 2
        for run in run_summaries
    ]
    return float(math.sqrt(statistics.mean(squared_distances)))


def _build_mean_trajectory(
    trajectory_runs: list[dict[str, Any]],
    *,
    sample_points: int = 120,
) -> list[dict[str, float]]:
    if not trajectory_runs:
        return []

    sample_axis = np.linspace(0.0, 1.0, max(2, sample_points))
    lat_samples = []
    lon_samples = []
    alt_samples = []
    time_samples = []

    for trajectory in trajectory_runs:
        time_vector = np.asarray(trajectory["time_vector"], dtype=float)
        latitude_profile = np.asarray(trajectory["latitude_profile"], dtype=float)
        longitude_profile = np.unwrap(
            np.radians(np.asarray(trajectory["longitude_profile"], dtype=float))
        )
        altitude_profile = np.asarray(trajectory["altitude_profile"], dtype=float)

        if time_vector.size == 0:
            continue

        duration_s = float(time_vector[-1])
        if duration_s > 0.0:
            progress_axis = time_vector / duration_s
        else:
            progress_axis = np.linspace(0.0, 1.0, time_vector.size)

        lat_samples.append(np.interp(sample_axis, progress_axis, latitude_profile))
        lon_samples.append(np.interp(sample_axis, progress_axis, longitude_profile))
        alt_samples.append(np.interp(sample_axis, progress_axis, altitude_profile))
        time_samples.append(np.interp(sample_axis, progress_axis, time_vector))

    if not lat_samples:
        return []

    mean_latitude = np.mean(np.vstack(lat_samples), axis=0)
    lon_matrix = np.vstack(lon_samples)
    mean_longitude = np.degrees(
        np.arctan2(
            np.mean(np.sin(lon_matrix), axis=0),
            np.mean(np.cos(lon_matrix), axis=0),
        )
    )
    mean_altitude = np.mean(np.vstack(alt_samples), axis=0)
    mean_time = np.mean(np.vstack(time_samples), axis=0)

    return [
        {
            "time_s": float(mean_time[index]),
            "lat": float(mean_latitude[index]),
            "lon": _normalize_longitude_180(float(mean_longitude[index])),
            "alt_m": float(mean_altitude[index]),
        }
        for index in range(sample_axis.size)
    ]


def _coerce_str(payload: dict[str, Any], key: str, *, required: bool = True, default: str | None = None) -> str | None:
    value = payload.get(key, default)
    if value is None or value == "":
        if required:
            raise ValueError(f"{key} is required.")
        return default
    return str(value).strip()


def _coerce_float(
    payload: dict[str, Any],
    key: str,
    *,
    required: bool = True,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = payload.get(key, default)
    if value in (None, ""):
        if required:
            raise ValueError(f"{key} is required.")
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number.") from exc
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{key} must be at most {maximum}.")
    return result


def _coerce_int(
    payload: dict[str, Any],
    key: str,
    *,
    required: bool = True,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = payload.get(key, default)
    if value in (None, ""):
        if required:
            raise ValueError(f"{key} is required.")
        return default
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer.") from exc
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{key} must be at most {maximum}.")
    return result


def _coerce_bool(payload: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_datetime(payload: dict[str, Any], key: str) -> datetime:
    value = _coerce_str(payload, key)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{key} must be ISO 8601 format: YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS.") from exc
    if result.tzinfo is not None:
        return result.astimezone(UTC).replace(tzinfo=None)
    return result


def _validate_hardware(balloon_model: str, gas_type: str, parachute_model: str | None = None) -> None:
    if balloon_model not in balloons:
        raise ValueError(f"Unknown balloon_model '{balloon_model}'.")
    if gas_type not in VALID_GAS_TYPES:
        raise ValueError(f"gas_type must be one of {VALID_GAS_TYPES}.")
    if parachute_model is not None and parachute_model not in parachutes:
        raise ValueError(f"Unknown parachute_model '{parachute_model}'.")


def lookup_launch_elevation(lat: float, lon: float) -> dict[str, Any]:
    last_error = None

    for endpoint in OPENTOPO_ENDPOINTS:
        try:
            response = requests.get(
                endpoint,
                params={"locations": f"{lat},{lon}"},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            if not results:
                raise RuntimeError("OpenTopoData response did not include any elevation results.")

            first_result = results[0] or {}
            elevation_m = first_result.get("elevation")
            if elevation_m is None:
                raise RuntimeError("OpenTopoData response did not include elevation for this point.")

            return {
                "lat": float(first_result.get("location", {}).get("lat", lat)),
                "lon": float(first_result.get("location", {}).get("lng", lon)),
                "elevation_m": float(elevation_m),
                "dataset": payload.get("dataset") or first_result.get("dataset") or endpoint.rsplit("/", 1)[-1],
                "status": payload.get("status") or "OK",
                "source": "open-topo-data",
            }
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Unable to fetch launch elevation from OpenTopoData endpoints: {last_error}"
    )


def get_balloon_catalog() -> list[dict[str, Any]]:
    items = []
    for name, spec in sorted(balloons.items(), key=lambda item: str(item[0])):
        family = "totex" if name.startswith("TA") else "hwoyee" if name.startswith("HW") else "other"
        items.append(
            {
                "name": name,
                "family": family,
                "mass_kg": float(spec[0]),
                "burst_diameter_m": float(spec[1]),
                "weibull_lambda": float(spec[2]),
                "weibull_k": float(spec[3]),
            }
        )
    return items


def get_parachute_catalog() -> list[dict[str, Any]]:
    items = []
    for name, area in sorted(parachutes.items(), key=lambda item: str(item[0])):
        items.append(
            {
                "name": name,
                "reference_area_m2": float(area),
                "approx_diameter_m": 2.0 * math.sqrt(area / math.pi),
            }
        )
    return items


def calculate_nozzle_lift(payload: dict[str, Any]) -> dict[str, Any]:
    balloon_model = _coerce_str(payload, "balloon_model")
    gas_type = _coerce_str(payload, "gas_type")
    payload_weight_kg = _coerce_float(payload, "payload_weight_kg", minimum=0.0, maximum=50.0)
    ascent_rate_ms = _coerce_float(payload, "ascent_rate_ms", required=False, default=5.0, minimum=0.1, maximum=20.0)

    _validate_hardware(balloon_model, gas_type)

    balloon_mass_kg = balloons[balloon_model][0]
    gas_mol_mass = MIXEDGAS_MOLECULAR_MASS[gas_type]

    nozzle_lift = nozzleLiftFixedAscent(
        ascentRate=ascent_rate_ms,
        balloonMass=balloon_mass_kg,
        payloadMass=payload_weight_kg,
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

    return {
        "balloon_model": balloon_model,
        "gas_type": gas_type,
        "payload_weight_kg": payload_weight_kg,
        "ascent_rate_ms": ascent_rate_ms,
        "balloon_mass_kg": round(float(balloon_mass_kg), 4),
        "nozzle_lift_kg": round(float(nozzle_lift), 4),
        "gas_mass_kg": round(float(gas_mass), 4),
        "balloon_volume_m3": round(float(volume), 4),
        "balloon_diameter_m": round(float(diameter), 4),
    }


def calculate_balloon_volume(payload: dict[str, Any]) -> dict[str, Any]:
    balloon_model = _coerce_str(payload, "balloon_model")
    gas_type = _coerce_str(payload, "gas_type")
    nozzle_lift_kg = _coerce_float(payload, "nozzle_lift_kg", minimum=0.0, maximum=100.0)
    payload_weight_kg = _coerce_float(payload, "payload_weight_kg", minimum=0.0, maximum=50.0)

    _validate_hardware(balloon_model, gas_type)

    balloon_mass_kg = balloons[balloon_model][0]
    gas_mol_mass = MIXEDGAS_MOLECULAR_MASS[gas_type]
    gas_mass, volume, diameter = liftingGasMass(
        nozzleLift=nozzle_lift_kg,
        balloonMass=balloon_mass_kg,
        ambientTempC=STD_TEMP_C,
        ambientPressMbar=STD_PRESS_MBAR,
        gasMolecularMass=gas_mol_mass,
        excessPressureCoefficient=STD_EXCESS_PRESSURE,
    )
    free_lift = nozzle_lift_kg - payload_weight_kg - balloon_mass_kg

    return {
        "balloon_model": balloon_model,
        "gas_type": gas_type,
        "nozzle_lift_kg": nozzle_lift_kg,
        "payload_weight_kg": payload_weight_kg,
        "balloon_mass_kg": round(float(balloon_mass_kg), 4),
        "gas_mass_kg": round(float(gas_mass), 4),
        "balloon_volume_m3": round(float(volume), 4),
        "balloon_diameter_m": round(float(diameter), 4),
        "free_lift_kg": round(float(free_lift), 4),
    }


def run_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    from astra.simulator import flight, forecastEnvironment

    launch_lat = _coerce_float(payload, "launch_lat", minimum=-90.0, maximum=90.0)
    launch_lon = _coerce_float(payload, "launch_lon", minimum=-180.0, maximum=180.0)
    launch_elevation_m = _coerce_float(
        payload,
        "launch_elevation_m",
        required=False,
        default=None,
        minimum=0.0,
        maximum=5000.0,
    )
    launch_dt = _coerce_datetime(payload, "launch_datetime")
    balloon_model = _coerce_str(payload, "balloon_model")
    gas_type = _coerce_str(payload, "gas_type")
    nozzle_lift_kg = _coerce_float(payload, "nozzle_lift_kg", minimum=0.0, maximum=100.0)
    payload_weight_kg = _coerce_float(payload, "payload_weight_kg", minimum=0.0, maximum=50.0)
    parachute_model = _coerce_str(payload, "parachute_model", required=False, default=None)
    num_runs = _coerce_int(payload, "num_runs", required=False, default=5, minimum=1, maximum=20)
    floating_flight = _coerce_bool(payload, "floating_flight", default=False)
    floating_altitude_m = _coerce_float(
        payload, "floating_altitude_m", required=False, default=None, minimum=0.0, maximum=50000.0
    )
    cutdown = _coerce_bool(payload, "cutdown", default=False)
    cutdown_altitude_m = _coerce_float(
        payload, "cutdown_altitude_m", required=False, default=None, minimum=0.0, maximum=50000.0
    )
    force_low_res = _coerce_bool(payload, "force_low_res", default=False)
    compare_with_sondehub = _coerce_bool(payload, "compare_with_sondehub", default=True)
    adjust_with_sondehub = _coerce_bool(payload, "adjust_with_sondehub", default=True)
    sondehub_adjustment_weight = _coerce_float(
        payload,
        "sondehub_adjustment_weight",
        required=False,
        default=DEFAULT_SONDEHUB_ADJUSTMENT_WEIGHT,
        minimum=0.0,
        maximum=1.0,
    )

    if launch_elevation_m is None:
        launch_elevation_m = lookup_launch_elevation(launch_lat, launch_lon)["elevation_m"]

    _validate_hardware(balloon_model, gas_type, parachute_model)

    flight_kwargs: dict[str, Any] = {}
    if floating_flight:
        if floating_altitude_m is None:
            raise ValueError("floating_altitude_m is required when floating_flight is true.")
        flight_kwargs["floatingFlight"] = True
        flight_kwargs["floatingAltitude"] = floating_altitude_m
    if cutdown:
        if cutdown_altitude_m is None:
            raise ValueError("cutdown_altitude_m is required when cutdown is true.")
        flight_kwargs["cutdown"] = True
        flight_kwargs["cutdownAltitude"] = cutdown_altitude_m

    environment = forecastEnvironment(
        launchSiteLat=launch_lat,
        launchSiteLon=launch_lon,
        launchSiteElev=launch_elevation_m,
        dateAndTime=launch_dt,
        forceNonHD=force_low_res,
        debugging=False,
    )
    forecast_info = _load_or_refresh_forecast_cache(environment)

    baseline_sim = flight(
        environment=environment,
        balloonGasType=gas_type,
        balloonModel=balloon_model,
        nozzleLift=nozzle_lift_kg,
        payloadTrainWeight=payload_weight_kg,
        parachuteModel=parachute_model,
        numberOfSimRuns=1,
        debugging=False,
        **flight_kwargs,
    )
    baseline_sim.run()
    if not baseline_sim.results:
        raise RuntimeError("Baseline simulation completed but produced no results.")

    if num_runs == 1:
        sim = baseline_sim
    else:
        sim = flight(
            environment=environment,
            balloonGasType=gas_type,
            balloonModel=balloon_model,
            nozzleLift=nozzle_lift_kg,
            payloadTrainWeight=payload_weight_kg,
            parachuteModel=parachute_model,
            numberOfSimRuns=num_runs,
            debugging=False,
            **flight_kwargs,
        )
        sim.run()

    if not sim.results:
        raise RuntimeError("Simulation completed but produced no results.")

    raw_run_summaries = [_extract_profile_summary(profile) for profile in sim.results]
    raw_aggregate = _aggregate_runs(raw_run_summaries)
    raw_trajectory = _sample_trajectory(sim.results[0])

    sondehub_info: dict[str, Any] = {
        "status": "skipped",
        "provider": "sondehub-tawhiri",
        "adjustment_weight": float(sondehub_adjustment_weight),
    }
    calibration = None

    if compare_with_sondehub:
        if floating_flight:
            sondehub_info["reason"] = "SondeHub comparison is currently only applied to burst/descent flights."
        else:
            request_params = _estimate_sondehub_request(baseline_sim.results[0])
            if request_params is None:
                sondehub_info["reason"] = "Unable to derive a SondeHub reference from the baseline ASTRA profile."
            else:
                try:
                    sondehub_payload = _fetch_sondehub_prediction(request_params)
                    sondehub_info["request"] = request_params
                    sondehub_info["reference"] = _build_sondehub_reference(sondehub_payload)
                    if adjust_with_sondehub and sondehub_adjustment_weight > 0:
                        calibration = _build_sondehub_calibration(
                            baseline_sim.results[0],
                            sondehub_payload,
                            weight=float(sondehub_adjustment_weight),
                        )
                    if calibration:
                        sondehub_info["status"] = "applied"
                        sondehub_info["comparison"] = calibration["comparison"]
                    else:
                        sondehub_info["status"] = "compared"
                except Exception as exc:
                    sondehub_info["status"] = "error"
                    sondehub_info["error"] = f"{type(exc).__name__}: {exc}"

    run_summaries = []
    adjusted_trajectory = raw_trajectory
    adjusted_trajectory_runs = []
    for index, profile in enumerate(sim.results):
        adjusted_latitudes, adjusted_longitudes = _apply_sondehub_calibration(profile, calibration)
        adjusted_trajectory_runs.append(
            {
                "time_vector": profile.timeVector,
                "latitude_profile": adjusted_latitudes,
                "longitude_profile": adjusted_longitudes,
                "altitude_profile": profile.altitudeProfile,
            }
        )
        run_summaries.append(
            _extract_profile_summary_from_arrays(
                profile,
                latitude_profile=adjusted_latitudes,
                longitude_profile=adjusted_longitudes,
                altitude_profile=profile.altitudeProfile,
                time_vector=profile.timeVector,
            )
        )
        if index == 0:
            adjusted_trajectory = _sample_trajectory_from_arrays(
                time_vector=profile.timeVector,
                latitude_profile=adjusted_latitudes,
                longitude_profile=adjusted_longitudes,
                altitude_profile=profile.altitudeProfile,
            )

    aggregate = _aggregate_runs(run_summaries)
    mean_burst = _build_mean_location(
        run_summaries,
        lat_key="peak_lat",
        lon_key="peak_lon",
        alt_key="max_altitude_m",
        time_key="peak_time_s",
    )
    mean_landing = _build_mean_location(
        run_summaries,
        lat_key="landing_lat",
        lon_key="landing_lon",
        alt_key="landing_alt_m",
        time_key="flight_duration_s",
    )
    mean_trajectory = _build_mean_trajectory(adjusted_trajectory_runs)

    return {
        "status": "success",
        "launch": {
            "lat": launch_lat,
            "lon": launch_lon,
            "elevation_m": launch_elevation_m,
            "datetime": launch_dt.isoformat(),
        },
        "config": {
            "balloon_model": balloon_model,
            "gas_type": gas_type,
            "nozzle_lift_kg": nozzle_lift_kg,
            "payload_weight_kg": payload_weight_kg,
            "parachute_model": parachute_model,
            "num_runs": num_runs,
            "floating_flight": floating_flight,
            "floating_altitude_m": floating_altitude_m,
            "cutdown": cutdown,
            "cutdown_altitude_m": cutdown_altitude_m,
            "force_low_res": force_low_res,
        },
        "num_runs": len(sim.results),
        "forecast": forecast_info,
        "sondehub": sondehub_info,
        "runs": run_summaries,
        "aggregate": aggregate,
        "raw_runs": raw_run_summaries,
        "raw_aggregate": raw_aggregate,
        "trajectory_run1": adjusted_trajectory,
        "trajectory_run1_raw": raw_trajectory,
        "trajectory_artifact": {
            "launch": {
                "lat": launch_lat,
                "lon": launch_lon,
                "alt_m": launch_elevation_m,
                "time_s": 0.0,
            },
            "mean_trajectory": mean_trajectory,
            "mean_burst": mean_burst,
            "mean_landing": mean_landing,
            "landing_uncertainty_sigma_m": _landing_uncertainty_sigma_m(
                run_summaries,
                mean_landing,
            ),
        },
    }


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "astra-web"})

    @app.get("/api/hardware")
    def hardware():
        return jsonify(
            {
                "balloons": get_balloon_catalog(),
                "parachutes": get_parachute_catalog(),
                "gas_types": list(VALID_GAS_TYPES),
            }
        )

    @app.get("/api/balloons")
    def balloons_route():
        return jsonify({"balloons": get_balloon_catalog()})

    @app.get("/api/parachutes")
    def parachutes_route():
        return jsonify({"parachutes": get_parachute_catalog()})

    @app.get("/api/elevation")
    def elevation_route():
        try:
            lat = _coerce_float(request.args, "lat", minimum=-90.0, maximum=90.0)
            lon = _coerce_float(request.args, "lon", minimum=-180.0, maximum=180.0)
            return jsonify(lookup_launch_elevation(lat, lon))
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"status": "error", "error": f"{type(exc).__name__}: {exc}"}), 502

    @app.post("/api/nozzle-lift")
    def nozzle_lift_route():
        try:
            return jsonify(calculate_nozzle_lift(request.get_json(silent=True) or {}))
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"status": "error", "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/balloon-volume")
    def balloon_volume_route():
        try:
            return jsonify(calculate_balloon_volume(request.get_json(silent=True) or {}))
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"status": "error", "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/simulate")
    def simulate_route():
        try:
            return jsonify(run_simulation(request.get_json(silent=True) or {}))
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"status": "error", "error": f"{type(exc).__name__}: {exc}"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("ASTRA_HOST", "127.0.0.1"),
        port=int(os.environ.get("ASTRA_PORT", "5000")),
        debug=os.environ.get("ASTRA_DEBUG", "").lower() in {"1", "true", "yes"},
    )
