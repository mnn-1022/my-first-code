"""Assembly of the MCP server: tools, middleware and the ``/health`` endpoint.

This module builds an :class:`mcp.server.mcpserver.MCPServer` (SDK 2.x — never
``FastMCP``) that is meant to run over the **stateless** Streamable HTTP
transport (protocol ``2026-07-28``): no ``initialize`` handshake, no
``Mcp-Session-Id``, no session storage / expiry, no ``max_sessions`` and no
stateful SSE recovery.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import Settings
from .logging_config import get_logger
from .rest_client import RestClient
from .tools import (
    TOOL_DESCRIPTION,
    list_pets,
    set_rest_client,
    validate_tool_call_arguments,
)

SERVICE_NAME = "pet-hospital-mcp"
SERVICE_VERSION = "0.1.0"

logger = get_logger("pet_hospital_mcp.server")


def _health_payload(settings: Settings) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "backend": settings.pet_hospital_base_url,
    }


def create_server(settings: Settings, rest_client: "RestClient | None" = None) -> MCPServer:
    """Build a fully configured ``MCPServer``.

    Args:
        settings: Runtime configuration (host/port/base URL/timeouts/log level).
        rest_client: Optional pre-built REST client. Injected in tests so the
            tool talks to a mocked backend; when omitted one is built from
            ``settings``.

    Returns:
        An un-run ``MCPServer``. Call ``run(transport="streamable-http", ...)``
        or mount ``server.streamable_http_app(...)`` to serve it.
    """
    server = MCPServer(
        name=SERVICE_NAME,
        title="Pet Hospital MCP Server",
        description="Stateless MCP service exposing the Go Pet Hospital REST API to AI agents.",
        instructions=(
            "Browse the pet hospital register through the list_pets tool. "
            "All results mirror the Go REST API's data payload."
        ),
        version=SERVICE_VERSION,
    )

    # Wire the shared REST client into the tool layer.
    if rest_client is None:
        rest_client = RestClient(
            settings.pet_hospital_base_url,
            timeout_seconds=settings.backend_timeout_seconds,
            max_retries=settings.backend_max_retries,
        )
    set_rest_client(rest_client)

    # Reject unknown / invalid tool arguments with a clean unified error before
    # the SDK's auto-generated argument model strips or re-renders them.
    server.middleware.append(validate_tool_call_arguments)

    # Register the only phase-1 tool.
    server.add_tool(list_pets, description=TOOL_DESCRIPTION)

    # Health check endpoint (kept per project requirements).
    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(_health_payload(settings))

    logger.info(
        "server built",
        extra={
            "tool_name": "server",
            "params": {"base_url": settings.pet_hospital_base_url, "service": SERVICE_NAME},
            "status": "ok",
            "duration_ms": 0.0,
        },
    )
    return server
