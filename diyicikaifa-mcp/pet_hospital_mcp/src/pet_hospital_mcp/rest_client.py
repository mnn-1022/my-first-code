"""Async HTTP client for the Go Pet Hospital REST API.

The Go service is the only business backend and is never modified; this MCP
service reaches it exclusively over HTTP. Every call enforces a timeout and a
bounded number of retries, and every failure is normalized into a
:class:`~pet_hospital_mcp.errors.PetHospitalError` carrying one of the stable
backend error codes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import httpx

from .errors import (
    BACKEND_API_ERROR,
    BACKEND_INVALID_RESPONSE,
    BACKEND_TIMEOUT,
    BACKEND_UNAVAILABLE,
    INTERNAL_ERROR,
    PetHospitalError,
)

API_PATH_PETS = "/api/v1/pets"


class RestClient:
    """Thin, stateless wrapper around ``httpx`` for the Go REST API.

    ``client`` may be injected in tests (e.g. an ``httpx.AsyncClient`` built on
    ``httpx.MockTransport``) so tests never touch a real Go service.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self._injected_client = client

    def _new_client(self) -> httpx.AsyncClient:
        if self._injected_client is not None:
            return self._injected_client
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    async def list_pets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call ``GET /api/v1/pets`` and return the parsed ``data`` object.

        Args:
            params: Query parameters already validated by the tool layer.

        Returns:
            The ``data`` mapping from the Go response envelope.

        Raises:
            PetHospitalError: normalized backend failure.
        """
        url = f"{self.base_url}{API_PATH_PETS}"
        client = self._new_client()
        try:
            response = await self._get_with_retries(client, url, params)
            return self._parse_success_envelope(response)
        except PetHospitalError:
            raise
        except Exception as exc:  # unexpected crash in the call path
            raise PetHospitalError(
                INTERNAL_ERROR,
                "Unexpected error while calling the pet hospital backend",
                {"kind": type(exc).__name__},
            ) from exc
        finally:
            # Only close clients we created ourselves; injected clients are owned
            # by the caller (tests reuse them across calls).
            if self._injected_client is None:
                await client.aclose()

    async def _get_with_retries(
        self, client: httpx.AsyncClient, url: str, params: Dict[str, Any]
    ) -> httpx.Response:
        attempts = 0
        while True:
            attempts += 1
            try:
                return await client.get(url, params=params)
            except httpx.TimeoutException as exc:
                if attempts <= self.max_retries:
                    await asyncio.sleep(0.2 * attempts)
                    continue
                raise PetHospitalError(
                    BACKEND_TIMEOUT,
                    "The pet hospital backend did not respond in time",
                    {"attempts": attempts},
                ) from exc
            except httpx.HTTPError as exc:
                # Connection refused / reset / DNS failure etc.
                if attempts <= self.max_retries:
                    await asyncio.sleep(0.2 * attempts)
                    continue
                raise PetHospitalError(
                    BACKEND_UNAVAILABLE,
                    "The pet hospital backend is unavailable",
                    {"attempts": attempts, "kind": type(exc).__name__},
                ) from exc

    def _parse_success_envelope(self, response: httpx.Response) -> Dict[str, Any]:
        if response.status_code >= 400:
            raise PetHospitalError(
                BACKEND_API_ERROR,
                f"The pet hospital backend returned HTTP {response.status_code}",
                {"status_code": response.status_code},
            )
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise PetHospitalError(
                BACKEND_INVALID_RESPONSE,
                "The pet hospital backend returned an invalid JSON body",
            ) from exc

        if not isinstance(body, dict) or body.get("code") != 200 or "data" not in body:
            raise PetHospitalError(
                BACKEND_INVALID_RESPONSE,
                "The pet hospital backend response envelope is malformed",
            )
        data = body["data"]
        if not isinstance(data, dict):
            raise PetHospitalError(
                BACKEND_INVALID_RESPONSE,
                "The pet hospital backend response is missing its data payload",
            )
        return data
