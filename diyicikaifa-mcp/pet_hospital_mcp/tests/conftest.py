"""Shared pytest fixtures.

The fake Go backend is served through ``httpx.MockTransport`` inside the test
process, so tests never touch a real Go service. The MCP server under test runs
as an in-process ``uvicorn`` instance so the full stateless Streamable HTTP
flow (protocol ``2026-07-28``) is exercised end to end.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio
import uvicorn

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.rest_client import RestClient
from pet_hospital_mcp.server import create_server
from pet_hospital_mcp.tools import set_rest_client

LATEST_MODERN_VERSION = "2026-07-28"

ENVELOPE_META = {
    "io.modelcontextprotocol/protocolVersion": LATEST_MODERN_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
}


def _pet(item_id: str = "PET-000001", name: str = "旺财") -> Dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "species": "犬",
        "breed": "金毛",
        "gender": "公",
        "ageMonths": 36,
        "color": "金色",
        "chipNo": "CHIP-000001",
        "ownerName": "张三",
        "ownerPhone": "13800001111",
        "ownerAddr": "成都市武侯区",
        "doctor": "李医生",
        "disease": "急性肠胃炎",
        "status": "待就诊",
        "allergy": "无",
        "note": "",
        "records": [
            {
                "id": "MR-000001",
                "visitDate": "2026-01-01",
                "diagnosis": "急性肠胃炎",
                "charge": 380.0,
            }
        ],
        "charges": [{"item": "血常规", "category": "检查", "amount": 380.0}],
        "totalCost": 380.0,
        "visitCount": 1,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def ok_payload(
    *,
    items: Optional[List[Dict[str, Any]]] = None,
    total: int = 1,
    page: int = 1,
    page_size: int = 20,
    total_cost: float = 380.0,
) -> Dict[str, Any]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": items if items is not None else [_pet()],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": total_pages,
            "totalCost": total_cost,
        },
        "time": "2026-09-28T00:00:00+08:00",
    }


class MockBackend:
    """A configurable fake of the Go pet hospital REST API."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: Any = None,
        json_text: Optional[str] = None,
        raise_exception: Optional[Exception] = None,
    ) -> None:
        self.requests: List[httpx.Request] = []
        self.status_code = status_code
        self.body = body  # when set, returned as the JSON body
        self.json_text = json_text  # when set, returned as raw text
        self.raise_exception = raise_exception
        self.last_url: Optional[str] = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.last_url = str(request.url)
        if self.raise_exception is not None:
            raise self.raise_exception
        if self.json_text is not None:
            return httpx.Response(self.status_code, text=self.json_text)
        body = self.body if self.body is not None else ok_payload()
        return httpx.Response(self.status_code, json=body)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest_asyncio.fixture
async def mock_backend() -> MockBackend:
    return MockBackend()


@pytest_asyncio.fixture
async def mcp_base_url(mock_backend: MockBackend) -> str:
    """Run the MCP server (stateless Streamable HTTP) against ``mock_backend``.

    The tool's REST client is wired to an ``httpx.MockTransport`` that serves
    ``mock_backend``, so the whole HTTP MCP flow is exercised without any real
    Go service.
    """
    transport_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_backend), timeout=5.0
    )
    injected = RestClient(
        "http://backend.test",
        timeout_seconds=2.0,
        max_retries=0,
        client=transport_client,
    )
    set_rest_client(injected)

    server = create_server(
        Settings(
            pet_hospital_base_url="http://backend.test",
            backend_timeout_seconds=2.0,
            backend_max_retries=0,
        ),
        rest_client=injected,
    )
    port = _free_port()
    config = uvicorn.Config(
        server.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True
        ),
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    runner = uvicorn.Server(config)
    task = asyncio.create_task(runner.serve())
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if runner.started:
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("MCP server did not start")
        yield base
    finally:
        runner.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
        await transport_client.aclose()


def mcp_headers(method: str, name: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "MCP-Protocol-Version": LATEST_MODERN_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


async def mcp_post(
    client: httpx.AsyncClient,
    base_url: str,
    method: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
    id_: int = 1,
) -> httpx.Response:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "method": method}
    request_params: Dict[str, Any] = {"_meta": dict(ENVELOPE_META)}
    if params:
        request_params.update(params)
    body["params"] = request_params
    return await client.post(
        f"{base_url}/mcp",
        headers=mcp_headers(method, name),
        json=body,
    )


async def mcp_post_raw(
    client: httpx.AsyncClient,
    base_url: str,
    method: str,
    body: Dict[str, Any],
    *,
    name: Optional[str] = None,
) -> httpx.Response:
    """POST a request body that may contain ``NaN`` / ``Infinity`` literals.

    ``httpx`` refuses to serialize such values via ``json=``, so the body is
    dumped manually with ``allow_nan=True``.
    """
    raw = json.dumps(body, allow_nan=True)
    return await client.post(
        f"{base_url}/mcp",
        headers=mcp_headers(method, name),
        content=raw,
    )


def parse_jsonrpc(response: httpx.Response) -> Dict[str, Any]:
    return json.loads(response.text)
