"""MCP tool modules.

Each tool lives in its own module and exposes a callable plus its input /
success / error models. Future phases add new modules here and reuse the shared
REST client, logging and error helpers.
"""

from .list_pets import (
    ListPetsInput,
    ListPetsSuccess,
    PetItem,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    list_pets,
    set_rest_client,
    validate_tool_call_arguments,
)

__all__ = [
    "ListPetsInput",
    "ListPetsSuccess",
    "PetItem",
    "TOOL_DESCRIPTION",
    "TOOL_NAME",
    "list_pets",
    "set_rest_client",
    "validate_tool_call_arguments",
]
