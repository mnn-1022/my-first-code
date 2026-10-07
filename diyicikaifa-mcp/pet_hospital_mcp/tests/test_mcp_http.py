"""SDK 2.x stateless Streamable HTTP connection flow (protocol 2026-07-28).

Verifies that the server:
- uses ``server/discover`` and per-request envelopes (no legacy ``initialize``);
- never requires or returns ``Mcp-Session-Id`` (no session storage);
- serves ``/health``;
- exposes ``list_pets`` through the HTTP MCP endpoint.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    LATEST_MODERN_VERSION,
    mcp_headers,
    mcp_post,
    parse_jsonrpc,
)


@pytest.mark.asyncio
async def test_server_discover_modern_protocol(mcp_base_url):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(client, mcp_base_url, "server/discover", id_=1)
    assert response.status_code == 200, response.text
    result = parse_jsonrpc(response)["result"]
    assert LATEST_MODERN_VERSION in result["supportedVersions"]
    assert "tools" in result["capabilities"]
    # No session id is minted in stateless mode.
    headers = {k.lower(): v for k, v in response.headers.items()}
    assert "mcp-session-id" not in headers


@pytest.mark.asyncio
async def test_no_mcp_session_id_required(mcp_base_url):
    # Sending no Mcp-Session-Id header (and no session flow) must succeed.
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(client, mcp_base_url, "tools/list", id_=1)
    assert response.status_code == 200
    headers = {k.lower(): v for k, v in response.headers.items()}
    assert "mcp-session-id" not in headers


@pytest.mark.asyncio
async def test_health_endpoint(mcp_base_url):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{mcp_base_url}/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "pet-hospital-mcp"


@pytest.mark.asyncio
async def test_tools_list_discovers_list_pets(mcp_base_url):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(client, mcp_base_url, "tools/list", id_=1)
    assert response.status_code == 200
    tools = parse_jsonrpc(response)["result"]["tools"]
    assert any(t["name"] == "list_pets" for t in tools)


@pytest.mark.asyncio
async def test_tool_callable_over_http(mcp_base_url):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(
            client,
            mcp_base_url,
            "tools/call",
            params={"name": "list_pets", "arguments": {"species": "犬", "pageSize": 2}},
            name="list_pets",
            id_=1,
        )
    assert response.status_code == 200
    result = parse_jsonrpc(response)["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_legacy_initialize_not_required(mcp_base_url):
    """A modern stateless client never needs the legacy ``initialize`` handshake.

    We exercise a normal tools/list call (no initialize anywhere in the flow)
    and confirm it succeeds, proving the server is not gated on the legacy
    handshake.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(client, mcp_base_url, "tools/list", id_=1)
    assert response.status_code == 200
    assert "result" in parse_jsonrpc(response)


@pytest.mark.asyncio
async def test_wrong_routing_header_rejected(mcp_base_url):
    """The modern path enforces the ``Mcp-Method`` routing header."""
    headers = mcp_headers("server/discover")
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{mcp_base_url}/mcp",
            headers=headers,  # body method differs from header
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": LATEST_MODERN_VERSION,
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            },
        )
    assert response.status_code == 400
    error = parse_jsonrpc(response)["error"]
    assert error["message"].startswith("mcp-method header")
