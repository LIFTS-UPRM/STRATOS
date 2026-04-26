from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm


ASTRA_TOOL_NAMES = {
    "astra_list_balloons",
    "astra_list_parachutes",
    "astra_calculate_nozzle_lift",
    "astra_calculate_balloon_volume",
    "astra_run_simulation",
}


def _sondehub_payload(request_params: dict[str, object]) -> dict[str, object]:
    run = int(request_params["run"])
    launch_dt = datetime.fromisoformat(
        str(request_params["launch_datetime"]).replace("Z", "+00:00")
    )
    burst_seconds = float(request_params["burst_altitude"]) / float(request_params["ascent_rate"])
    landing_seconds = burst_seconds + (
        float(request_params["burst_altitude"]) / float(request_params["descent_rate"])
    )
    burst_dt = launch_dt + timedelta(seconds=burst_seconds)
    landing_dt = launch_dt + timedelta(seconds=landing_seconds)
    launch_lat = float(request_params["launch_latitude"])
    launch_lon = float(request_params["launch_longitude"])

    return {
        "prediction": [
            {
                "stage": "ascent",
                "trajectory": [
                    {
                        "latitude": launch_lat,
                        "longitude": launch_lon,
                        "altitude": float(request_params["launch_altitude"]),
                        "datetime": launch_dt.isoformat().replace("+00:00", "Z"),
                    },
                    {
                        "latitude": launch_lat + 0.04 + run * 0.001,
                        "longitude": launch_lon + 0.05,
                        "altitude": float(request_params["burst_altitude"]),
                        "datetime": burst_dt.isoformat().replace("+00:00", "Z"),
                    },
                ],
            },
            {
                "stage": "descent",
                "trajectory": [
                    {
                        "latitude": launch_lat + 0.04 + run * 0.001,
                        "longitude": launch_lon + 0.05,
                        "altitude": float(request_params["burst_altitude"]),
                        "datetime": burst_dt.isoformat().replace("+00:00", "Z"),
                    },
                    {
                        "latitude": launch_lat + 0.08 + run * 0.01,
                        "longitude": launch_lon + 0.10 + run * 0.01,
                        "altitude": 10.0,
                        "datetime": landing_dt.isoformat().replace("+00:00", "Z"),
                    },
                ],
            },
        ]
    }


def test_get_tools_exposes_sondehub_and_removes_astra_tools() -> None:
    tool_names = {tool["function"]["name"] for tool in llm.get_tools()}

    assert "sondehub_run_simulation" in tool_names
    assert ASTRA_TOOL_NAMES.isdisjoint(tool_names)
    assert {"predict_standard", "health_check", "get_supported_profiles"}.isdisjoint(tool_names)


def test_get_tools_filters_by_enabled_group() -> None:
    tool_names = [
        tool["function"]["name"]
        for tool in llm.get_tools(["trajectory", "airspace"])
    ]

    assert "sondehub_run_simulation" in tool_names
    assert "get_balloon_no_flight_zone" in tool_names
    assert "get_surface_weather" not in tool_names
    assert "get_winds_aloft" not in tool_names
    assert ASTRA_TOOL_NAMES.isdisjoint(tool_names)


def test_get_tools_returns_no_schemas_when_no_groups_enabled() -> None:
    assert llm.get_tools([]) == []


def test_system_prompt_uses_sondehub_only_policy() -> None:
    assert "STRATOS AI" in llm.SYSTEM_PROMPT
    assert "mission copilot" in llm.SYSTEM_PROMPT
    assert "SondeHub Tawhiri is the only trajectory prediction source" in llm.SYSTEM_PROMPT
    assert "Do not expose or call ASTRA tools" in llm.SYSTEM_PROMPT
    assert "untrusted data" in llm.SYSTEM_PROMPT
    assert "restriction_source_status" in llm.SYSTEM_PROMPT
    assert "get_balloon_no_flight_zone" in llm.SYSTEM_PROMPT


def test_sondehub_wrapper_import_smoke() -> None:
    from mcp_servers import sondehub_server

    assert sondehub_server.mcp is not None
    assert callable(sondehub_server.sondehub_run_simulation)
    assert sondehub_server.SONDEHUB_TAWHIRI_ENDPOINT


def test_sondehub_missing_profile_inputs_returns_clear_error() -> None:
    from mcp_servers import sondehub_server

    payload = json.loads(
        asyncio.run(
            sondehub_server.run_sondehub_simulation_payload(
                {
                    "launch_lat": 18.2,
                    "launch_lon": -67.1,
                    "launch_elevation_m": 12.0,
                    "launch_datetime": "2026-04-01T12:00:00Z",
                    "num_runs": 2,
                }
            )
        )
    )

    assert payload["status"] == "error"
    assert payload["error_type"] == "missing_profile"
    assert payload["missing_fields"] == [
        "ascent_rate_ms",
        "burst_altitude_m",
        "descent_rate_ms",
    ]


def test_sondehub_rejects_legacy_hardware_inputs() -> None:
    from mcp_servers import sondehub_server

    payload = json.loads(
        asyncio.run(
            sondehub_server.run_sondehub_simulation_payload(
                {
                    "launch_lat": 18.2,
                    "launch_lon": -67.1,
                    "launch_elevation_m": 12.0,
                    "launch_datetime": "2026-04-01T12:00:00Z",
                    "ascent_rate_ms": 5.0,
                    "burst_altitude_m": 30000.0,
                    "descent_rate_ms": 6.0,
                    "num_runs": 2,
                    "balloon_model": "TA800",
                    "nozzle_lift_kg": 2.0,
                }
            )
        )
    )

    assert payload["status"] == "error"
    assert payload["error_type"] == "unsupported_hardware_inputs"
    assert payload["details"]["unsupported_fields"] == ["balloon_model", "nozzle_lift_kg"]


def test_sondehub_monte_carlo_is_seed_stable(monkeypatch) -> None:
    from mcp_servers import sondehub_server

    async def fake_fetch(request_params: dict[str, object]) -> dict[str, object]:
        return _sondehub_payload(request_params)

    monkeypatch.setattr(sondehub_server, "_fetch_sondehub_prediction", fake_fetch)
    request = {
        "launch_lat": 18.2,
        "launch_lon": -67.1,
        "launch_elevation_m": 12.0,
        "launch_datetime": "2026-04-01T12:00:00Z",
        "ascent_rate_ms": 5.0,
        "burst_altitude_m": 30000.0,
        "descent_rate_ms": 6.0,
        "num_runs": 3,
        "seed": 1234,
    }

    first = json.loads(asyncio.run(sondehub_server.run_sondehub_simulation_payload(request)))
    second = json.loads(asyncio.run(sondehub_server.run_sondehub_simulation_payload(request)))

    assert first["status"] == "success"
    assert first["runs"] == second["runs"]
    assert first["trajectory_artifact"] == second["trajectory_artifact"]


def test_sondehub_response_normalizes_trajectory_artifact(monkeypatch) -> None:
    from mcp_servers import sondehub_server

    async def fake_fetch(request_params: dict[str, object]) -> dict[str, object]:
        return _sondehub_payload(request_params)

    monkeypatch.setattr(sondehub_server, "_fetch_sondehub_prediction", fake_fetch)

    payload = json.loads(
        asyncio.run(
            sondehub_server.run_sondehub_simulation_payload(
                {
                    "launch_lat": 18.2,
                    "launch_lon": -67.1,
                    "launch_elevation_m": 12.0,
                    "launch_datetime": "2026-04-01T12:00:00Z",
                    "ascent_rate_ms": 5.0,
                    "burst_altitude_m": 30000.0,
                    "descent_rate_ms": 6.0,
                    "num_runs": 2,
                    "seed": 42,
                }
            )
        )
    )

    assert payload["status"] == "success"
    assert payload["source"] == "sondehub-tawhiri"
    assert payload["num_runs"] == 2
    assert payload["trajectory_run1"][0]["lon"] == pytest.approx(-67.1)
    assert payload["trajectory_artifact"]["mean_landing"]["lat"] > 18.2
    assert payload["trajectory_artifact"]["landing_uncertainty_sigma_m"] > 0.0
    assert payload["trajectory_artifact"]["sondehub_reference"] is None


def test_execute_tool_normalizes_json_response(monkeypatch) -> None:
    from mcp_servers import sondehub_server

    async def fake_run(payload: dict[str, object]) -> str:
        assert payload == {"launch_lat": 18.2}
        return '{"status":"success","source":"sondehub-tawhiri"}'

    monkeypatch.setattr(sondehub_server, "run_sondehub_simulation_payload", fake_run)

    payload = json.loads(
        asyncio.run(llm.execute_tool("sondehub_run_simulation", {"launch_lat": 18.2}))
    )

    assert payload == {"status": "success", "source": "sondehub-tawhiri"}


def test_execute_tool_normalizes_error_string(monkeypatch) -> None:
    from mcp_servers import sondehub_server

    async def fake_run(_: dict[str, object]) -> str:
        return "Error loading SondeHub data: RuntimeError: boom"

    monkeypatch.setattr(sondehub_server, "run_sondehub_simulation_payload", fake_run)

    payload = json.loads(asyncio.run(llm.execute_tool("sondehub_run_simulation", {})))

    assert payload["status"] == "error"
    assert payload["tool"] == "sondehub_run_simulation"
    assert "boom" in payload["message"]


def test_execute_tool_rejects_non_json_string(monkeypatch) -> None:
    from mcp_servers import sondehub_server

    async def fake_run(_: dict[str, object]) -> str:
        return "plain text output"

    monkeypatch.setattr(sondehub_server, "run_sondehub_simulation_payload", fake_run)

    payload = json.loads(asyncio.run(llm.execute_tool("sondehub_run_simulation", {})))

    assert payload["status"] == "error"
    assert payload["tool"] == "sondehub_run_simulation"
    assert "non-JSON" in payload["message"]
