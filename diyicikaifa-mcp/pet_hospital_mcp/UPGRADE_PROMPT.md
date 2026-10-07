# UPGRADE PROMPT —— 从 MCP SDK 1.x（FastMCP）升级到 SDK 2.x（MCPServer，2026-07-28）

本文档说明本仓库从 SDK 1.x / 旧协议升级到 **SDK 2.x + 协议 `2026-07-28`（无状态 Streamable HTTP）** 的约束与要点。它既是升级的「提示词」，也是实现本仓库所依据的硬性边界。

> 本仓库**不实现、不兼容、不迁移**任何 SDK 1.x 的 FastMCP 服务；只实现 SDK 2.x + `2026-07-28` 现代无状态模型。

---

## 1. 为什么不能用 FastMCP

- SDK 1.x 的 `mcp.server.fastmcp.FastMCP` 属于旧握手时代（`initialize` 会话 + 有状态连接）。
- 本项目明确要求 **`mcp.server.mcpserver.MCPServer`**，且**不得使用或导入** `mcp.server.fastmcp.FastMCP`。
- 升级时若遇到旧代码里的 `from mcp.server.fastmcp import FastMCP`，应改为使用 `MCPServer` 的 API（`add_tool` / `@server.tool()` / `custom_route`）。

## 2. 版本与协议

- 官方 Python SDK 2.x：**`mcp==2.2.0`**。
- 协议版本：**`2026-07-28`**，属于 `MODERN_PROTOCOL_VERSIONS`（现代 per-request envelope 时代）。
- 现代时代**不用 `initialize` 握手**，改用 **`server/discover`** 探针；能力与工具通过 `server/discover` / `tools/list` 发现。

## 3. 无状态 Streamable HTTP

- 以 `stateless_http=True` 运行 Streamable HTTP：**每个请求新建传输**，不建会话。
- **不实现 / 不使用**：
  - 旧 `initialize`
  - `Mcp-Session-Id`（不要求、不返回）
  - 会话存储 / 会话过期
  - `max_sessions`
  - 有状态 SSE 恢复
- 客户端每次请求携带 `MCP-Protocol-Version: 2026-07-28`、`Mcp-Method`（tools/call 还需 `Mcp-Name`），并在 `params._meta` 携带
  `io.modelcontextprotocol/protocolVersion` 与 `io.modelcontextprotocol/clientCapabilities`。

## 4. 工具注册与参数

- 用 `MCPServer.add_tool(fn, description=...)` 或 `@server.tool()` 注册；工具名使用 snake_case。
- 工具输入 JSON Schema 由函数签名（Pydantic）自动生成。
- **未知字段 / NaN / Infinity 的拒绝**：SDK 自动生成的参数模型默认会静默丢弃未知字段，因此通过一个 `ServerMiddleware` 在 `tools/call` 用严格的 Pydantic 输入模型先行校验，任何失败都以 `isError=true` 的统一错误结构返回。
- 用 Pydantic 定义输入、成功输出、错误输出三类模型。

## 5. 错误标记（2.x 实际规定）

- SDK 2.x 的工具失败状态仍通过 `CallToolResult(isError=...)` 标记（`is_error` 字段）。
- 工具函数返回 `CallToolResult`：成功 `is_error=False`，失败 `is_error=True` 且文本内容为统一错误 JSON。
- 统一结构：
  ```json
  { "error": { "code": "ERROR_CODE", "message": "可读错误信息", "details": {} } }
  ```
  至少区分 `VALIDATION_ERROR / BACKEND_TIMEOUT / BACKEND_UNAVAILABLE / BACKEND_API_ERROR / BACKEND_INVALID_RESPONSE / INTERNAL_ERROR`。
- 不向客户端暴露 HTTPX / Pydantic / SDK / Python 堆栈。

## 6. 后端边界

- Go 宠物医院是唯一业务后端，**不得修改**；MCP 服务只能通过 HTTP 调用。
- `PET_HOSPITAL_BASE_URL` 默认 `http://127.0.0.1:8080`。
- 后端调用必须**超时 + 有限重试**。

## 7. 验证清单（升级通过的标准）

- [ ] 不导入 `FastMCP`；使用 `MCPServer`
- [ ] 协议为 `2026-07-28`
- [ ] 无状态：请求不发送旧 `initialize`；响应不要求 / 不返回 `Mcp-Session-Id`
- [ ] 通过 `server/discover` 发现
- [ ] `/health` 可用
- [ ] `list_pets` 可通过 HTTP MCP 端点发现与调用
- [ ] `cd pet_hospital_mcp && pytest -q` 全部通过
