from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.logging import configure_logging
from app.schemas import ChatRequest, ChatResponse


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting %s in %s", settings.app_name, settings.app_env)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    logger.info("Received chat message (%d chars)", len(payload.message))
    return ChatResponse(
        response="This is a mock response from STRATOS backend.",
        source="mock",
    )
