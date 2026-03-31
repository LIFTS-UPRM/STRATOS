"""LLM provider abstraction — OpenAI implementation.

Exports:
  ALL_TOOLS         — merged OpenAI function-calling tool schema list
  SYSTEM_PROMPT     — Agent system prompt
  execute_tool(name, input) — dispatches to all MCP tool functions
  LLMProvider       — abstract base class
  OpenAIProvider    — OpenAI implementation
"""
from __future__ import annotations

import abc
import json
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings

# ── Tool schemas ──────────────────────────────────────────────────────────────

WEATHER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_surface_weather",
            "description": (
                "Fetch surface weather conditions and GO/CAUTION/NO-GO launch assessment "
                "for a site. Returns hourly conditions for the forecast window: wind speed, "
                "gusts, cloud cover, precipitation probability, CAPE, visibility. "
                "Always call this before recommending a launch window."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude":       {"type": "number",  "description": "Launch site latitude (-90 to 90)"},
                    "longitude":      {"type": "number",  "description": "Launch site longitude (-180 to 180)"},
                    "forecast_hours": {"type": "integer", "description": "Hours ahead to forecast (1-72)", "default": 24},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_winds_aloft",
            "description": (
                "Fetch winds aloft profile at 9 pressure levels (1000-200 hPa) for a "
                "launch site at a specific forecast time. Returns u/v components, wind "
                "speed/direction, altitude mapping, and jet stream alerts (>40 m/s). "
                "Use when upper-level wind patterns affect trajectory planning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude":          {"type": "number", "description": "Launch site latitude"},
                    "longitude":         {"type": "number", "description": "Launch site longitude"},
                    "forecast_datetime": {
                        "type": "string",
                        "description": "ISO 8601 datetime for the forecast (e.g. '2026-03-15T12:00:00Z')",
                    },
                },
                "required": ["latitude", "longitude", "forecast_datetime"],
            },
        },
    },
]

NOTAM_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_notam_airspace",
            "description": (
                "Check NOTAMs for balloon launch airspace using FAA + AviationWeather.gov. "
                "Returns relevant NOTAMs and clearance status: NO_CRITICAL_ALERTS, "
                "REVIEW_REQUIRED, or MANUAL_CHECK_REQUIRED. "
                "Call this when the user asks about airspace safety or launch clearance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude":        {"type": "number", "description": "Launch site latitude"},
                    "longitude":       {"type": "number", "description": "Launch site longitude"},
                    "radius_km":       {"type": "number", "description": "Search radius in km (default 25)", "default": 25},
                    "launch_datetime": {"type": "string", "description": "ISO 8601 launch datetime"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
]

TRAJECTORY_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "predict_standard",
            "description": (
                "Predict a high-altitude balloon trajectory using Tawhiri (NOAA GFS winds). "
                "Returns full flight path, burst/landing coordinates, water landing flag, "
                "and direct SharePoint-sourced file links when relevant. "
                "Call this to show where the balloon will land. "
                "Wind data is fetched automatically — do not call get_winds_aloft first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "launch_latitude":  {"type": "number", "description": "Launch latitude (-90 to 90)"},
                    "launch_longitude": {"type": "number", "description": "Launch longitude (-180 to 180)"},
                    "launch_datetime":  {"type": "string", "description": "ISO 8601 / RFC3339 launch datetime (e.g. '2026-03-19T12:00:00Z')"},
                    "ascent_rate":      {"type": "number", "description": "Ascent rate in m/s (typical: 4–6)"},
                    "burst_altitude":   {"type": "number", "description": "Burst altitude in metres (typical: 25000–35000)"},
                    "descent_rate":     {"type": "number", "description": "Descent rate in m/s (typical: 6–9)"},
                    "launch_altitude":  {"type": "number", "description": "Launch site altitude in metres ASL (default 0)", "default": 0.0},
                },
                "required": [
                    "launch_latitude", "launch_longitude", "launch_datetime",
                    "ascent_rate", "burst_altitude", "descent_rate",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_check",
            "description": "Check that the trajectory service is configured and reachable.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_supported_profiles",
            "description": "List supported trajectory profiles and their required input fields.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

HELIUM_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "calculate_helium",
            "description": "Calculate helium fill parameters (neck lift, volume, burst altitude, flight time) for a balloon+payload combination. Returns GO/MARGINAL/NO-GO recommendation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "balloon_model": {
                        "type": "string",
                        "description": "Balloon model ID (e.g. TX1000, H1200, KCI-1000). Call list_balloon_models for options."
                    },
                    "payload_mass_g": {
                        "type": "number",
                        "description": "Total payload mass in grams including tracker, camera, and box."
                    },
                    "target_ascent_rate_ms": {
                        "type": "number",
                        "description": "Target ascent rate in m/s. Default 5.0."
                    },
                    "surface_temp_c": {
                        "type": "number",
                        "description": "Surface temperature at launch site in Celsius. Default 15."
                    }
                },
                "required": ["balloon_model", "payload_mass_g"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_balloons",
            "description": "Compare multiple balloon models and rank by altitude/helium efficiency. Use when user wants to choose between balloon options.",
            "parameters": {
                "type": "object",
                "properties": {
                    "models": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of balloon model IDs to compare."
                    },
                    "payload_mass_g": {
                        "type": "number",
                        "description": "Total payload mass in grams."
                    },
                    "target_ascent_rate_ms": {"type": "number", "description": "Target ascent rate in m/s. Default 5.0."},
                    "surface_temp_c": {"type": "number", "description": "Surface temp in Celsius. Default 15."}
                },
                "required": ["models", "payload_mass_g"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_documents",
            "description": "Semantically search the user's uploaded documents for information relevant to the query. Returns ranked text chunks with source attribution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query."
                    },
                    "folder_path": {
                        "type": "string",
                        "description": "Optional folder path to scope the search (e.g. 'missions/2026'). Omit to search all documents."
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Maximum number of chunks to return (default 5, max 10)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_balloon_models",
            "description": "List all available balloon models with their specs. Call this before calculate_helium or compare_balloons to see valid model IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "manufacturer": {
                        "type": "string",
                        "description": "Optional filter by manufacturer name (e.g. 'Totex', 'Hwoyee', 'Kaymont')."
                    }
                },
                "required": []
            }
        }
    },
]

ALL_TOOLS = WEATHER_TOOLS + NOTAM_TOOLS + TRAJECTORY_TOOLS + HELIUM_TOOLS


def get_tools() -> list[dict]:
    """Return the full list of tool schemas."""
    return ALL_TOOLS

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are LIFTOFF Agent, an AI mission planning assistant for weather balloon operations.

When a user asks about a launch location or conditions, use your tools to retrieve data \
and return a clear, structured mission brief.

Guidelines:
- Always call get_surface_weather before recommending a launch window.
- Call get_winds_aloft when the user needs upper-level wind patterns or trajectory context.
- Call check_notam_airspace when the user asks about airspace clearance or launch safety.
- Call predict_standard to compute the predicted balloon trajectory. \
  Wind data is fetched automatically from NOAA GFS — do not call get_winds_aloft before predict_standard.
- Lead with the overall GO / CAUTION / NO-GO recommendation.
- Explicitly name threshold violations (e.g., "Surface wind 8.2 m/s — CAUTION threshold: 7.0 m/s").
- Report NOTAM clearance_status clearly; MANUAL_CHECK_REQUIRED always requires human review.
- Include observation_links and sondehub_links from tool results at the end of your response.
- Be concise. Use short paragraphs and bullet points.
"""

# ── Tool dispatcher ───────────────────────────────────────────────────────────

async def execute_tool(name: str, tool_input: dict) -> str:
    """Execute any named tool and return a JSON string result."""
    from mcp_servers.weather_server    import get_surface_weather, get_winds_aloft
    # from mcp_servers.notam_server      import check_notam_airspace
    from mcp_servers.trajectory.server import predict_standard, health_check, get_supported_profiles

    if name == "get_surface_weather":
        result = await get_surface_weather(**tool_input)

    elif name == "get_winds_aloft":
        result = await get_winds_aloft(**tool_input)

    elif name == "check_notam_airspace":
        #     faa_client_secret=s.faa_client_secret,
        # )
        result = {
        "clearance_status": "MANUAL_CHECK_REQUIRED",
        "summary": "NOTAM check disabled in development. FAA credentials not configured.",
        "notams": [],
        "source": "mock_notam_dev"
    }

    elif name == "predict_standard":
        result = await predict_standard(**tool_input)

    elif name == "health_check":
        result = await health_check()

    elif name == "get_supported_profiles":
        result = await get_supported_profiles()

    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result)


# ── Provider abstraction ──────────────────────────────────────────────────────

class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def get_client(self) -> Any: ...

    @abc.abstractmethod
    def get_model(self) -> str: ...

    @abc.abstractmethod
    def get_tools(self) -> list[dict]: ...

    @abc.abstractmethod
    def get_system_prompt(self) -> str: ...


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(api_key=s.llm_api_key)
        self._model  = s.llm_model

    def get_client(self) -> AsyncOpenAI:
        return self._client

    def get_model(self) -> str:
        return self._model

    def get_tools(self) -> list[dict]:
        return ALL_TOOLS

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT
