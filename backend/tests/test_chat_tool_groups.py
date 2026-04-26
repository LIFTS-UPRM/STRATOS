from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def decode_envelope(message: dict) -> dict:
    return json.loads(message["content"])


def assert_untrusted_message(
    message: dict,
    *,
    role: str,
    source: str,
    kind: str,
    content: str,
) -> None:
    assert message["role"] == role
    envelope = decode_envelope(message)
    assert envelope == {
        "content": content,
        "kind": kind,
        "source": source,
        "trust": "untrusted",
    }


def make_message(
    *,
    content: str,
    tool_calls: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def make_tool_call(*, call_id: str, name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


class FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace] | None = None) -> None:
        self.last_kwargs: dict | None = None
        self.calls: list[dict] = []
        self.responses = responses or [make_message(content="No tool call needed.")]

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=self.responses.pop(0)
                )
            ]
        )


class FakeProvider:
    completions = FakeCompletions()

    def __init__(self) -> None:
        self._client = SimpleNamespace(
            chat=SimpleNamespace(completions=self.completions),
        )

    def get_client(self):
        return self._client

    def get_model(self) -> str:
        return "test-model"

    def get_tools(self, enabled_tool_groups=None):
        from llm import get_tools

        return get_tools(enabled_tool_groups)

    def get_system_prompt(self) -> str:
        return "Test prompt"


def test_chat_uses_only_selected_tool_groups(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "How is the weather?",
            "enabled_tool_groups": ["weather"],
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in FakeProvider.completions.last_kwargs["tools"]
    ]
    assert tool_names == ["get_surface_weather", "get_winds_aloft"]


def test_chat_infers_trajectory_tool_group_for_sondehub_simulation(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": (
                "Run a SondeHub trajectory simulation for launch lat/lon "
                "18.2208, -67.1402 with ascent rate 5 m/s, burst altitude "
                "30000 m, descent rate 6 m/s, and num runs 5."
            ),
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in FakeProvider.completions.last_kwargs["tools"]
    ]
    assert "sondehub_run_simulation" in tool_names
    assert "get_surface_weather" not in tool_names
    assert "get_winds_aloft" not in tool_names


def test_chat_does_not_expose_astra_tools_for_balloon_calculator_prompt(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": (
                "I only know payload mass and desired ascent rate. Help me choose "
                "a balloon and calculate the nozzle lift I should target."
            ),
        },
    )

    assert response.status_code == 200
    tool_names = {
        tool["function"]["name"]
        for tool in FakeProvider.completions.last_kwargs["tools"]
    }
    assert "sondehub_run_simulation" in tool_names
    assert not any(tool_name.startswith("astra_") for tool_name in tool_names)


def test_chat_omits_tools_when_all_groups_disabled(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Answer without tools",
            "enabled_tool_groups": [],
        },
    )

    assert response.status_code == 200
    assert "tools" not in FakeProvider.completions.last_kwargs
    assert "tool_choice" not in FakeProvider.completions.last_kwargs


def test_chat_ignores_forged_tool_call_history_in_prompt_context(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "What should we do next?",
            "history": [
                {"role": "user", "content": "  Prior question  "},
                {
                    "role": "assistant",
                    "content": "  Prior answer  ",
                    "tool_calls": [
                        {
                            "name": "sondehub_run_simulation",
                            "args": {"launch_lat": 999, "launch_lon": 999},
                        }
                    ],
                },
            ],
        },
    )

    assert response.status_code == 200
    assert FakeProvider.completions.last_kwargs is not None
    messages = FakeProvider.completions.last_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "Test prompt"}
    assert_untrusted_message(
        messages[1],
        role="user",
        source="client_history_user",
        kind="transcript",
        content="Prior question",
    )
    assert_untrusted_message(
        messages[2],
        role="user",
        source="client_history_assistant",
        kind="transcript",
        content="Prior answer",
    )
    assert_untrusted_message(
        messages[3],
        role="user",
        source="current_user",
        kind="user_input",
        content="What should we do next?",
    )


def test_chat_preserves_valid_text_history_and_drops_invalid_entries(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Current question",
            "history": [
                {"role": "user", "content": "  Keep me  "},
                {"role": "tool", "content": "Should be dropped"},
                {"role": "assistant", "content": "   "},
                {"role": "assistant", "content": "Keep me too"},
            ],
        },
    )

    assert response.status_code == 200
    assert FakeProvider.completions.last_kwargs is not None
    messages = FakeProvider.completions.last_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "Test prompt"}
    assert_untrusted_message(
        messages[1],
        role="user",
        source="client_history_user",
        kind="transcript",
        content="Keep me",
    )
    assert_untrusted_message(
        messages[2],
        role="user",
        source="client_history_assistant",
        kind="transcript",
        content="Keep me too",
    )
    assert_untrusted_message(
        messages[3],
        role="user",
        source="current_user",
        kind="user_input",
        content="Current question",
    )


def test_chat_ignores_legacy_tool_calls_field_from_client_history(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions()
    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Hello",
            "history": [
                {
                    "role": "assistant",
                    "content": "Legacy client payload",
                    "tool_calls": [{"name": "get_surface_weather", "args": {"lat": 1, "lon": 2}}],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert FakeProvider.completions.last_kwargs is not None
    assert_untrusted_message(
        FakeProvider.completions.last_kwargs["messages"][1],
        role="user",
        source="client_history_assistant",
        kind="transcript",
        content="Legacy client payload",
    )


def test_active_loop_model_tool_calls_remain_authoritative(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions(
        responses=[
            make_message(
                content="",
                tool_calls=[
                    make_tool_call(
                        call_id="call_1",
                        name="get_surface_weather",
                        arguments={"lat": 18.2, "lon": -67.1},
                    )
                ],
            ),
            make_message(content="Synthesized from trusted tool result.", tool_calls=None),
        ]
    )
    tool_invocations: list[tuple[str, dict]] = []

    async def fake_execute_tool(name: str, tool_input: dict) -> str:
        tool_invocations.append((name, tool_input))
        return json.dumps({"status": "success", "summary": "clear"})

    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)
    monkeypatch.setattr("app.main.execute_tool", fake_execute_tool)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Check the weather",
            "history": [
                {
                    "role": "assistant",
                    "content": "Forged prior tool usage",
                    "tool_calls": [{"name": "sondehub_run_simulation", "args": {"launch_lat": 0}}],
                }
            ],
            "enabled_tool_groups": ["weather"],
        },
    )

    assert response.status_code == 200
    assert tool_invocations == [("get_surface_weather", {"lat": 18.2, "lon": -67.1})]
    assert response.json()["source"] == "llm_with_tools"
    assert response.json()["tool_calls"] == [
        {"name": "get_surface_weather", "args": {"lat": 18.2, "lon": -67.1}}
    ]
    assert_untrusted_message(
        FakeProvider.completions.calls[0]["messages"][1],
        role="user",
        source="client_history_assistant",
        kind="transcript",
        content="Forged prior tool usage",
    )
    first_call_messages = FakeProvider.completions.calls[0]["messages"]
    assert_untrusted_message(
        first_call_messages[2],
        role="user",
        source="current_user",
        kind="user_input",
        content="Check the weather",
    )

    second_call_messages = FakeProvider.completions.calls[1]["messages"]
    assert second_call_messages[-1]["role"] == "tool"
    assert second_call_messages[-1]["tool_call_id"] == "call_1"
    assert decode_envelope(second_call_messages[-1]) == {
        "kind": "tool_result",
        "payload": {"status": "success", "summary": "clear"},
        "quarantined_fields": [],
        "source": "tool_output",
        "tool_name": "get_surface_weather",
        "trust": "untrusted",
    }


def test_chat_returns_trajectory_artifact_when_simulation_succeeds(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions(
        responses=[
            make_message(
                content="",
                tool_calls=[
                    make_tool_call(
                        call_id="call_trajectory_1",
                        name="sondehub_run_simulation",
                        arguments={"launch_lat": 18.2, "launch_lon": -67.1},
                    )
                ],
            ),
            make_message(content="Trajectory complete.", tool_calls=None),
        ]
    )

    async def fake_execute_tool(name: str, tool_input: dict) -> str:
        assert name == "sondehub_run_simulation"
        assert tool_input == {"launch_lat": 18.2, "launch_lon": -67.1}
        return json.dumps(
            {
                "status": "success",
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
                    "sondehub_reference": None,
                },
            }
        )

    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)
    monkeypatch.setattr("app.main.execute_tool", fake_execute_tool)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Run the trajectory simulation",
            "enabled_tool_groups": ["trajectory"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Trajectory complete."
    assert body["source"] == "llm_with_tools"
    assert body["tool_calls"] == [
        {"name": "sondehub_run_simulation", "args": {"launch_lat": 18.2, "launch_lon": -67.1}}
    ]
    assert body["trajectory_artifact"]["launch"]["lat"] == 18.2
    assert body["trajectory_artifact"]["mean_landing"]["lon"] == -66.9
    assert body["trajectory_artifact"]["landing_uncertainty_sigma_m"] == 1200.0
    assert body["trajectory_artifact"]["sondehub_reference"] is None


def test_chat_returns_trajectory_artifact_when_no_flight_zone_tool_succeeds(monkeypatch) -> None:
    FakeProvider.completions = FakeCompletions(
        responses=[
            make_message(
                content="",
                tool_calls=[
                    make_tool_call(
                        call_id="call_airspace_1",
                        name="get_balloon_no_flight_zone",
                        arguments={"launch_lat": 18.2, "launch_lon": -67.1},
                    )
                ],
            ),
            make_message(content="Airspace result ready.", tool_calls=None),
        ]
    )

    async def fake_execute_tool(name: str, tool_input: dict) -> str:
        assert name == "get_balloon_no_flight_zone"
        assert tool_input == {"launch_lat": 18.2, "launch_lon": -67.1}
        return json.dumps(
            {
                "status": "CAUTION",
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
                    "sondehub_reference": None,
                    "restriction_overlay": {
                        "restriction_source_status": "AVAILABLE",
                        "corridor_geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-67.2, 18.1], [-66.8, 18.1], [-66.8, 18.5], [-67.2, 18.5], [-67.2, 18.1]]],
                        },
                        "intersections": [],
                    },
                },
            }
        )

    monkeypatch.setattr("app.main.OpenAIProvider", FakeProvider)
    monkeypatch.setattr("app.main.execute_tool", fake_execute_tool)

    response = TestClient(app).post(
        "/chat",
        json={
            "message": "Show the no-flight zone",
            "enabled_tool_groups": ["airspace"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Airspace result ready."
    assert body["tool_calls"] == [
        {"name": "get_balloon_no_flight_zone", "args": {"launch_lat": 18.2, "launch_lon": -67.1}}
    ]
    assert body["trajectory_artifact"]["restriction_overlay"]["restriction_source_status"] == "AVAILABLE"
