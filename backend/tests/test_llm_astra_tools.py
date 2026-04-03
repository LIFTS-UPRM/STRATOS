from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm


def test_get_tools_exposes_astra_and_removes_old_trajectory_tools() -> None:
    tool_names = [tool["function"]["name"] for tool in llm.get_tools()]

    for expected in (
        "astra_list_balloons",
        "astra_list_parachutes",
        "astra_calculate_nozzle_lift",
        "astra_calculate_balloon_volume",
        "astra_run_simulation",
    ):
        assert expected in tool_names

    for removed in ("predict_standard", "health_check", "get_supported_profiles"):
        assert removed not in tool_names


def test_get_tools_filters_by_enabled_group() -> None:
    tool_names = [
        tool["function"]["name"]
        for tool in llm.get_tools(["trajectory", "airspace"])
    ]

    assert "astra_run_simulation" in tool_names
    assert "check_airspace_hazards" in tool_names
    assert "get_surface_weather" not in tool_names
    assert "get_winds_aloft" not in tool_names


def test_get_tools_returns_no_schemas_when_no_groups_enabled() -> None:
    assert llm.get_tools([]) == []


def test_astra_wrapper_import_smoke() -> None:
    from mcp_servers import astra_server

    assert astra_server.mcp is not None
    assert callable(astra_server.astra_run_simulation)
    assert "TA800" in astra_server.balloons


def test_astra_list_balloons_uses_hab_predictor_catalog() -> None:
    from mcp_servers import astra_server

    payload = json.loads(asyncio.run(astra_server.astra_list_balloons()))

    assert "TA800" in payload
    assert payload["TA800"]["mass_kg"] > 0


def test_astra_run_simulation_includes_trajectory_artifact(monkeypatch) -> None:
    from mcp_servers import astra_server

    async def fake_run_bridge_tool(
        tool_name: str,
        _: dict[str, object],
    ) -> str:
        assert tool_name == "astra_run_simulation"
        return json.dumps({
            "status": "success",
            "num_runs": 2,
            "runs": [],
            "aggregate": {},
            "trajectory_run1": [],
            "trajectory_artifact": {
                "launch": {
                    "lat": 18.2,
                    "lon": -67.1,
                    "alt_m": 12.0,
                    "time_s": 0.0,
                },
                "mean_trajectory": [
                    {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
                    {"lat": 18.3, "lon": -67.0, "alt_m": 30000.0, "time_s": 2000.0},
                ],
                "mean_burst": {
                    "lat": 18.3,
                    "lon": -67.0,
                    "alt_m": 30000.0,
                    "time_s": 2000.0,
                },
                "mean_landing": {
                    "lat": 18.4,
                    "lon": -66.9,
                    "alt_m": 8.0,
                    "time_s": 5000.0,
                },
                "landing_uncertainty_sigma_m": 1200.0,
            },
        })

    monkeypatch.setattr(astra_server, "_run_bridge_tool", fake_run_bridge_tool)

    payload = json.loads(
        asyncio.run(
            astra_server.astra_run_simulation(
                launch_lat=18.2,
                launch_lon=-67.1,
                launch_elevation_m=12.0,
                launch_datetime="2026-04-01T12:00:00",
                balloon_model="TA800",
                gas_type="Helium",
                nozzle_lift_kg=2.0,
                payload_weight_kg=0.433,
                parachute_model="SPH36",
                num_runs=2,
            )
        )
    )

    assert payload["status"] == "success"
    assert payload["trajectory_artifact"]["landing_uncertainty_sigma_m"] == 1200.0
    assert payload["trajectory_artifact"]["mean_trajectory"][1]["alt_m"] == 30000.0


def test_execute_tool_normalizes_json_response(monkeypatch) -> None:
    from mcp_servers import astra_server

    async def fake_list_balloons(**_: object) -> str:
        return '{"status":"success","models":["TA800"]}'

    monkeypatch.setattr(astra_server, "astra_list_balloons", fake_list_balloons)

    payload = json.loads(asyncio.run(llm.execute_tool("astra_list_balloons", {})))

    assert payload == {"status": "success", "models": ["TA800"]}


def test_execute_tool_normalizes_error_string(monkeypatch) -> None:
    from mcp_servers import astra_server

    async def fake_run_simulation(**_: object) -> str:
        return "Error loading forecast data: RuntimeError: boom"

    monkeypatch.setattr(astra_server, "astra_run_simulation", fake_run_simulation)

    payload = json.loads(asyncio.run(llm.execute_tool("astra_run_simulation", {})))

    assert payload["status"] == "error"
    assert payload["tool"] == "astra_run_simulation"
    assert "boom" in payload["message"]


def test_execute_tool_rejects_non_json_string(monkeypatch) -> None:
    from mcp_servers import astra_server

    async def fake_list_parachutes(**_: object) -> str:
        return "plain text output"

    monkeypatch.setattr(astra_server, "astra_list_parachutes", fake_list_parachutes)

    payload = json.loads(asyncio.run(llm.execute_tool("astra_list_parachutes", {})))

    assert payload["status"] == "error"
    assert payload["tool"] == "astra_list_parachutes"
    assert "non-JSON" in payload["message"]
