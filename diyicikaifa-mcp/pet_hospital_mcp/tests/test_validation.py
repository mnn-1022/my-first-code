"""Strict input validation for ``list_pets``, verified over HTTP.

Every invalid input must surface as an ``isError=true`` ``CallToolResult`` whose
text content is the unified error document with ``code == "VALIDATION_ERROR"``.
Unknown fields, ``NaN`` / ``Infinity``, wrong types, invalid enum members and
out-of-range numbers are all rejected.
"""

from __future__ import annotations

import math

import httpx
import pytest
import pytest_asyncio

from tests.conftest import (
    ENVELOPE_META,
    mcp_headers,
    mcp_post,
    mcp_post_raw,
    parse_jsonrpc,
)


@pytest.mark.asyncio
async def _call(mcp_base_url: str, arguments: dict) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post(
            client,
            mcp_base_url,
            "tools/call",
            params={"name": "list_pets", "arguments": arguments},
            name="list_pets",
        )
    assert response.status_code == 200, response.text
    envelope = parse_jsonrpc(response)
    return envelope


def _error_from_call(envelope: dict) -> dict:
    result = envelope["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    return __import__("json").loads(text)


@pytest.mark.asyncio
async def test_page_must_be_ge_1(mcp_base_url):
    envelope = await _call(mcp_base_url, {"page": 0})
    error = _error_from_call(envelope)
    assert error["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_page_size_ge_1(mcp_base_url):
    envelope = await _call(mcp_base_url, {"pageSize": 0})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_page_size_le_500(mcp_base_url):
    envelope = await _call(mcp_base_url, {"pageSize": 501})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_min_non_negative(mcp_base_url):
    envelope = await _call(mcp_base_url, {"min": -1})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_max_non_negative(mcp_base_url):
    envelope = await _call(mcp_base_url, {"max": -5})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_min_not_above_max(mcp_base_url):
    envelope = await _call(mcp_base_url, {"min": 500, "max": 100})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_species(mcp_base_url):
    envelope = await _call(mcp_base_url, {"species": "狗"})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_status(mcp_base_url):
    envelope = await _call(mcp_base_url, {"status": "已出院"})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_sort_by(mcp_base_url):
    envelope = await _call(mcp_base_url, {"sortBy": "fancyField"})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_order(mcp_base_url):
    envelope = await _call(mcp_base_url, {"order": "ascending"})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_wrong_type_rejected(mcp_base_url):
    envelope = await _call(mcp_base_url, {"page": "abc"})
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_unknown_field_rejected(mcp_base_url):
    envelope = await _call(mcp_base_url, {"q": "dog", "bogus": 1})
    error = _error_from_call(envelope)
    assert error["error"]["code"] == "VALIDATION_ERROR"
    assert "bogus" in error["error"]["details"].get("unknown", [])


@pytest.mark.asyncio
async def test_nan_rejected(mcp_base_url):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "_meta": dict(ENVELOPE_META),
            "name": "list_pets",
            "arguments": {"min": math.nan},
        },
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post_raw(
            client, mcp_base_url, "tools/call", body, name="list_pets"
        )
    assert response.status_code == 200, response.text
    envelope = parse_jsonrpc(response)
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_infinity_rejected(mcp_base_url):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "_meta": dict(ENVELOPE_META),
            "name": "list_pets",
            "arguments": {"max": math.inf},
        },
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await mcp_post_raw(
            client, mcp_base_url, "tools/call", body, name="list_pets"
        )
    assert response.status_code == 200, response.text
    envelope = parse_jsonrpc(response)
    assert _error_from_call(envelope)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_all_valid_params_accepted(mcp_base_url):
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
            "min": 0,
            "max": 5000,
            "sortBy": "totalCost",
            "order": "desc",
            "page": 1,
            "pageSize": 20,
        },
    )
    assert envelope["result"]["isError"] is False
