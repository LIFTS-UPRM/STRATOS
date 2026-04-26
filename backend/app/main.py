from __future__ import annotations

import asyncio
import json
import logging

from pydantic import ValidationError
from fastapi import FastAPI, HTTPException, Request, status

from fastapi.middleware.cors import CORSMiddleware

from app.prompt_assembly import (
    format_client_history_message,
    format_current_user_message,
    format_tool_output_message,
)
from llm import OpenAIProvider, execute_tool
from app.config import get_settings
from app.logging import configure_logging
from app.schemas import (
    CHAT_HISTORY_MAX_ITEMS,
    CHAT_HISTORY_MESSAGE_MAX_CHARS,
    CHAT_MESSAGE_MAX_CHARS,
    CHAT_PAYLOAD_MAX_BYTES,
    CHAT_PAYLOAD_MAX_DEPTH,
    ChatHistoryMessage,
    ChatRequest,
    ChatResponse,
    TrajectoryArtifact,
    ToolCallRecord,
)


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
ALLOWED_HISTORY_ROLES = frozenset({"user", "assistant"})
TRAJECTORY_REQUEST_MARKERS = (
    "astra trajectory",
    "astra simulation",
    "sondehub",
    "trajectory simulation",
    "trajectory analysis",
    "run astra",
    "run sondehub",
    "run a trajectory",
    "landing prediction",
    "landing area",
    "num runs",
    "burst altitude",
    "descent rate",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting %s in %s", settings.app_name, settings.app_env)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = CHAT_PAYLOAD_MAX_BYTES + 1

        if declared_size > CHAT_PAYLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": "Chat request payload is too large.",
                    "limit_bytes": CHAT_PAYLOAD_MAX_BYTES,
                },
            )

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > CHAT_PAYLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": "Chat request payload is too large.",
                    "limit_bytes": CHAT_PAYLOAD_MAX_BYTES,
                },
            )

    return bytes(body)


def _within_json_depth(value: object) -> bool:
    stack = [(value, 1)]

    while stack:
        current, depth = stack.pop()
        if depth > CHAT_PAYLOAD_MAX_DEPTH:
            return False

        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)

    return True


async def _parse_chat_request(request: Request) -> ChatRequest:
    raw_body = await _read_limited_body(request)

    try:
        raw_payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Chat request body must be valid JSON."},
        ) from exc
    except RecursionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Chat request JSON is too deeply nested."},
        ) from exc

    if not isinstance(raw_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Chat request body must be a JSON object."},
        )

    if not _within_json_depth(raw_payload):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Chat request JSON is too deeply nested.",
                "limit_depth": CHAT_PAYLOAD_MAX_DEPTH,
            },
        )

    try:
        return ChatRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Invalid chat request.",
                "details": exc.errors(),
            },
        ) from exc


def _sanitize_history_message(message: ChatHistoryMessage) -> dict[str, str] | None:
    if message.role not in ALLOWED_HISTORY_ROLES:
        return None

    content = message.content.strip()
    if not content:
        return None

    return {"role": message.role, "content": content}

def _infer_enabled_tool_groups(message: str) -> list[str] | None:
    normalized = message.casefold()
    if any(marker in normalized for marker in TRAJECTORY_REQUEST_MARKERS):
        return ["trajectory"]
    return None

@app.post(
    "/chat",
    response_model=ChatResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["message"],
                        "properties": {
                            "message": {
                                "type": "string",
                                "maxLength": CHAT_MESSAGE_MAX_CHARS,
                            },
                            "history": {
                                "type": "array",
                                "maxItems": CHAT_HISTORY_MAX_ITEMS,
                                "items": {
                                    "type": "object",
                                    "required": ["role", "content"],
                                    "properties": {
                                        "role": {
                                            "type": "string",
                                            "enum": ["user", "assistant"],
                                        },
                                        "content": {
                                            "type": "string",
                                            "maxLength": CHAT_HISTORY_MESSAGE_MAX_CHARS,
                                        },
                                    },
                                },
                            },
                            "enabled_tool_groups": {
                                "type": "array",
                                "nullable": True,
                                "items": {
                                    "type": "string",
                                    "enum": ["trajectory", "weather", "airspace"],
                                },
                            },
                        },
                    },
                    "example": {
                        "message": "hello",
                        "history": [],
                        "enabled_tool_groups": [],
                    },
                }
            },
        }
    },
)

async def chat(request: Request) -> ChatResponse:
    payload = await _parse_chat_request(request)
    logger.info("Received chat message (%d chars)", len(payload.message))

    tool_calls_log: list[ToolCallRecord] = []
    trajectory_artifact: TrajectoryArtifact | None = None
    try:
        provider = OpenAIProvider()
        client = provider.get_client()

        messages: list[dict] = [{"role": "system", "content": provider.get_system_prompt()}]
        for history_message in payload.history:
            sanitized_message = _sanitize_history_message(history_message)
            if sanitized_message is not None:
                messages.append(format_client_history_message(**sanitized_message))

        messages.append(format_current_user_message(payload.message))
        enabled_tool_groups = payload.enabled_tool_groups
        if enabled_tool_groups is None:
            enabled_tool_groups = _infer_enabled_tool_groups(payload.message)
        last_tool_name = "llm"
        max_steps = 10
        seen_calls: set[tuple[str, str]] = set()
        # Any future cross-request replay must come from server-owned
        # TrustedConversationState, never from client-supplied history.

        for step in range(max_steps):
            logger.info("LLM step %d", step + 1)

            completion_kwargs = {
                "model": provider.get_model(),
                "messages": messages,
            }
            enabled_tools = provider.get_tools(enabled_tool_groups)
            if enabled_tools:
                completion_kwargs["tools"] = enabled_tools
                completion_kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**completion_kwargs)

            assistant_message = response.choices[0].message

            logger.info("Assistant content: %s", assistant_message.content)
            logger.info("Assistant tool calls: %s", assistant_message.tool_calls)

            # If no tool calls, we are done
            if not assistant_message.tool_calls:
                final_text = assistant_message.content or "No response returned."
                source = "llm_with_tools" if last_tool_name != "llm" else "llm"
                return ChatResponse(
                    response=final_text,
                    source=source,
                    tool_calls=tool_calls_log,
                    trajectory_artifact=trajectory_artifact,
                )

            # Append assistant tool-call message
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ],
                }
            )

            # Execute all requested tool calls
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                last_tool_name = tool_name
                try:
                    tool_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    logger.exception("Invalid JSON arguments for tool %s", tool_name)
                    return ChatResponse(
                        response=f"Tool call failed: invalid JSON arguments for {tool_name}.",
                        source="tool_error",
                        tool_calls=tool_calls_log,
                        trajectory_artifact=trajectory_artifact,
                    )

                tool_key = (tool_name, json.dumps(tool_args, sort_keys=True))
                if tool_key in seen_calls:
                    logger.warning("Duplicate tool call detected: %s %s", tool_name, tool_args)

                    messages.append(
                        format_tool_output_message(
                            tool_call_id=tool_call.id,
                            tool_name=tool_name,
                            raw_result=json.dumps(
                                {
                                    "error": (
                                        "Duplicate tool call detected for "
                                        f"{tool_name}. Do not retry with the same arguments. "
                                        "Provide the final answer."
                                    )
                                }
                            ),
                        )
                    )
                    continue

                seen_calls.add(tool_key)
                tool_calls_log.append(ToolCallRecord(name=tool_name, args=tool_args))

                logger.info("Tool requested: %s", tool_name)
                logger.info("Tool args: %s", tool_args)
                
                try:
                    # Use longer timeout for simulation tools (up to 2 minutes)
                    timeout = (
                        120
                        if tool_name in {"sondehub_run_simulation", "get_balloon_no_flight_zone"}
                        else 30
                    )
                    tool_result = await asyncio.wait_for(
                        execute_tool(tool_name, tool_args),
                        timeout=timeout
                    )

                    # execute_tool returns a JSON string, so inspect it
                    try:
                        parsed_result = json.loads(tool_result)
                        if isinstance(parsed_result, dict) and parsed_result.get("error"):
                            logger.warning("Tool returned error payload: %s", tool_name)
                        if (
                            isinstance(parsed_result, dict)
                            and parsed_result.get("trajectory_artifact")
                        ):
                            try:
                                trajectory_artifact = TrajectoryArtifact.model_validate(
                                    parsed_result["trajectory_artifact"]
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to parse trajectory artifact from %s",
                                    tool_name,
                                )
                    except json.JSONDecodeError:
                        # If it's not JSON, just leave it alone
                        parsed_result = None

                except asyncio.TimeoutError:
                    logger.warning("Tool execution timed out: %s", tool_name)
                    tool_result = json.dumps({"error": f"{tool_name} timed out after {timeout} seconds"})

                except Exception as e:
                    logger.exception("Tool execution failed: %s", tool_name)
                    tool_result = json.dumps({"error": f"{tool_name} failed: {str(e)}"})

                messages.append(
                    format_tool_output_message(
                        tool_call_id=tool_call.id,
                        tool_name=tool_name,
                        raw_result=tool_result,
                    )
                )

        return ChatResponse(
            response="Tool-calling loop reached the maximum number of steps.",
            source="tool_loop_limit",
            tool_calls=tool_calls_log,
            trajectory_artifact=trajectory_artifact,
        )

    except Exception as e:
        logger.exception("Unhandled error in chat endpoint")
        return ChatResponse(
            response=f"Server error: {str(e)}",
            source="error",
            tool_calls=tool_calls_log,
            trajectory_artifact=trajectory_artifact,
        )
