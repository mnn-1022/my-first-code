"""MCP server exposing AnythingLLM's first workspace document list over Streamable HTTP."""

import json
import os

import httpx
from mcp.server.mcpserver import MCPServer

ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://localhost:3001").rstrip("/")
ANYTHINGLLM_API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "")
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "3002"))

server = MCPServer(name="anythingllm", version="0.1.0")


def _get(path: str) -> httpx.Response:
    if not ANYTHINGLLM_API_KEY:
        raise RuntimeError("ANYTHINGLLM_API_KEY is not set")
    with httpx.Client(timeout=30.0) as client:
        return client.get(
            f"{ANYTHINGLLM_URL}{path}",
            headers={"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"},
        )


@server.tool(
    name="list_workspace_documents",
    description="List the documents of the first AnythingLLM workspace, with metadata (title, source, word count, tokens, path).",
)
def list_workspace_documents() -> str:
    workspaces = _get("/api/v1/workspaces").json()["workspaces"]
    if not workspaces:
        return json.dumps({"error": "no workspace found"}, ensure_ascii=False)

    first = workspaces[0]
    detail = _get(f"/api/v1/workspace/{first['slug']}").json()["workspace"][0]
    documents = []
    for doc in detail.get("documents") or []:
        metadata = doc.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                pass
        documents.append(
            {
                "docId": doc.get("docId"),
                "filename": doc.get("filename"),
                "docpath": doc.get("docpath"),
                "pinned": doc.get("pinned"),
                "createdAt": doc.get("createdAt"),
                "lastUpdatedAt": doc.get("lastUpdatedAt"),
                "metadata": metadata,
            }
        )

    return json.dumps(
        {
            "workspace": {"id": first["id"], "name": first["name"], "slug": first["slug"]},
            "documentCount": len(documents),
            "documents": documents,
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    # stateless_http + json_response => serves pre-2026-07-28 clients (initialize
    # handshake, Mcp-Session-Id optional) and 2026-07-28+ clients (single POST, no
    # handshake, no long-lived connection) from the same endpoint.
    server.run(transport="streamable-http", host=HOST, port=PORT, stateless_http=True, json_response=True)
