"""Entry point: run the stateless Streamable HTTP MCP server.

Usage::

    python -m pet_hospital_mcp
    pet-hospital-mcp

Environment:
    MCP_HOST (default 127.0.0.1)
    MCP_PORT (default 8000)
    MCP_PATH (default /mcp)
    PET_HOSPITAL_BASE_URL (default http://127.0.0.1:8080)
    PET_HOSPITAL_TIMEOUT_SECONDS (default 5.0)
    PET_HOSPITAL_MAX_RETRIES (default 2)
    PET_HOSPITAL_LOG_LEVEL (default INFO)
"""

from __future__ import annotations

from .config import Settings
from .logging_config import setup_logging
from .server import create_server


def main() -> None:
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    server = create_server(settings)
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_path,
        json_response=False,
        stateless_http=True,
        # Stateless mode owns no sessions; explicitly disable the (unused)
        # stateful-session knobs so no session storage / expiry is configured.
        session_idle_timeout=None,
        max_sessions=None,
    )


if __name__ == "__main__":
    main()
