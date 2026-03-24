# backend/mcp_servers/trajectory/tawhiri_client.py
"""Async HTTP client for the self-hosted Tawhiri trajectory API."""
from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import get_settings
from .errors import TawhiriError

logger = logging.getLogger(__name__)


async def call_tawhiri(params: dict) -> dict:
    """GET {TAWHIRI_BASE_URL}/api/v1/ with the given query params.

    Args:
        params: Tawhiri query parameters (built by normalizers.to_tawhiri_params).

    Returns:
        Parsed JSON response dict (contains 'prediction' key).

    Raises:
        TawhiriError: On missing config, HTTP errors, timeouts, or malformed response.
    """
    settings = get_settings()
    base_url = settings.tawhiri_base_url
    timeout = settings.tawhiri_timeout

    if not base_url:
        raise TawhiriError("TAWHIRI_BASE_URL is not configured")

    logger.info("Tawhiri request params: %s", params)
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}/api/v1/", params=params)
    except httpx.TimeoutException as exc:
        raise TawhiriError(f"Tawhiri request timed out after {timeout}s") from exc
    except httpx.RequestError as exc:
        raise TawhiriError(f"Tawhiri network error: {exc}") from exc

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Tawhiri response: status=%d elapsed=%.1fms",
        response.status_code,
        elapsed_ms,
    )

    if response.status_code >= 400:
        raise TawhiriError(
            f"Tawhiri returned {response.status_code}: {response.text}",
            status_code=response.status_code,
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise TawhiriError("Tawhiri returned non-JSON response") from exc

    if "prediction" not in data:
        raise TawhiriError("Tawhiri response missing 'prediction' key")

    logger.info("Tawhiri trajectory: %d stages returned", len(data["prediction"]))
    return data
