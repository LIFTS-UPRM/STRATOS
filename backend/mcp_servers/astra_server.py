"""STRATOS wrapper around the vendored ASTRA MCP server."""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from vendor.astra_simulator_mcp import mcp_server as upstream


def _configure_astra_runtime() -> None:
    settings = get_settings()
    upstream.GFS_CACHE_ROOT = Path(settings.astra_gfs_cache_dir).expanduser().resolve()


_configure_astra_runtime()

mcp = upstream.mcp


async def astra_list_balloons(response_format: str = "json") -> str:
    return await upstream.astra_list_balloons(
        upstream.ListInput(response_format=response_format)
    )


async def astra_list_parachutes(response_format: str = "json") -> str:
    return await upstream.astra_list_parachutes(
        upstream.ListInput(response_format=response_format)
    )


async def astra_calculate_nozzle_lift(
    balloon_model: str,
    gas_type: str,
    payload_weight_kg: float,
    ascent_rate_ms: float = 5.0,
) -> str:
    return await upstream.astra_calculate_nozzle_lift(
        upstream.NozzleLiftInput(
            balloon_model=balloon_model,
            gas_type=gas_type,
            payload_weight_kg=payload_weight_kg,
            ascent_rate_ms=ascent_rate_ms,
        )
    )


async def astra_calculate_balloon_volume(
    balloon_model: str,
    gas_type: str,
    nozzle_lift_kg: float,
    payload_weight_kg: float,
) -> str:
    return await upstream.astra_calculate_balloon_volume(
        upstream.BalloonVolumeInput(
            balloon_model=balloon_model,
            gas_type=gas_type,
            nozzle_lift_kg=nozzle_lift_kg,
            payload_weight_kg=payload_weight_kg,
        )
    )


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
    return await upstream.astra_run_simulation(
        upstream.SimulationInput(
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
    )


if __name__ == "__main__":
    mcp.run()
