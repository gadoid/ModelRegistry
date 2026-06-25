# `gimbal prism` — Web 配置器 (UI 模式)

> **目的**：通过浏览器 4-Tab UI，把 capture 抓到的 NDJSON 编辑成可运行的
> GIMBAL Scenario YAML，落到 `$GIMBAL_HOME/scenarios/{sid}.yaml`。
>
> **设计理念**：FastAPI `lifespan` + `app.state` 集中管理状态，无模块级单例。
> schema 是单一事实源 (SSOT)，前端表单从 `/api/schema/ui-spec` 反射生成。

---

## 目录

1. [快速开始](#1-快速开始)
2. [工作流](#2-工作流)
3. [UI 4-Tab 结构](#3-ui-4-tab-结构)
4. [HTTP API 参考](#4-http-api-参考)
5. [WebSocket / SSE 实时事件流](#5-websocket--sse-实时事件流)
6. [Scenario YAML 完整格式](#6-scenario-yaml-完整格式)
7. [退出码与日志](#7-退出码与日志)
8. [常见问题](#8-常见问题)

---

## 1. 快速开始

### 1.1 启动

```bash
# 默认 127.0.0.1:8765
gimbal prism start

# 指定 host/port/home
gimbal prism start --host 0.0.0.0 --port 9000 --home /var/lib/gimbal

# 开发模式 (热重载)
gimbal prism start --reload
```

**启动输出**：

```
[prism] GIMBAL_HOME=/home/user/.gimbal
[prism] starting on http://127.0.0.1:8765
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

### 1.2 配合 capture

```bash
# A 终端
gimbal capture start -s e2e-checkout

# B 终端
gimbal prism start

# 浏览器打开 http://127.0.0.1:8765
# 配置浏览器代理到 127.0.0.1:8080
# 业务操作 (登录, 加购, 提交订单)
# 在 prism UI 中实时看到事件流入
```

### 1.3 直接打开已抓包的 session

```bash
# 启动 prism
gimbal prism start

# 浏览器访问
http://127.0.0.1:8765/configure?session=e2e-checkout
```

`session` query 参数会注入到 HTML 的 `<meta name="gimbal-session">`，前端自动加载该 session 的事件。

---

## 2. 工作流

```
┌─────────────┐    mitmproxy     ┌────────────────────┐
│  浏览器/客户端 │ ───────────────▶ │  $GIMBAL_HOME/      │
│  (代理:8080)  │                 │  captures/active/  │
└─────────────┘                 │  e2e.ndjson        │
                                  └────────┬───────────┘
                                           │ (SSE / WS / 轮询)
                                           ▼
                                  ┌────────────────────┐
                                  │  prism FastAPI     │
                                  │  (port 8765)       │
                                  └────────┬───────────┘
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │  4-Tab UI (浏览器)        │
                              │  1. Captures            │
                              │  2. Steps               │
                              │  3. Config (auth/...)  │
                              │  4. Resources          │
                              └────────┬────────────────┘
                                       │ PUT /api/draft/{sid}
                                       ▼
                              ┌─────────────────────────┐
                              │  app.state.sessions[...].draft │
                              └────────┬────────────────┘
                                       │ POST /api/draft/{sid}/export
                                       ▼
                              $GIMBAL_HOME/scenarios/{sid}.yaml
```

---

## 3. UI 4-Tab 结构

### Tab 1: **Captures** (捕获事件列表)

- 显示 `active/{sid}.ndjson` 所有事件
- 实时通过 SSE 流接收新事件
- 每条事件显示：方法、host/path、状态码、耗时
- 可勾选/取消要进入 scenario 的事件
- 可点 "Clear" 清空文件

### Tab 2: **Steps** (步骤编辑)

- 每个 step 一张卡片
- 可编辑字段：
  - `key` (步骤名，如 `1-login`, `2-submit_order`)
  - `method` / `path` (覆盖 capture 抓到的)
  - `service` (从 capture 的 host 推断，可改)
  - `params` (query 参数)
  - `body` (请求体，JSON 编辑)
  - `assertions` (断言，如 `status == 200`, `body.code == 0`)
  - `extracts` (提取变量，如 `body.data.token → var.token`)
  - `assigns` (赋值，如 `var.user_id ← $response.body.user.id`)
  - `note` (备注)
- 可拖拽排序
- 可启用/禁用 (`enabled` 字段)

### Tab 3: **Config** (场景配置)

- **Meta**:
  - `scenario_id`, `name`, `description`
  - `module`, `priority`, `author`, `owner`
  - `tags` (数组), `version`, `expire`
  - `requirement_ref` (数组)
- **Services**: `host → service_name` 映射
- **Users**: 多个认证用户 (key/url/username/password/expires_in/token_type/token)
- **Time Policy**:
  - `kind`: `record` (录制) / `timeout` (超时)
  - `seconds`: 超时秒数
- **Retry**:
  - `enabled`: bool
  - `max_attempts`: int
  - `backoff_seconds`: float
  - `retry_on`: 状态码列表
- **Setup/Teardown Refs**: 引用其他 scenario

### Tab 4: **Resources** (依赖资源)

- 4 种 kind：
  - `mock`: 内嵌 mock 服务 (`image`, `config`, `portMapping`)
  - `mock_ref`: 引用已注册的 mock (`ref`)
  - `file`: 内嵌文件 (`path`)
  - `file_ref`: 引用已注册的文件 (`ref`)

### 顶部操作栏

- **Export** → 调用 `POST /api/draft/{sid}/export`，把 draft 渲染成 Scenario YAML 落地
- **Preview YAML** → 调用 `POST /api/draft/{sid}/yaml`，不写盘仅预览
- **Undo / Redo** → draft 历史栈

---

## 4. HTTP API 参考

### 4.1 通用

#### `GET /api/health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "sessions": 3,
  "captures_active": 2
}
```

#### `GET /api/schema/ui-spec`

返回 schema → 前端可消费 JSON。前端用这个**反射生成表单**。

```json
{
  "name": "Scenario",
  "fields": [
    {
      "name": "scenarioId",
      "type": "str",
      "ui": {"widget": "input", "required": true}
    },
    {
      "name": "meta",
      "type": "Meta",
      "ui": {"widget": "object"}
    },
    ...
  ]
}
```

#### `GET /api/schema/dot-paths`

```json
{
  "paths": [
    "scenarioId",
    "meta.name",
    "meta.tags",
    "config.users.*.url",
    "config.timePolicy.kind",
    "steps.*.api.method",
    "steps.*.api.path",
    "resource.*.kind",
    ...
  ],
  "count": 87
}
```

#### `GET /api/registry/ui-spec`

返回 ModelRegistry 反射出的 UI spec（Phase 3 引入，给字段提供"选择已有 service"下拉）。

### 4.2 Captures (文件视角)

#### `GET /api/captures?sid=<SID>&limit=500`

读历史事件（默认最多 500 条）。

```json
{
  "count": 12,
  "sid": "e2e-checkout",
  "events": [
    {
      "ts": 1719283721.234,
      "method": "POST",
      "host": "api.example.com",
      "path": "/api/order/submit",
      "headers": {...},
      "body": "...",
      "response": {"status": 201, "headers": {...}, "body": "..."}
    },
    ...
  ]
}
```

#### `DELETE /api/captures?sid=<SID>`

截断 NDJSON 文件（清空事件）。

```json
{"status": "cleared", "sid": "e2e-checkout"}
```

#### `POST /api/captures/inject?sid=<SID>`

单条事件追加（给测试/replay 工具用）。

```bash
curl -X POST 'http://127.0.0.1:8765/api/captures/inject?sid=test' \
     -H "Content-Type: application/json" \
     -d '{"method":"GET","host":"x.com","path":"/y","response":{"status":200}}'
```

#### `POST /api/captures/import-from-path?sid=<SID>`

从本地 NDJSON 路径批量追加到 `active/{sid}.ndjson`。
**安全约束**：path 必须在 CWD 之内（防任意文件读）。

```json
// Request
{"path": "./captures/old.ndjson"}

// Response
{"status": "ok", "imported": 42, "path": "/abs/path/captures/old.ndjson", "sid": "test"}
```

### 4.3 Session / Draft

#### `GET /api/draft/{session_id}`

读当前 draft + 历史栈长度。

```json
{
  "draft": {
    "scenarioId": "sc_e2e_checkout",
    "name": "template",
    "steps": [...],
    ...
  },
  "history_len": 5,
  "redo_len": 0
}
```

#### `PUT /api/draft/{session_id}`

把整个 draft 覆盖（前端每次编辑后调用，自动入历史栈）。

```bash
curl -X PUT 'http://127.0.0.1:8765/api/draft/e2e' \
     -H "Content-Type: application/json" \
     -d @draft.json
```

#### `POST /api/draft/{session_id}/export`

把 draft 渲染成 Scenario YAML 并落地。

```json
// Request
{
  "fmt": "yaml",              // or "json"
  "output_path": "/custom/path/scenario.yaml",  // 可选, 缺省 $GIMBAL_HOME/scenarios/{sid}.yaml
  ...所有 DraftIn 字段...
}

// Response
{
  "status": "ok",
  "path": "/home/user/.gimbal/scenarios/e2e.yaml",
  "fmt": "yaml",
  "scenario_id": "e2e"
}
```

**校验失败** → `422`：

```json
{
  "detail": {
    "schema_errors": [
      {"loc": ["config", "users", "admin", "url"], "msg": "field required", "type": "value_error.missing"}
    ]
  }
}
```

#### `POST /api/draft/{session_id}/yaml`

只读 YAML 预览，不写盘。校验失败时返回 422 + 字段级错误信息（方便前端高亮）。

```json
// Response 200
{"yaml": "scenarioId: sc_e2e\nmeta:\n  name: ...\n..."}

// Response 422
{
  "errors": [
    {"field": "config.users.admin.url", "msg": "field required"},
    {"field": "steps.2.api.path", "msg": "string does not match regex"}
  ]
}
```

---

## 5. WebSocket / SSE 实时事件流

两种方式都能用，前端默认用 SSE（更简单）。

### 5.1 SSE: `GET /api/captures/stream?sid=<SID>`

```bash
curl -N 'http://127.0.0.1:8765/api/captures/stream?sid=e2e'
# event: capture
# id: 1719283721.234
# data: {"ts":1719283721.234,"method":"POST",...}
#
# event: capture
# id: 1719283722.456
# data: {...}
```

**特点**：
- 连接时先发一帧历史所有事件（前端可补齐）
- 之后每条新事件发一帧
- 浏览器原生 `EventSource` 即可

### 5.2 WebSocket: `ws://.../ws/captures?sid=<SID>`

**协议**：

```jsonc
// 1. 客户端连接
ws://127.0.0.1:8765/ws/captures?sid=e2e

// 2. 服务端 hello 帧 (历史补齐)
{"type": "hello", "count": 12, "events": [...]}

// 3. 服务端每条新事件
{"type": "capture", "data": {"ts": ..., "method": ..., ...}}
```

**特点**：
- 双向（理论上可扩展，v0 服务端只推不收）
- 适合需要在同连接上发控制命令的场景

---

## 6. Scenario YAML 完整格式

落地文件长这样（`$GIMBAL_HOME/scenarios/e2e.yaml`）：

```yaml
scenarioId: sc_e2e_checkout
meta:
  name: e2e_checkout
  description: 端到端冒烟测试
  module: default
  priority: 1
  author: prism
  owner: qa-team
  tags:
    - smoke
    - e2e
  version: 1.0.0
  createTime: 2026-06-25T14:23:01
  expire: false
  requirementRef: []
config:
  setup:
    - kind: setup
    - kind: setup_ref
      ref: setup_db
  teardown: []
  services:
    api.example.com: order_api
    auth.example.com: auth_api
  users:
    admin:
      url: https://auth.example.com/login
      username: admin
      password: <REDACTED>          # confirm_password=false 时自动改写
      expires_in: 7200
      token_type: Authorization
      token: ${auth.admin.token}    # 引用变量
  timePolicy:
    kind: record                    # record / timeout
    seconds: 60
  retry:
    kind: retry_policy
    maxAttempts: 3
    backoffSeconds: 20.0
    retryOn: [500, 502, 503]
resource:
  order_db:
    kind: mock
    name: order_db
    image: postgres:16
    config:
      env:
        POSTGRES_PASSWORD: test
    portMapping:
      5432: 5432
steps:
  - kind: step
    key: 1-login
    api:
      kind: api
      service: auth_api
      method: POST
      path: /api/user/login
      headers:
        Authorization: ${auth.admin.token}
      timeout: 30
    request:
      kind: request
      body:
        username: admin
        password: secret123
    strategy:
      - kind: assertion
        name: assert_status_1
        phase: verifying
        order: 0
        target: response_status
        operator: eq
        expected: 200
        message: POST /api/user/login 应返回 200
        soft: false
      - kind: extract
        name: extract_token
        phase: after_request
        order: 1
        expression: $.body.token
        target: var.token
        scope: scenario
        required: true
  - kind: step
    key: 2-submit_order
    api:
      kind: api
      service: order_api
      method: POST
      path: /api/order/submit
      headers:
        Authorization: ${auth.admin.token}
      timeout: 30
    request:
      kind: request
      params:
        trace_id: abc123
      body:
        product_id: 123
        qty: 2
    strategy:
      - kind: assertion
        name: assert_status_2
        phase: verifying
        order: 0
        target: response_status
        operator: eq
        expected: 201
        soft: false
      - kind: assertion
        name: assert_user_0
        phase: verifying
        order: 1
        target: response_body.status
        operator: eq
        expected: created
        soft: false
```

---

## 7. 退出码与日志

### 7.1 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 正常退出 (Ctrl+C) |
| `1` | 配置错误 (uvicorn 启动失败) |

### 7.2 日志

uvicorn 默认输出到 stdout，**结构化字段**：

```
[prism] GIMBAL_HOME=/home/user/.gimbal
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765
[capture] #1 GET /api/user/profile -> 200    # 来自 mitmdump 子进程
```

dev 模式 `--reload` 会监听 `gimbal/prism/server/` 目录的文件变更。

---

## 8. 常见问题

### Q1: 启动时 `prism UI not built`

prism 的前端是纯静态文件（`gimbal/prism/static/index.html`），需要单独构建。
clone 仓库后从 `prism-frontend` 子项目构建，或在 release 中下载。

### Q2: 浏览器看到旧版 UI

v0.5.5+ 已加 `Cache-Control: no-cache` 头给 `/static/*` 和 `/`、`/configure`。
若仍有问题，**强制刷新** (Ctrl+Shift+R) 或清浏览器缓存。

### Q3: 多用户同时编辑同一 session

v0 不支持 session 锁，**后写覆盖前写**。建议团队约定一个 sid 一次只开一个 tab。

### Q4: capture 在跑但 UI 看不到事件

排查：

```bash
# 1. capture 进程在跑?
ps aux | grep mitmdump

# 2. NDJSON 文件有内容?
ls -la ~/.gimbal/captures/active/
wc -l ~/.gimbal/captures/active/e2e.ndjson

# 3. prism 端能读到?
curl 'http://127.0.0.1:8765/api/captures?sid=e2e' | jq '.count'

# 4. SSE 连得通?
curl -N 'http://127.0.0.1:8765/api/captures/stream?sid=e2e' --max-time 5
```

### Q5: Export 失败 `schema_errors`

`POST /api/draft/{sid}/yaml` 不写盘，先调它看错误详情：

```json
{
  "errors": [
    {"field": "config.users.admin.url", "msg": "field required"},
    {"field": "steps.2.api.path", "msg": "string does not match regex \"^/\" "}
  ]
}
```

逐个修。

### Q6: 如何从已落地的 YAML 重新编辑？

```bash
# 1. 把现有 scenario 复制到 captures active
cp ~/.gimbal/scenarios/e2e.yaml /tmp/e2e-draft.json  # 手动转 JSON

# 2. 通过 API 注入 draft
curl -X PUT 'http://127.0.0.1:8765/api/draft/e2e' \
     -H "Content-Type: application/json" \
     -d @/tmp/e2e-draft.json

# 3. 浏览器打开 http://127.0.0.1:8765/configure?session=e2e
```

更好的方式是：直接用 `gimbal prism meta/config/user/resource` 等 CLI 子命令做小修小补（见 [prism-cli.md](./prism-cli.md)）。

### Q7: 怎么启用/禁用整个 step？

UI Steps Tab 里每个卡片有 `enabled` 复选框。也可在 `StepDraft` 数据模型上设 `enabled=False`。
**disabled step** 在 `build_scenario()` 时不会进入输出 `steps` 数组。

### Q8: 多个 capture 合并到同一 session？

```bash
# 把多个 NDJSON 拼接到一个 active 文件
cat captures/old/a.ndjson captures/old/b.ndjson > ~/.gimbal/captures/active/merged.ndjson

# 或用 API
curl -X POST 'http://127.0.0.1:8765/api/captures/import-from-path?sid=merged' \
     -H "Content-Type: application/json" \
     -d '{"path": "./captures/old/a.ndjson"}'
```
