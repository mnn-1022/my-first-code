"""Unit tests for the REST client against a mocked Go backend.

No real Go service is contacted: every request is served by ``httpx.MockTransport``.
"""

from __future__ import annotations

import httpx
import pytest

from pet_hospital_mcp.errors import (
    BACKEND_API_ERROR,
    BACKEND_INVALID_RESPONSE,
    BACKEND_TIMEOUT,
    BACKEND_UNAVAILABLE,
    PetHospitalError,
)
from pet_hospital_mcp.rest_client import RestClient
from tests.conftest import MockBackend, ok_payload


def _client(backend: MockBackend, *, timeout: float = 2.0, retries: int = 1) -> RestClient:
    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(backend), timeout=timeout)
    return RestClient(
        "http://backend.test",
        timeout_seconds=timeout,
        max_retries=retries,
        client=transport_client,
    )


@pytest.mark.asyncio
async def test_normal_call_forwards_path_and_all_params():
    backend = MockBackend()
    client = _client(backend)
    params = {
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
    }
    data = await client.list_pets(params)
    assert data["total"] == 1
    assert backend.last_url == (
        "http://backend.test/api/v1/pets"
        "?q=%E8%82%A0%E8%83%83"
        "&name=%E6%97%BA%E8%B4%A2"
        "&ownerName=%E5%BC%A0%E4%B8%89"
        "&ownerPhone=13800001111"
        "&species=%E7%8A%AC"
        "&doctor=%E6%9D%8E%E5%8C%BB%E7%94%9F"
        "&disease=%E8%82%A0%E8%83%83%E7%82%8E"
        "&status=%E5%BE%85%E5%B0%B1%E8%AF%8A"
        "&min=100"
        "&max=5000"
        "&sortBy=totalCost"
        "&order=desc"
        "&page=2"
        "&pageSize=50"
    )
    assert backend.last_url.startswith("http://backend.test/api/v1/pets")


@pytest.mark.asyncio
async def test_normal_call_parses_data_payload():
    backend = MockBackend(body=ok_payload(total=3, page_size=20))
    client = _client(backend)
    data = await client.list_pets({"page": 1})
    assert data["total"] == 3
    assert data["pageSize"] == 20
    assert data["items"][0]["id"] == "PET-000001"


@pytest.mark.asyncio
async def test_http_4xx_raises_backend_api_error():
    backend = MockBackend(status_code=404, body={"error": "not found"})
    client = _client(backend, retries=0)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_API_ERROR


@pytest.mark.asyncio
async def test_http_5xx_raises_backend_api_error():
    backend = MockBackend(status_code=500, body={"error": "boom"})
    client = _client(backend, retries=0)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_API_ERROR


@pytest.mark.asyncio
async def test_timeout_raises_backend_timeout():
    backend = MockBackend()
    backend.raise_exception = httpx.ReadTimeout("read timeout")
    client = _client(backend, retries=1)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_TIMEOUT


@pytest.mark.asyncio
async def test_connection_error_raises_backend_unavailable():
    backend = MockBackend()
    backend.raise_exception = httpx.ConnectError("connection refused")
    client = _client(backend, retries=1)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_UNAVAILABLE


@pytest.mark.asyncio
async def test_retries_are_bounded():
    backend = MockBackend()
    backend.raise_exception = httpx.ConnectError("down")
    client = _client(backend, retries=2)
    with pytest.raises(PetHospitalError):
        await client.list_pets({})
    # initial attempt + 2 retries = 3 calls, no more
    assert len(backend.requests) == 3


@pytest.mark.asyncio
async def test_retry_recovers_on_second_attempt():
    backend = MockBackend()

    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("first attempt down")
        return httpx.Response(200, json=ok_payload())

    backend.raise_exception = None
    flaky_client = httpx.AsyncClient(transport=httpx.MockTransport(flaky), timeout=2.0)
    client = RestClient(
        "http://backend.test", timeout_seconds=2.0, max_retries=2, client=flaky_client
    )
    data = await client.list_pets({})
    assert data["total"] == 1
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_invalid_json_raises_backend_invalid_response():
    backend = MockBackend(json_text="<html>not json</html>")
    client = _client(backend, retries=0)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_malformed_envelope_raises_backend_invalid_response():
    # 200 with a body that is not the {"code":200,"data":...} envelope
    backend = MockBackend(body={"unexpected": True})
    client = _client(backend, retries=0)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_missing_data_raises_backend_invalid_response():
    backend = MockBackend(body={"code": 200, "message": "ok"})
    client = _client(backend, retries=0)
    with pytest.raises(PetHospitalError) as exc_info:
        await client.list_pets({})
    assert exc_info.value.code == BACKEND_INVALID_RESPONSE
