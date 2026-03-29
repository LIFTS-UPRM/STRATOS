from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    log_level: str
    host: str
    port: int
    llm_api_key: str
    llm_model: str
    faa_client_id: str
    faa_client_secret: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "STRATOS Backend"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        faa_client_id=os.getenv("FAA_CLIENT_ID", ""),
        faa_client_secret=os.getenv("FAA_CLIENT_SECRET", ""),
    )
