from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm import OpenAIProvider, execute_tool
from app.config import get_settings
from app.logging import configure_logging
from app.schemas import ChatRequest, ChatResponse


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

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


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    logger.info("Received chat message (%d chars)", len(payload.message))

    provider = OpenAIProvider()
    client = provider.get_client()

    messages: list[dict] = [
        {"role": "system", "content": provider.get_system_prompt()},
        {"role": "user", "content": payload.message},
    ]
    failed_tools: set[str] = set()
    last_tool_name = "llm"
    max_steps = 10
    seen_calls: set[tuple[str, str]] = set()

    for step in range(max_steps):
        logger.info("LLM step %d", step + 1)

        response = await client.chat.completions.create(
            model=provider.get_model(),
            messages=messages,
            tools=provider.get_tools(),
            tool_choice="auto",
        )

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
            if tool_name in failed_tools:
                logger.warning("Skipping repeated failed tool: %s", tool_name)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({
                        "error": f"{tool_name} previously failed. Do not retry."
                    })
                })

                continue
            

            try:
                tool_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                logger.exception("Invalid JSON arguments for tool %s", tool_name)
                return ChatResponse(
                    response=f"Tool call failed: invalid JSON arguments for {tool_name}.",
                    source="tool_error",
                )

            tool_key = (tool_name, json.dumps(tool_args, sort_keys=True))
            if tool_key in seen_calls:
                logger.warning("Duplicate tool call detected: %s %s", tool_name, tool_args)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "error": f"Duplicate tool call detected for {tool_name}. Do not retry with the same arguments. Provide the final answer."
                            }
                        ),
                    }
                )
                continue

            seen_calls.add(tool_key)

            logger.info("Tool requested: %s", tool_name)
            logger.info("Tool args: %s", tool_args)
            
            try:
                tool_result = await execute_tool(tool_name, tool_args)

                # execute_tool returns a JSON string, so inspect it
                try:
                    parsed_result = json.loads(tool_result)
                    if isinstance(parsed_result, dict) and parsed_result.get("error"):
                        logger.warning("Tool returned error payload: %s", tool_name)
                        failed_tools.add(tool_name)
                except json.JSONDecodeError:
                    # If it's not JSON, just leave it alone
                    parsed_result = None

            except Exception as e:
                logger.exception("Tool execution failed: %s", tool_name)
                failed_tools.add(tool_name)
                tool_result = json.dumps({"error": f"{tool_name} failed: {str(e)}"})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

    return ChatResponse(
        response="Tool-calling loop reached the maximum number of steps.",
        source="tool_loop_limit",
    )