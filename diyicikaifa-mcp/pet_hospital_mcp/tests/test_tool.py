"""End-to-end tool behaviour over HTTP, including backend error mapping and
tool registration / schema checks.
"""

from __future__ import annotations

import json

import httpx
import pytest

from pet_hospital_mcp.server import create_server
from pet_hospital_mcp.config import Settings
from tests.conftest import (
    mcp_headers,
    mcp_post,
    ok_payload,
    parse_jsonrpc,
)


async def _call(mcp_base_url, arguments, id_=1):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(
            client,
            mcp_base_url,
            "tools/call",
            params={"name": "list_pets", "arguments": arguments},
            name="list_pets",
            id_=id_,
        )
    assert response.status_code == 200, response.text
    return parse_jsonrpc(response)


async def _discover_tools(mcp_base_url):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(client, mcp_base_url, "tools/list", id_=1)
    assert response.status_code == 200
    return parse_jsonrpc(response)["result"]["tools"]


# ---------------------------------------------------------------------------
# Normal call: params forwarded to the backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normal_call_forwards_filters_sort_and_pagination(mcp_base_url, mock_backend):
    envelope = await _call(
        mcp_base_url,
        {
            "q": "肠胃",
            "name": "旺财",
            "ownerName": "张三",
            "ownerPhone": "13800001111",
            "species": "犬",
            "doctor": "李医生",
            "disease": "肠胃炎",
            "status": "待就诊",
            "min": 100,
            "max": 5000,
            "sortBy": "totalCost",
            "order": "desc",
            "page": 2,
            "pageSize": 50,
        },
    )
    assert envelope["result"]["isError"] is False
    url = mock_backend.last_url
    assert url.startswith("http://backend.test/api/v1/pets")
    assert "q=%E8%82%A0%E8%83%83" in url
    assert "species=%E7%8A%AC" in url
    assert "sortBy=totalCost" in url
    assert "order=desc" in url
    assert "page=2" in url
    assert "pageSize=50" in url
    assert "min=100" in url and "max=5000" in url


@pytest.mark.asyncio
async def test_success_payload_matches_go_data(mcp_base_url):
    envelope = await _call(mcp_base_url, {"pageSize": 20})
    assert envelope["result"]["isError"] is False
    data = json.loads(envelope["result"]["content"][0]["text"])
    for key in ("items", "total", "page", "pageSize", "totalPages", "totalCost"):
        assert key in data


@pytest.mark.asyncio
async def test_records_charges_may_be_null(mcp_base_url, mock_backend):
    item = {
        "id": "PET-000002",
        "name": "球球",
        "species": "猫",
        "records": None,
        "charges": None,
        "totalCost": 0.0,
        "visitCount": 0,
    }
    mock_backend.body = ok_payload(items=[item], total=1)
    envelope = await _call(mcp_base_url, {})
    assert envelope["result"]["isError"] is False
    data = json.loads(envelope["result"]["content"][0]["text"])
    assert data["items"][0]["records"] is None
    assert data["items"][0]["charges"] is None


# ---------------------------------------------------------------------------
# Backend error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backend_4xx_maps_to_api_error(mcp_base_url, mock_backend):
    mock_backend.status_code = 404
    mock_backend.body = {"error": "not found"}
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert envelope["result"]["isError"] is True
    assert error["code"] == "BACKEND_API_ERROR"


@pytest.mark.asyncio
async def test_backend_5xx_maps_to_api_error(mcp_base_url, mock_backend):
    mock_backend.status_code = 500
    mock_backend.body = {"error": "boom"}
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert error["code"] == "BACKEND_API_ERROR"


@pytest.mark.asyncio
async def test_backend_timeout_maps_to_backend_timeout(mcp_base_url, mock_backend):
    import httpx as _httpx

    mock_backend.raise_exception = _httpx.ReadTimeout("timeout")
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert error["code"] == "BACKEND_TIMEOUT"


@pytest.mark.asyncio
async def test_backend_connection_error_maps_to_unavailable(mcp_base_url, mock_backend):
    import httpx as _httpx

    mock_backend.raise_exception = _httpx.ConnectError("refused")
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert error["code"] == "BACKEND_UNAVAILABLE"


@pytest.mark.asyncio
async def test_backend_invalid_json_maps_to_invalid_response(mcp_base_url, mock_backend):
    mock_backend.json_text = "<html>oops</html>"
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert error["code"] == "BACKEND_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_backend_malformed_model_maps_to_invalid_response(mcp_base_url, mock_backend):
    # Missing required fields -> fails ListPetsSuccess validation
    mock_backend.body = {"code": 200, "message": "ok", "data": {"items": [], "total": 0}}
    envelope = await _call(mcp_base_url, {})
    error = json.loads(envelope["result"]["content"][0]["text"])["error"]
    assert error["code"] == "BACKEND_INVALID_RESPONSE"


# ---------------------------------------------------------------------------
# Registration / schema
# ---------------------------------------------------------------------------


def test_tool_registration_name_and_schema():
    server = create_server(Settings())
    import asyncio

    tools = asyncio.run(server.list_tools())
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "list_pets"
    assert tool.description and len(tool.description) > 100
    schema = tool.input_schema
    props = schema["properties"]
    expected = {
        "q",
        "name",
        "ownerName",
        "ownerPhone",
        "species",
        "doctor",
        "disease",
        "status",
        "min",
        "max",
        "sortBy",
        "order",
        "page",
        "pageSize",
    }
    assert expected == set(props)
    assert props["species"]["anyOf"][0]["enum"] == ["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"]
    assert props["status"]["anyOf"][0]["enum"] == ["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
    assert "totalCost" in props["sortBy"]["anyOf"][0]["enum"]
