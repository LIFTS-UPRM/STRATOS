from __future__ import annotations

import json
from typing import Any


INSTRUCTION_LIKE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ignore_previous", "ignore previous"),
    ("ignore_above", "ignore above"),
    ("system_prompt_reference", "system prompt"),
    ("developer_message_reference", "developer message"),
    ("persona_reset", "you are now"),
    ("tool_call_instruction", "call the tool"),
    ("tool_choice_reference", "tool_choice"),
    ("function_call_reference", "function call"),
    ("xml_system_tag", "<system>"),
    ("xml_assistant_tag", "<assistant>"),
)

QUARANTINED_PAYLOAD = "[quarantined]"
QUARANTINED_ROOT_PATH = "$"
RETRIEVED_CONTEXT_EXCERPT_LIMIT = 200


def _serialize_envelope(envelope: dict[str, Any]) -> str:
    return json.dumps(envelope, sort_keys=True, default=str)


def _make_excerpt(text: str, limit: int = RETRIEVED_CONTEXT_EXCERPT_LIMIT) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip()


def detect_instruction_like_text(text: str) -> list[str]:
    lowered = text.casefold()
    return [code for code, needle in INSTRUCTION_LIKE_PATTERNS if needle in lowered]


def _format_untrusted_text_message(
    *,
    role: str,
    source: str,
    kind: str,
    content: str,
) -> dict[str, str]:
    return {
        "role": role,
        "content": _serialize_envelope(
            {
                "source": source,
                "trust": "untrusted",
                "kind": kind,
                "content": content.strip(),
            }
        ),
    }


def format_client_history_message(*, role: str, content: str) -> dict[str, str]:
    return _format_untrusted_text_message(
        role="user",
        source=f"client_history_{role}",
        kind="transcript",
        content=content,
    )


def format_current_user_message(text: str) -> dict[str, str]:
    return _format_untrusted_text_message(
        role="user",
        source="current_user",
        kind="user_input",
        content=text,
    )


def _sanitize_tool_payload(payload: Any, *, path: str = QUARANTINED_ROOT_PATH) -> tuple[Any, list[str]]:
    if isinstance(payload, str):
        if detect_instruction_like_text(payload):
            return QUARANTINED_PAYLOAD, [path]
        return payload, []

    if isinstance(payload, list):
        sanitized_items: list[Any] = []
        quarantined_fields: list[str] = []
        for index, item in enumerate(payload):
            sanitized_item, item_fields = _sanitize_tool_payload(item, path=f"{path}[{index}]")
            sanitized_items.append(sanitized_item)
            quarantined_fields.extend(item_fields)
        return sanitized_items, quarantined_fields

    if isinstance(payload, dict):
        sanitized_payload: dict[str, Any] = {}
        quarantined_fields: list[str] = []
        for key, value in payload.items():
            sanitized_value, value_fields = _sanitize_tool_payload(
                value,
                path=f"{path}.{key}",
            )
            sanitized_payload[key] = sanitized_value
            quarantined_fields.extend(value_fields)
        return sanitized_payload, quarantined_fields

    return payload, []


def format_tool_output_message(
    *,
    tool_call_id: str,
    tool_name: str,
    raw_result: str,
) -> dict[str, str]:
    try:
        parsed_payload = json.loads(raw_result)
    except json.JSONDecodeError:
        parsed_payload = raw_result

    sanitized_payload, quarantined_fields = _sanitize_tool_payload(parsed_payload)
    quarantined_fields = sorted(quarantined_fields)
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": _serialize_envelope(
            {
                "source": "tool_output",
                "trust": "untrusted",
                "tool_name": tool_name,
                "kind": "tool_result",
                "payload": sanitized_payload,
                "quarantined_fields": quarantined_fields,
            }
        ),
    }


def format_retrieved_context(*, document_id: str, text: str) -> str:
    stripped_text = text.strip()
    reason_codes = detect_instruction_like_text(stripped_text)
    status = "quarantined" if reason_codes else "accepted"
    content = _make_excerpt(stripped_text) if status == "quarantined" else stripped_text
    return _serialize_envelope(
        {
            "source": "retrieved_document",
            "trust": "untrusted",
            "kind": "grounding_context",
            "document_id": document_id,
            "status": status,
            "reason_codes": reason_codes,
            "content": content,
        }
    )
