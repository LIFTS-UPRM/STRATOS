from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


class FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="No tool call needed.", tool_calls=None)
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
