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


def test_astra_wrapper_import_smoke() -> None:
    from mcp_servers import astra_server

    assert astra_server.mcp is not None
    assert callable(astra_server.astra_run_simulation)


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
