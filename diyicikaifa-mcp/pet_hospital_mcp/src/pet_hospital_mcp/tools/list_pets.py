"""The ``list_pets`` MCP tool.

Maps the MCP tool to the Go REST API ``GET /api/v1/pets``. All input is
validated by a strict Pydantic model (unknown fields, ``NaN`` / ``Infinity``,
wrong types, enum membership, range constraints and the ``min <= max`` rule),
all backend calls go through :class:`~pet_hospital_mcp.rest_client.RestClient`,
and every result is rendered as a :class:`mcp_types.CallToolResult` whose
``isError`` flag and text content follow the unified error contract.

Adding tools in later phases means adding a sibling module here and reusing the
shared REST client, logging and error helpers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Literal, Optional

from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..errors import (
    BACKEND_INVALID_RESPONSE,
    INTERNAL_ERROR,
    PetHospitalError,
    validation_error,
)
from ..logging_config import get_logger
from ..rest_client import RestClient

# ---------------------------------------------------------------------------
# Real allowed values, sourced from the Go backend ``/api/v1/meta``.
# ---------------------------------------------------------------------------
Species = Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"]
Status = Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
SortBy = Literal[
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
]
Order = Literal["asc", "desc"]

TOOL_NAME = "list_pets"


class ListPetsInput(BaseModel):
    """Strict input model for ``list_pets``.

    Rejects unknown fields, ``NaN`` / ``Infinity``, type-incorrect values,
    invalid enum members and out-of-range numbers; enforces ``min <= max``.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    q: Optional[str] = None
    name: Optional[str] = None
    ownerName: Optional[str] = None
    ownerPhone: Optional[str] = None
    species: Optional[Species] = None
    doctor: Optional[str] = None
    disease: Optional[str] = None
    status: Optional[Status] = None
    min: Optional[float] = Field(default=None, ge=0)
    max: Optional[float] = Field(default=None, ge=0)
    sortBy: Optional[SortBy] = None
    order: Optional[Order] = None
    page: Optional[int] = Field(default=None, ge=1)
    pageSize: Optional[int] = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not be greater than max")
        return self


class PetItem(BaseModel):
    """A single pet archive as returned by the Go API.

    ``records`` / ``charges`` may be ``null`` or an array on the wire; both are
    accepted. Unknown per-item fields are tolerated so the adapter is robust to
    additive backend changes.
    """

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    ageMonths: Optional[int] = None
    color: Optional[str] = None
    chipNo: Optional[str] = None
    ownerName: Optional[str] = None
    ownerPhone: Optional[str] = None
    ownerAddr: Optional[str] = None
    doctor: Optional[str] = None
    disease: Optional[str] = None
    status: Optional[str] = None
    allergy: Optional[str] = None
    note: Optional[str] = None
    records: Optional[List[Any]] = None
    charges: Optional[List[Any]] = None
    totalCost: Optional[float] = None
    visitCount: Optional[int] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class ListPetsSuccess(BaseModel):
    """The successful tool result, matching the Go ``data`` payload."""

    items: List[PetItem]
    total: int
    page: int
    pageSize: int
    totalPages: int
    totalCost: float


# ---------------------------------------------------------------------------
# REST client wiring (single instance configured at startup / in tests).
# ---------------------------------------------------------------------------
_rest_client: Optional[RestClient] = None


def set_rest_client(client: RestClient) -> None:
    global _rest_client
    _rest_client = client


def _client() -> RestClient:
    if _rest_client is None:
        raise PetHospitalError(INTERNAL_ERROR, "REST client is not configured")
    return _rest_client


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _error_result(err: PetHospitalError) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(err.to_dict(), ensure_ascii=False))],
        is_error=True,
    )


def _success_result(success: ListPetsSuccess) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=success.model_dump_json(by_alias=True))],
        is_error=False,
    )


def _validation_result(exc: ValidationError, supplied: Dict[str, Any]) -> CallToolResult:
    unknown = sorted(set(supplied) - set(ListPetsInput.model_fields))
    fields = []
    messages = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "input"
        fields.append(loc)
        messages.append(f"invalid value for '{loc}': {error.get('msg', 'invalid')}")
    err = validation_error(
        "; ".join(messages) or "invalid tool input",
        {"fields": fields, "unknown": unknown},
    )
    return _error_result(err)


# ---------------------------------------------------------------------------
# Server middleware: reject unknown / invalid tool arguments with a clean,
# unified error before the SDK ever strips or re-renders them.
# ---------------------------------------------------------------------------


async def validate_tool_call_arguments(ctx: Any, call_next: Any) -> Any:
    """Context middleware for ``tools/call``.

    Validates the raw client-supplied arguments against ``ListPetsInput`` and
    short-circuits with an ``isError=true`` ``CallToolResult`` on any failure.
    This is what makes "reject unknown fields" observable over HTTP, because the
    SDK's auto-generated argument model would otherwise silently drop extras.
    """
    if ctx.method != "tools/call":
        return await call_next(ctx)
    params = ctx.params if ctx.params else {}
    if params.get("name") != TOOL_NAME:
        return await call_next(ctx)
    arguments = params.get("arguments") or {}
    try:
        ListPetsInput(**arguments)
    except ValidationError as exc:
        return _validation_result(exc, dict(arguments))
    return await call_next(ctx)


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

TOOL_DESCRIPTION = (
    "List pet archives from the Pet Hospital, mirroring GET /api/v1/pets. "
    "Supports full-text search (q), filtering by name / ownerName / ownerPhone / "
    "species / doctor / disease / status and total-cost range (min, max), sorting "
    "(sortBy, order) and pagination (page, pageSize). Returns the data payload "
    "with items, total, page, pageSize, totalPages and totalCost. "
    "Use it to search and browse the hospital's pet register. "
    "species must be one of 犬/猫/兔/鸟/仓鼠/爬宠/其他; status one of "
    "待就诊/就诊中/住院中/已康复/慢性病随访; sortBy one of the allowed fields; "
    "order asc or desc; page >= 1; 1 <= pageSize <= 500; min and max are "
    "non-negative and min <= max."
)


async def list_pets(
    q: Optional[str] = None,
    name: Optional[str] = None,
    ownerName: Optional[str] = None,
    ownerPhone: Optional[str] = None,
    species: Optional[Species] = None,
    doctor: Optional[str] = None,
    disease: Optional[str] = None,
    status: Optional[Status] = None,
    min: Optional[float] = None,
    max: Optional[float] = None,
    sortBy: Optional[SortBy] = None,
    order: Optional[Order] = None,
    page: Optional[int] = None,
    pageSize: Optional[int] = None,
) -> CallToolResult:
    """Expose ``GET /api/v1/pets`` as an MCP tool.

    Args:
        q: Full-text search across fields.
        name: Exact pet name filter.
        ownerName: Owner name filter.
        ownerPhone: Owner phone filter.
        species: Species filter (see allowed values).
        doctor: Attending doctor filter.
        disease: Diagnosis / main condition filter.
        status: Visit status filter (see allowed values).
        min: Minimum total cost (non-negative).
        max: Maximum total cost (non-negative, >= min).
        sortBy: Sort field (one of the allowed fields).
        order: ``asc`` or ``desc``.
        page: Page number, >= 1.
        pageSize: Page size, 1..500.

    Returns:
        A ``CallToolResult``: on success its text content is the ``data`` payload
        (items/total/page/pageSize/totalPages/totalCost); on failure it is the
        unified error document and ``isError`` is ``True``.
    """
    logger: logging.Logger = get_logger("pet_hospital_mcp.tools.list_pets")
    start_ns = time.perf_counter_ns()
    supplied = {
        k: v
        for k, v in {
            "q": q,
            "name": name,
            "ownerName": ownerName,
            "ownerPhone": ownerPhone,
            "species": species,
            "doctor": doctor,
            "disease": disease,
            "status": status,
            "min": min,
            "max": max,
            "sortBy": sortBy,
            "order": order,
            "page": page,
            "pageSize": pageSize,
        }.items()
        if v is not None
    }

    try:
        validated = ListPetsInput(**supplied)
    except ValidationError as exc:
        result = _validation_result(exc, supplied)
        _log_call(logger, "validation_error", supplied, start_ns)
        return result

    query = validated.model_dump(exclude_none=True, by_alias=True)
    try:
        data = await _client().list_pets(query)
    except PetHospitalError as exc:
        result = _error_result(exc)
        _log_call(logger, exc.code, supplied, start_ns)
        return result

    try:
        success = ListPetsSuccess.model_validate(data)
    except ValidationError:
        result = _error_result(
            PetHospitalError(
                BACKEND_INVALID_RESPONSE,
                "The pet hospital backend returned data that does not match the expected model",
            )
        )
        _log_call(logger, BACKEND_INVALID_RESPONSE, supplied, start_ns)
        return result

    result = _success_result(success)
    _log_call(logger, "ok", supplied, start_ns)
    return result


def _log_call(logger: logging.Logger, status: str, params: Dict[str, Any], start_ns: int) -> None:
    duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
    logger.info(
        "tool call",
        extra={
            "tool_name": TOOL_NAME,
            "params": params,
            "status": status,
            "duration_ms": round(duration_ms, 3),
        },
    )
