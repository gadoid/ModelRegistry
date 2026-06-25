# `gimbal prism` CLI 模式 — 命令行配置器

> **目的**：用命令行把 NDJSON 转换为可运行的 GIMBAL Scenario YAML，并支持增量修改。
> 适合 CI/CD、批量处理、版本控制友好（YAML diff）、无浏览器场景。
>
> **设计原则**：每个子命令有明确边界；YAML I/O 复用 `gimbal.prism.core.load_scenario/save_scenario`；
> 与 web 模式共享同一 `build_scenario()` 渲染路径（[parity canary 测试](../../tests/test_prism_core_builder_parity.py) 保证字节级一致）。

---

## 目录

1. [快速开始](#1-快速开始)
2. [子命令一览](#2-子命令一览)
3. [Pipeline 子命令（5 个）](#3-pipeline-子命令5-个)
   - [`convert`](#31-convertndjson--config----scenario-yaml)
   - [`inspect`](#32-inspectndjson-统计)
   - [`validate`](#33-validateconfig-校验)
   - [`to-steps`](#34-to-stepsndjson--step-fragments)
   - [`explain`](#35-explainscenario-结构化摘要)
4. [Edit-by-section 子命令（4 组）](#4-edit-by-section-子命令4-组)
   - [`meta`](#41-meta-场景元数据)
   - [`user`](#42-user-认证用户)
   - [`resource`](#43-resource-依赖资源)
   - [`config`](#44-configconfig-section)
5. [配置文件格式](#5-配置文件格式)
6. [退出码](#6-退出码)
7. [典型工作流](#7-典型工作流)
8. [Web vs CLI 选型矩阵](#8-web-vs-cli-选型矩阵)

---

## 1. 快速开始

```bash
# 安装 (与 prism 同一入口)
pip install -e .

# 30 秒: NDJSON → Scenario YAML
gimbal prism convert -i captures/active/e2e.ndjson -o scenarios/e2e.yaml

# 加上 config (含 services 映射 / users / time policy 等)
gimbal prism convert -i e2e.ndjson -c config.yaml -o e2e.yaml

# 增量编辑
gimbal prism meta set e2e.yaml --name "checkout_smoke" --priority 1
gimbal prism user add e2e.yaml --key admin --username admin --password secret
gimbal prism config set e2e.yaml --time-policy-kind timeout --time-policy-seconds 120
gimbal prism validate -c e2e.yaml
gimbal prism explain e2e.yaml --json
```

---

## 2. 子命令一览

```
gimbal prism
├── start                 启动 web UI (与 prism.md 一致)
│
├── convert               NDJSON (+ config) → Scenario YAML
├── inspect               NDJSON → 统计信息 (methods/hosts/statuses)
├── validate              config YAML 校验
├── to-steps              NDJSON → step fragment JSON (中间产物)
├── explain               scenario YAML → 结构化摘要
│
├── meta                  场景元数据 (scenario_id / name / description / module / priority)
│   ├── get
│   └── set
├── user                  认证用户 (URL/username/password/...)
│   ├── list
│   ├── add
│   └── remove
├── resource              依赖资源 (mock/file/mock_ref/file_ref)
│   ├── list
│   ├── add
│   └── remove
└── config                config section (timePolicy / retry / services)
    ├── get
    └── set
```

10 个子命令（不含 `start`），按职责分两组：

- **Pipeline (5)**：端到端把 NDJSON 变 Scenario，CI 友好
- **Edit-by-section (4 组)**：对已有 scenario 做局部修改

---

## 3. Pipeline 子命令（5 个）

### 3.1 `convert` — NDJSON + config → Scenario YAML

**用法**：

```bash
gimbal prism convert --input <NDJSON> [--config <YAML>] [--output <YAML>] [OPTIONS]
```

| 参数 | 别名 | 必填 | 说明 |
|---|---|---|---|
| `--input` | `-i` | ✅ | NDJSON 文件 |
| `--config` | `-c` |  | 场景配置 YAML（services/users/timePolicy/...） |
| `--output` | `-o` |  | 输出 YAML 路径（缺省 stdout） |
| `--home` |  |  | `$GIMBAL_HOME` 覆盖（仅用于 ensure dir） |
| `--quiet` | `-q` |  | 静默模式（不打印 stderr 摘要） |

**示例**：

```bash
# A. 最简: NDJSON → stdout
gimbal prism convert -i e2e.ndjson

# B. 落地
gimbal prism convert -i e2e.ndjson -o scenarios/e2e.yaml

# C. 带 config (含 services 映射、users、timePolicy、retry 等)
gimbal prism convert -i e2e.ndjson -c config.yaml -o e2e.yaml

# D. CI 友好的退出码 (成功=0, 文件缺失=2, NDJSON 错=3, 内部=5)
gimbal prism convert -i e2e.ndjson -o e2e.yaml && echo "OK"
```

**输出**（写到 stderr）：

```
[prism convert] events=12 steps=8 output=/abs/scenarios/e2e.yaml
```

**config.yaml 示例**：

```yaml
# config.yaml
scenario_id: sc_e2e_checkout      # 可选; 不填则从 events[0] 推 (sc_<host>_<path>)
name: e2e_checkout
description: 端到端冒烟测试
module: default
priority: 1
author: qa-team
owner: qa-team
tags: [smoke, e2e]
version: 1.0.0
expire: false
requirement_ref: []

services:                           # host → service_name 映射
  api.example.com: order_api
  auth.example.com: auth_api

users:                              # key → AuthDraft
  admin:
    url: https://auth.example.com/login
    username: admin
    password: secret123
    expires_in: 7200
    token_type: Authorization

time_policy:
  kind: record                      # record / timeout
  seconds: 60

retry:
  enabled: true
  max_attempts: 3
  backoff_seconds: 20.0
  retry_on: [500, 502, 503]

setup_refs: [setup_db]
teardown_refs: []

resources:                          # 4 种 kind: mock / mock_ref / file / file_ref
  order_db:
    kind: mock
    image: postgres:16
    config:
      env:
        POSTGRES_PASSWORD: test
    port_mapping:
      "5432": 5432
```

---

### 3.2 `inspect` — NDJSON 统计

**用法**：

```bash
gimbal prism inspect --input <NDJSON> [--limit <N>] [--json]
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--input` / `-i` | 必填 | NDJSON 文件 |
| `--limit` | `3` | sample 事件数 |
| `--json` | `False` | JSON 输出（缺省人读友好） |

**示例**：

```bash
$ gimbal prism inspect -i e2e.ndjson
events: 12
methods: {'GET': 8, 'POST': 4}
hosts: {'api.example.com': 10, 'auth.example.com': 2}
statuses: {200: 11, 201: 1}
sample (first 3):
  GET    /api/user/profile                   -> 200
  POST   /api/order/submit                   -> 201
  GET    /api/order/12345                    -> 200
```

```bash
# JSON 形式 (给 jq / 脚本用)
$ gimbal prism inspect -i e2e.ndjson --json | jq '.event_count'
12
```

**用途**：

- 快速检查抓包是否成功、是否抓到想要的接口
- 决定 services 映射（看 `hosts`）
- 给上游 dashboard 喂数据

---

### 3.3 `validate` — config 校验

**用法**：

```bash
gimbal prism validate --config <YAML>
```

**示例**：

```bash
$ gimbal prism validate -c config.yaml
[prism validate] OK: config.yaml   # 退出码 0

$ gimbal prism validate -c bad.yaml
  - 1 validation error for Scenario
  - config -> users -> admin -> url
    field required
  (退出码 4)
```

**注意**：`validate` 只校验 `config.yaml` 的元数据完整性（不依赖 NDJSON），
内部用 synthetic event 走一遍 `build_scenario`。
完整的 scenario YAML 校验（带 steps）请用 web 端 `POST /api/draft/{sid}/yaml` 或 `gimbal prism explain`。

---

### 3.4 `to-steps` — NDJSON → step fragments

**用法**：

```bash
gimbal prism to-steps --input <NDJSON> [--config <YAML>] [--output <JSON>]
```

**示例**：

```bash
# 输出到 stdout (JSON)
gimbal prism to-steps -i e2e.ndjson | jq '.[0]'
```

```json
{
  "api": {
    "kind": "api",
    "service": "api.example.com",
    "method": "POST",
    "path": "/api/order/submit",
    "headers": {},
    "timeout": 30
  },
  "request": {
    "kind": "request",
    "body": {"product_id": 123, "qty": 2}
  },
  "_captured_response": {
    "status": 201
  }
}
```

**用途**：

- **调试**：检查 capture → step 转换是否符合预期
- **拼接**：把多个 capture 的 steps 拼成一个 scenario
- **自定义**：写脚本用 step fragments 生成你想要的 scenario 结构

**注意**：step fragments 不是完整 scenario 格式（缺 meta/config/resource 等），
要落地完整 scenario 用 `convert`。

---

### 3.5 `explain` — scenario 结构化摘要

**用法**：

```bash
gimbal prism explain <SCENARIO_YAML> [--section <KEY>] [--json]
```

| 参数 | 说明 |
|---|---|
| `SCENARIO` | scenario YAML 路径（位置参数） |
| `--section` | 仅输出某个 section (`scenarioId` / `meta` / `config` / `steps_count` / `resources`) |
| `--json` | JSON 输出（默认也是 JSON，但可与 `--section` 组合） |

**示例**：

```bash
$ gimbal prism explain scenarios/e2e.yaml
{
  "scenarioId": "sc_e2e_checkout",
  "meta": {
    "name": "e2e_checkout",
    "description": "端到端冒烟测试",
    "module": "default",
    "priority": 1,
    "author": "qa-team",
    "owner": "qa-team",
    "tags": ["smoke", "e2e"],
    "version": "1.0.0"
  },
  "config": {
    "services": ["order_api", "auth_api"],
    "users": ["admin"],
    "timePolicy": {"kind": "record", "seconds": 60},
    "retry": {"kind": "retry_policy", "maxAttempts": 3, ...}
  },
  "steps_count": 8,
  "resources": ["order_db"]
}
```

```bash
# 只看 meta
$ gimbal prism explain e2e.yaml --section meta | jq '.name'
"e2e_checkout"

# 给 dashboard 喂数据
$ gimbal prism explain e2e.yaml --json | curl -X POST -H "Content-Type: application/json" -d @- https://dashboard/api/scenarios
```

---

## 4. Edit-by-section 子命令（4 组）

> 所有 edit 子命令都**就地修改** scenario YAML（load → 修改 → save），
> `--dry-run`（部分支持）只打印不写盘。

### 4.1 `meta` — 场景元数据

#### `meta get`

```bash
gimbal prism meta get <SCENARIO> [--field <KEY>]
```

```bash
$ gimbal prism meta get e2e.yaml
{
  "name": "e2e_checkout",
  "description": "端到端冒烟测试",
  "module": "default",
  "priority": 1,
  ...
}

$ gimbal prism meta get e2e.yaml --field name
{"name": "e2e_checkout"}
```

#### `meta set`

```bash
gimbal prism meta set <SCENARIO> [--name <STR>] [--description <STR>] \
                             [--module <STR>] [--priority <INT>] [--dry-run]
```

至少要传一个字段。

```bash
$ gimbal prism meta set e2e.yaml --name "checkout_smoke" --priority 1
[prism meta set] updated: ['name', 'priority']

# dry-run: 不写盘
$ gimbal prism meta set e2e.yaml --name "test_v2" --dry-run
{"name": "test_v2", ...}
```

**可改字段**：

| 字段 | 说明 |
|---|---|
| `--name` | 场景名（必填项，但 CLI 接受空） |
| `--description` | 描述 |
| `--module` | 模块名（用于分类） |
| `--priority` | 优先级（数字越小越高） |

其他 meta 字段（`tags` / `version` / `author` / `owner` / `expire` / `requirement_ref`）
请直接编辑 YAML 或扩展 CLI。

---

### 4.2 `user` — 认证用户

#### `user list`

```bash
gimbal prism user list <SCENARIO>
```

```bash
$ gimbal prism user list e2e.yaml
[
  {
    "key": "admin",
    "url": "https://auth.example.com/login",
    "username": "admin",
    "password": "<REDACTED>",
    "expires_in": 7200,
    "token_type": "Authorization"
  }
]
```

#### `user add`

```bash
gimbal prism user add <SCENARIO> --key <KEY> [--url <URL>] [--username <USER>] \
                                 [--password <PW>] [--expires-in <SEC>] [--token-type <STR>]
```

```bash
$ gimbal prism user add e2e.yaml --key admin \
    --url https://auth.example.com/login \
    --username admin --password secret123 \
    --expires-in 7200 --token-type Authorization
[prism user add] added: admin
```

**注意**：

- `--key` 必填（引用 user 的变量名，如 `${auth.admin.token}`）
- `--password` 落地时如果未确认，会被改写为 `<REDACTED>`（需在 export 时 `confirm_password=true`）
  （CLI 当前未实现 confirm flag；如需存明文请直接编辑 YAML）

#### `user remove`

```bash
gimbal prism user remove <SCENARIO> --key <KEY>
```

```bash
$ gimbal prism user remove e2e.yaml --key admin
[prism user remove] removed: admin

$ gimbal prism user remove e2e.yaml --key non-existent
user not found: non-existent   (退出码 6)
```

---

### 4.3 `resource` — 依赖资源

#### `resource list`

```bash
gimbal prism resource list <SCENARIO>
```

```bash
$ gimbal prism resource list e2e.yaml
[
  {
    "name": "order_db",
    "kind": "mock",
    "image": "postgres:16",
    "config": {...},
    "portMapping": {"5432": 5432}
  }
]
```

#### `resource add`

```bash
gimbal prism resource add <SCENARIO> --name <NAME> [--kind <KIND>] \
                                    [--image <IMAGE>] [--port <HOST:CONT>]
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `--name` | ✅ | 资源名（scenario 内唯一） |
| `--kind` |  | `mock` (默认) / `mock_ref` / `file` / `file_ref` |
| `--image` |  | `mock` 的 docker image |
| `--port` |  | `host:container` 形式（如 `5432:5432`），可多次传 |

```bash
# mock 服务
$ gimbal prism resource add e2e.yaml --name order_db --kind mock \
    --image postgres:16 --port 5432:5432
[prism resource add] added: order_db

# 文件资源
$ gimbal prism resource add e2e.yaml --name test_data --kind file --path /tmp/test.json
```

**注意**：复杂配置（如 `config` env / `value` / `ref`）请直接编辑 YAML。

#### `resource remove`

```bash
gimbal prism resource remove <SCENARIO> --name <NAME>
```

```bash
$ gimbal prism resource remove e2e.yaml --name order_db
[prism resource remove] removed: order_db
```

---

### 4.4 `config` — config section

**config** 下的子对象：`timePolicy` / `retry` / `services` / `users`（独立命令）/ `setup` / `teardown`。

#### `config get`

```bash
gimbal prism config get <SCENARIO> [--field <KEY>]
```

| 字段 | 含义 |
|---|---|
| `timePolicy` (默认) | 时间策略 |
| `retry` | 重试策略 |
| `services` | services 映射 |
| `setup` / `teardown` | setup/teardown refs |
| `users` | （建议用 `user list`，输出格式更友好） |

```bash
$ gimbal prism config get e2e.yaml --field timePolicy
{
  "kind": "record",
  "seconds": 60
}

$ gimbal prism config get e2e.yaml --field services
{
  "api.example.com": "order_api",
  "auth.example.com": "auth_api"
}

$ gimbal prism config get e2e.yaml --field retry
{
  "kind": "retry_policy",
  "maxAttempts": 3,
  "backoffSeconds": 20.0,
  "retryOn": [500, 502, 503]
}
```

#### `config set`

```bash
gimbal prism config set <SCENARIO> [OPTIONS]
```

至少要传一个字段。CLI 接受 **flat camelCase flags**（推荐）：

| 参数 | 说明 |
|---|---|
| `--time-policy-kind` | `record` / `timeout` |
| `--time-policy-seconds` | int |
| `--retry-enabled` / `--no-retry-enabled` | bool flag（typer 双标志） |
| `--retry-max-attempts` | int |
| `--retry-backoff-seconds` | float |
| ~~`--retry-on`~~ | （v0 未实现，请直接编辑 YAML） |

```bash
# 把时间策略从 record 改成 timeout 120s
$ gimbal prism config set e2e.yaml \
    --time-policy-kind timeout --time-policy-seconds 120
[prism config set] updated: ['timePolicyKind', 'timePolicySeconds']

# 启用 retry, 3 次重试, backoff 5s
$ gimbal prism config set e2e.yaml \
    --retry-enabled \
    --retry-max-attempts 3 \
    --retry-backoff-seconds 5.0
[prism config set] updated: ['retryEnabled', 'retryMaxAttempts', 'retryBackoffSeconds']

# 关闭 retry
$ gimbal prism config set e2e.yaml --no-retry-enabled
[prism config set] updated: ['retryEnabled']
```

**底层行为**：

- `retryEnabled=False` 且无其他 retry 字段 → `config["retry"] = None`
- 其他字段自动 merge 进现有 `timePolicy` / `retry` dict
- 每次写盘前**重新校验** Scenario，校验失败会回滚（不写盘）并 stderr 报字段错误

---

## 5. 配置文件格式

### 5.1 `config.yaml`（`prism convert --config` 用）

完整字段见 [3.1 config.yaml 示例](#31-convert--ndjson--config----scenario-yaml)。

最小：

```yaml
services:
  api.example.com: my_api
```

默认行为（不传 config）：

- `scenario_id` = `sc_<host>_<path>` 推得
- `name` = `scenario_id`
- `description` = `""`
- `module` = `"default"`
- `priority` = `1`
- `tags` = `["smoke"]`
- `users` = `{}`
- `timePolicy` = `{kind: record}`
- `retry` = `None`
- `resources` = `{}`

### 5.2 `filters.yaml`（`capture start --filter-file` 用）

完整字段见 [capture.md §4.2](./capture.md#42-yaml-格式)。

### 5.3 Scenario YAML 格式

`prism convert` 输出的 YAML 就是 schema 定义的 Scenario 格式。
完整样例见 [prism.md §6](./prism.md#6-scenario-yaml-完整格式)。

---

## 6. 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 参数错误 / 未知 section / 至少一个字段必填 |
| `2` | 文件不存在 (input/config/scenario) |
| `3` | NDJSON / JSON 解析错误 |
| `4` | Pydantic schema 校验失败 |
| `5` | 内部错误 (未捕获异常) |
| `6` | 字段未找到 (user/resource/...) |

**CI 用法**：

```bash
set -euo pipefail

gimbal prism convert -i e2e.ndjson -c config.yaml -o e2e.yaml \
    || { echo "convert failed"; exit 1; }

gimbal prism validate -c config.yaml \
    || { echo "validate failed"; exit 4; }

gimbal prism user list e2e.yaml | jq -e 'length > 0' \
    || { echo "no users configured"; exit 1; }
```

---

## 7. 典型工作流

### 7.1 一次性生成

```bash
# 1. 抓包
gimbal capture start -s e2e -f /api/
# 浏览器操作...
# Ctrl+C

# 2. 生成 scenario
gimbal prism convert \
    -i ~/.gimbal/captures/archive/2026-06-25/e2e-XXX.ndjson \
    -c config.yaml \
    -o ~/.gimbal/scenarios/e2e.yaml

# 3. 验证
gimbal prism validate -c config.yaml

# 4. 看摘要
gimbal prism explain e2e.yaml
```

### 7.2 增量迭代（CI/CD 友好）

```bash
# 在已有 scenario 上小改小补
gimbal prism meta set e2e.yaml --description "v2 优化"
gimbal prism user add e2e.yaml --key viewer --username v --password v
gimbal prism config set e2e.yaml --time-policy-seconds 180

# diff
git diff scenarios/e2e.yaml
```

### 7.3 批量处理

```bash
# 批量转换 10 个 NDJSON
for f in captures/active/*.ndjson; do
    sid=$(basename "$f" .ndjson)
    gimbal prism convert -i "$f" -o "scenarios/${sid}.yaml"
done

# 批量加 tag
for f in scenarios/*.yaml; do
    gimbal prism meta set "$f" --module e2e
done
```

### 7.4 调试 capture → step 转换

```bash
# 看前 3 个事件
gimbal prism inspect -i e2e.ndjson

# 看每个事件转成什么 step
gimbal prism to-steps -i e2e.ndjson | jq '.[0]'

# 直接尝试生成 (不写盘, 看 stdout)
gimbal prism convert -i e2e.ndjson -c config.yaml
```

### 7.5 与 web 端协作

```bash
# 1. CLI 抓包 + 转换
gimbal capture start -s e2e
# ... 浏览器操作 ...
# Ctrl+C
gimbal prism convert -i ~/.gimbal/captures/archive/.../e2e-XXX.ndjson \
                     -o ~/.gimbal/scenarios/e2e.yaml

# 2. CLI 做局部微调
gimbal prism meta set e2e.yaml --priority 2

# 3. Web 端做精修 (拖拽, 调断言, ...)
# 浏览器打开 http://127.0.0.1:8765/configure?session=e2e
# （注：web 端 session 是 in-memory draft, 不会反向覆盖 YAML）
```

---

## 8. Web vs CLI 选型矩阵

| 任务 | Web (prism UI) | CLI (prism-cli) | 说明 |
|---|---|---|---|
| 抓包实时观察事件流 | ✅ (SSE) | ❌ | web 强项 |
| 拖拽 step / 排序 | ✅ | ❌ | web 强项 |
| 写复杂 assertions | ✅ (表单校验) | ❌ | web 强项 |
| 写 extracts/assigns | ✅ | ❌ | web 强项 |
| CI/CD 集成 | ❌ | ✅ | CLI 强项 |
| YAML diff / git 友好 | ❌ | ✅ | CLI 强项 |
| 批量处理 10+ scenarios | ❌ | ✅ (shell 循环) | CLI 强项 |
| 远程 / SSH 环境 | ❌ | ✅ | CLI 强项 |
| 快速修复 1-2 个字段 | ⚠️ (要打开浏览器) | ✅ (1 行命令) | CLI 强项 |
| 探索 capture 统计 | ⚠️ (要打开浏览器) | ✅ (`inspect`) | CLI 强项 |
| 校验 schema | ⚠️ (要打开浏览器) | ✅ (`validate`) | CLI 强项 |
| 看 scenario 摘要 | ⚠️ (要打开浏览器) | ✅ (`explain`) | CLI 强项 |

**推荐混合工作流**：

1. **抓包 + 转换** → CLI (`capture start` + `prism convert`)
2. **小修小补**（meta / user / config） → CLI (`prism meta set` 等)
3. **精修**（拖拽、调断言、写 extracts） → Web (`prism start` + 浏览器)
4. **CI 验证** → CLI (`prism validate` + `prism explain` + `prism config set`)

---

## 附录：完整字段速查

| 子命令 | 字段 | 类型 | 默认 |
|---|---|---|---|
| `convert` | `--input` | Path | 必填 |
|  | `--config` | Path | None |
|  | `--output` | Path | stdout |
| `inspect` | `--limit` | int | 3 |
| `meta set` | `--name` `--description` `--module` `--priority` | str/int | None |
| `user add` | `--key` `--url` `--username` `--password` `--expires-in` `--token-type` | str | None/""/7200/"Authorization" |
| `resource add` | `--name` `--kind` `--image` `--port` | str | None/"mock"/""/None |
| `config set` | `--time-policy-kind` `--time-policy-seconds` | str/int | None |
|  | `--retry-enabled` / `--no-retry-enabled` | bool flag | None |
|  | `--retry-max-attempts` `--retry-backoff-seconds` | int/float | None |
