"""Runtime configuration for the MCP service, sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_LOG_LEVEL = "INFO"


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    """Immutable service settings.

    All values can be overridden through environment variables so the service
    can be deployed without code changes.
    """

    mcp_host: str = DEFAULT_HOST
    mcp_port: int = DEFAULT_PORT
    mcp_path: str = DEFAULT_MCP_PATH
    pet_hospital_base_url: str = DEFAULT_BASE_URL
    backend_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    backend_max_retries: int = DEFAULT_MAX_RETRIES
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mcp_host=os.environ.get("MCP_HOST", DEFAULT_HOST),
            mcp_port=_get_int("MCP_PORT", DEFAULT_PORT),
            mcp_path=os.environ.get("MCP_PATH", DEFAULT_MCP_PATH),
            pet_hospital_base_url=os.environ.get("PET_HOSPITAL_BASE_URL", DEFAULT_BASE_URL),
            backend_timeout_seconds=_get_float("PET_HOSPITAL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
            backend_max_retries=_get_int("PET_HOSPITAL_MAX_RETRIES", DEFAULT_MAX_RETRIES),
            log_level=os.environ.get("PET_HOSPITAL_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )
