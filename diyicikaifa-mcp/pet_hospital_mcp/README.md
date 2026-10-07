# 🐾 Pet Hospital MCP Service

一个独立的 **MCP（Model Context Protocol）服务**，把现有 **Go 宠物医院 REST API** 的能力暴露给 AI Agent。

- 语言 / 运行时：**Python 3.11+**
- 官方 Python SDK：**`mcp==2.2.0`**（SDK **2.x**，不是 1.x）
- 使用 **`mcp.server.mcpserver.MCPServer`**（**不使用 / 不导入 `mcp.server.fastmcp.FastMCP`**）
- 协议版本：**`2026-07-28`**（现代无状态 per-request envelope 时代）
- 传输：**无状态（stateless）Streamable HTTP**
- 不实现旧协议：无 `initialize` 握手、无 `Mcp-Session-Id`、无会话存储 / 会话过期、无 `max_sessions`、无有状态 SSE 恢复

> 本服务只做 **HTTP 调用 Go REST API**，**不修改 Go 后端**；教学场景不实现认证 / 权限 / CORS / Origin 校验。

---

## 目录结构

```text
pet_hospital_mcp/
├── pyproject.toml
├── README.md
├── UPGRADE_PROMPT.md
├── conftest.py                 # 让 `pytest -q` 无需安装即可运行
├── src/
│   └── pet_hospital_mcp/
│       ├── __init__.py
│       ├── __main__.py         # 入口：python -m pet_hospital_mcp
│       ├── config.py           # MCP_HOST / MCP_PORT / PET_HOSPITAL_BASE_URL …
│       ├── server.py           # 装配 MCPServer、middleware、/health
│       ├── rest_client.py      # httpx 客户端：超时 + 有限重试 + 结构化错误
│       ├── errors.py           # 统一错误结构（VALIDATION_ERROR 等）
│       ├── logging_config.py   # JSON 日志 + 敏感字段递归脱敏
│       └── tools/
│           ├── __init__.py
│           └── list_pets.py    # 阶段一唯一工具
└── tests/                      # pytest + pytest-asyncio + httpx.MockTransport
```

新增工具：在 `tools/` 下加一个模块，复用 `RestClient`、日志与错误约定即可。

---

## 一、安装与启动

### 0. 前置条件

- **Python 3.11+**
- **先启动 Go 宠物医院服务**（本服务的唯一业务后端）：
  ```bash
  cd pet-hospital-windows-amd64/windows
  pethospital.exe            # 默认监听 http://127.0.0.1:8080
  ```

### 1. 安装依赖

```bash
cd pet_hospital_mcp
pip install -e ".[dev]"      # 或：pip install mcp==2.2.0 httpx pydantic pytest pytest-asyncio
```

### 2. 启动 MCP 服务

```bash
cd pet_hospital_mcp
python -m pet_hospital_mcp          # 或：pet-hospital-mcp
```

启动后默认监听 `http://127.0.0.1:8000`，MCP 端点为 `/mcp`。

### 3. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MCP_HOST` | `127.0.0.1` | MCP 服务监听地址 |
| `MCP_PORT` | `8000` | MCP 服务监听端口 |
| `MCP_PATH` | `/mcp` | MCP Streamable HTTP 端点路径 |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API 上游地址 |
| `PET_HOSPITAL_TIMEOUT_SECONDS` | `5.0` | 后端调用超时（秒） |
| `PET_HOSPITAL_MAX_RETRIES` | `2` | 后端调用有限重试次数 |
| `PET_HOSPITAL_LOG_LEVEL` | `INFO` | 日志级别 |

示例（自定义端口与上游）：

```bash
MCP_PORT=9000 PET_HOSPITAL_BASE_URL=http://127.0.0.1:9090 python -m pet_hospital_mcp
```

---

## 二、MCP 端点

- `POST {MCP_PATH}`（默认 `http://127.0.0.1:8000/mcp`）：无状态 Streamable HTTP 请求入口
- `GET /health`：健康检查

协议版本：`2026-07-28`。每次请求使用 **per-request envelope**：

请求头：
```
MCP-Protocol-Version: 2026-07-28
Mcp-Method: <method>              # server/discover | tools/list | tools/call
Mcp-Name: <tool>                  # 仅 tools/call 需要
Content-Type: application/json
Accept: application/json, text/event-stream
```

请求体（`params._meta` 携带信封字段）：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "server/discover",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

---

## 三、阶段一唯一工具：`list_pets`

严格适配 Go 的 `GET /api/v1/pets`，**支持且仅支持**以下查询参数：

`q` `name` `ownerName` `ownerPhone` `species` `doctor` `disease` `status` `min` `max` `sortBy` `order` `page` `pageSize`

输入校验（严格）：
- `species` 必须是 `犬/猫/兔/鸟/仓鼠/爬宠/其他`
- `status` 必须是 `待就诊/就诊中/住院中/已康复/慢性病随访`
- `sortBy` 必须是 `id/name/ownerName/species/doctor/disease/status/totalCost/visitCount/createdAt/updatedAt`
- `order` 必须是 `asc/desc`
- `page >= 1`；`1 <= pageSize <= 500`
- `min`、`max` 非负，且 `min <= max`
- **拒绝未知字段、NaN、Infinity 和类型不正确的输入**

成功输出对应 Go 响应中的 `data`：
`items`、`total`、`page`、`pageSize`、`totalPages`、`totalCost`。
兼容 `records` / `charges` 为 `null` 或数组的真实 JSON 表现。

### 错误处理（统一结构化）

所有无效输入和上游异常都返回：

```json
{ "error": { "code": "ERROR_CODE", "message": "可读错误信息", "details": {} } }
```

至少区分：`VALIDATION_ERROR`、`BACKEND_TIMEOUT`、`BACKEND_UNAVAILABLE`、`BACKEND_API_ERROR`、`BACKEND_INVALID_RESPONSE`、`INTERNAL_ERROR`。

后端调用具备**超时 + 有限重试**；不向客户端暴露 HTTPX / Pydantic / SDK / Python 堆栈。

---

## 四、验证步骤

### 1. 健康检查

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"pet-hospital-mcp","version":"0.1.0","backend":"http://127.0.0.1:8080"}
```

### 2. 无状态发现（server/discover）

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: server/discover' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```

响应 `result.supportedVersions` 包含 `2026-07-28`，且**不返回 `Mcp-Session-Id`**（无状态）。

### 3. 列出工具

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/list' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```

### 4. 调用 `list_pets`

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/call' -H 'Mcp-Name: list_pets' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}},"name":"list_pets","arguments":{"species":"犬","sortBy":"totalCost","order":"desc","page":1,"pageSize":2}}}'
```

成功响应（`isError: false`）的文本内容即 Go `data`：
`items / total / page / pageSize / totalPages / totalCost`。

### 5. 使用 MCP Inspector 或 SDK 2.x 客户端

- **MCP Inspector**：`npx @modelcontextprotocol/inspector` 后连接 `http://127.0.0.1:8000/mcp`（Streamable HTTP）。
- **SDK 2.x 客户端**：使用 `mcp` 2.x 客户端对 `http://127.0.0.1:8000/mcp` 发起 `server/discover` → `tools/list` → `tools/call`。整个流程**不需要旧版 `initialize`**，也**不要求 `Mcp-Session-Id`**。

---

## 五、单元测试

```bash
cd pet_hospital_mcp
pytest -q
```

预期结果：**全部通过**（示例：`43 passed`）。

测试说明：
- 使用 `pytest`、`pytest-asyncio`、`httpx.MockTransport`；
- **测试绝不访问真实 Go 服务**（后端由进程内 MockTransport 模拟）；
- 覆盖：参数正确转发、输入校验失败、4xx/5xx、超时与连接异常、非法 JSON / 不符合模型、工具注册 / 名称 / JSON Schema、无状态 HTTP 流程（discover / tools/list / tools/call / /health、无 `initialize`、无 `Mcp-Session-Id`）。

---

## 六、日志

JSON 结构化日志（stderr），每条工具调用至少包含：

```json
{"timestamp": "...", "level": "INFO", "logger": "...", "message": "tool call",
 "tool_name": "list_pets", "params": {...}, "status": "ok", "duration_ms": 1.234}
```

`ownerPhone`、`ownerAddr`、`chipNo` 及其 snake_case 写法在 `params` 中**递归脱敏**为 `***`，完整敏感值不会写入日志。

---

## 七、阶段说明

本次只实现阶段一唯一工具 **`list_pets`**；阶段二工具**未实现**。

---

## 八、技术要点速览

| 项 | 取值 |
| --- | --- |
| 语言 / 运行时 | Python 3.11+ |
| 官方 SDK | `mcp==2.2.0`（SDK 2.x） |
| 服务器类 | `mcp.server.mcpserver.MCPServer` |
| 禁用 | `mcp.server.fastmcp.FastMCP` |
| 协议版本 | `2026-07-28`（MODERN） |
| 传输 | 无状态 Streamable HTTP（`stateless_http=True`） |
| 会话 | 无（无 `initialize` / `Mcp-Session-Id` / 会话存储 / 过期 / `max_sessions` / 有状态 SSE 恢复） |
| MCP 端点 | `POST /mcp` |
| 健康检查 | `GET /health` |
