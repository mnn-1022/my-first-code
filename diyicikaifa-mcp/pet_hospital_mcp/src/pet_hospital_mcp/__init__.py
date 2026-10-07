"""Pet Hospital MCP service.

A stateless MCP server (protocol ``2026-07-28``) that exposes the Go Pet
Hospital REST API to AI agents through the official MCP Python SDK 2.x
``MCPServer`` over Streamable HTTP.

This package deliberately does **not** use ``mcp.server.fastmcp.FastMCP`` and
does **not** implement the legacy ``initialize`` handshake, ``Mcp-Session-Id``
session storage or stateful SSE recovery.
"""

__version__ = "0.1.0"
