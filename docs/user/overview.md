# gimbal: capture → prism → run 端到端指南

> **gimbal** 是一个**数据驱动测试用例**配置平台。
> 把浏览器/客户端抓到的 HTTP 流量（NDJSON）转换为 GIMBAL 可运行的 Scenario YAML。
>
> 本指南是 [capture.md](./capture.md)、[prism.md](./prism.md)、[prism-cli.md](./prism-cli.md) 的端到端串联。

---

## 目录

1. [gimbal 是什么](#1-gimbal-是什么)
2. [整体架构](#2-整体架构)
3. [三种角色，三种使用方式](#3-三种角色三种使用方式)
4. [端到端工作流（5 步）](#4-端到端工作流5-步)
5. [关键概念](#5-关键概念)
6. [$GIMBAL_HOME 目录约定](#6-gimbal_home-目录约定)
7. [Web vs CLI 决策树](#7-web-vs-cli-决策树)
8. [常见任务速查](#8-常见任务速查)

---

## 1. gimbal 是什么

**GIMBAL** 是一个测试用例管理平台，scenario YAML 是其核心 artifact：

```yaml
scenarioId: sc_e2e_checkout
meta:
  name: 端到端冒烟测试
  ...
config:
  services: {...}
  users: {...}
  timePolicy: {...}
  retry: {...}
steps:
  - key: 1-login
    api: {method: POST, path: /api/user/login, ...}
    request: {body: {...}}
    strategy:
      - {kind: assertion, expected: 200, ...}
      - {kind: extract, target: var.token, ...}
  - key: 2-submit_order
    ...
```

**痛点**：手写 100 个 scenario 太累、容易错、对新人门槛高。

**gimbal 的方案**：让真人去操作真实业务（点按钮、提交订单），mitmproxy 抓 HTTP 流量，
prism 配置器把流量**编辑/补充/校验**成可运行的 Scenario YAML。

---

## 2. 整体架构

```
                    gimbal 系统边界
                    ═══════════════
                                                          
  ┌─────────────┐   mitmproxy  ┌────────────────────────┐
  │ 浏览器/客户端 │ ──────────▶ │  capture 子系统         │
  │ (代理:8080) │             │  (mitmdump + addon)    │
  └─────────────┘             └───────────┬────────────┘
                                          │ 追加写
                                          ▼
                              ┌────────────────────────┐
                              │  NDJSON 文件            │
                              │  $GIMBAL_HOME/         │
                              │  captures/active/      │
                              │  {sid}.ndjson          │
                              └───────────┬────────────┘
                                          │
                  ┌───────────────────────┴─────────────────────┐
                  │                                              │
                  ▼                                              ▼
   ┌──────────────────────────┐                  ┌────────────────────────┐
   │  prism Web UI             │                  │  prism-cli (命令行)     │
   │  (FastAPI + 静态前端)     │                  │  (Typer)               │
   │                          │                  │                        │
   │  4-Tab:                  │                  │  10 子命令:             │
   │  - Captures             │                  │  convert/inspect/      │
   │  - Steps                │                  │  validate/to-steps/    │
   │  - Config               │                  │  explain/meta/user/    │
   │  - Resources            │                  │  resource/config       │
   └──────────┬───────────────┘                  └──────────┬─────────────┘
              │                                             │
              └──────────────────┬──────────────────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │  shared core                │
                  │  (build_scenario + schema)  │
                  │  ──────────────────────────  │
                  │  parity canary test 保证    │
                  │  web / CLI 字节级一致       │
                  └──────────┬──────────────────┘
                             │
                             ▼
                  $GIMBAL_HOME/scenarios/{sid}.yaml
                             │
                             ▼
                  ┌─────────────────────────────┐
                  │  GIMBAL 执行器 (其他项目)    │
                  │  - 读 scenario YAML         │
                  │  - 启动 mock / 真服务        │
                  │  - 跑 step / 收集 metric    │
                  │  - 报告                     │
                  └─────────────────────────────┘
```

**关键设计**：

1. **Schema 是 SSOT**：所有 Pydantic model 在 `gimbal/schema/`，前端表单从 `/api/schema/ui-spec` 反射生成
2. **Web 和 CLI 共享 core**：`gimbal/prism/core.py` 是唯一渲染入口，[parity canary test](../../tests/test_prism_core_builder_parity.py) 防止漂移
3. **无 I/O 纯函数**：`gimbal/prism/convert.py` 只做 record→fragment，文件 I/O 在 `gimbal/io_utils.py`

---

## 3. 三种角色，三种使用方式

### 角色 A: **测试开发**（写新 scenario）

```bash
# 1. 抓包
gimbal capture start -s new-feature

# 2. 用 Web UI 精修 (拖拽、调断言、写 extracts)
gimbal prism start
# 浏览器打开 http://127.0.0.1:8765/configure?session=new-feature

# 3. Export
# (UI 上点 Export) → $GIMBAL_HOME/scenarios/new-feature.yaml
```

### 角色 B: **DevOps / SRE**（CI/CD 集成）

```bash
# 1. CI 任务里下载 capture artifact
# 2. 自动转换
gimbal prism convert -i captures.ndjson -c config.yaml -o scenario.yaml

# 3. 校验
gimbal prism validate -c config.yaml

# 4. 部署
cp scenario.yaml $GIMBAL_HOME/scenarios/
```

### 角色 C: **测试维护**（修改已有 scenario）

```bash
# 1. 改 meta
gimbal prism meta set scenarios/login.yaml --description "v2: 加入 2FA"

# 2. 加 user
gimbal prism user add scenarios/login.yaml --key admin2 --username admin2

# 3. 调 retry
gimbal prism config set scenarios/login.yaml --retry-enabled --retry-max-attempts 5

# 4. 看结果
gimbal prism explain scenarios/login.yaml
```

---

## 4. 端到端工作流（5 步）

### 步骤 1: 准备 GIMBAL_HOME

```bash
export GIMBAL_HOME=~/.gimbal
mkdir -p $GIMBAL_HOME/{captures/active,captures/archive,scenarios}

# 可选: 安装 mitmproxy CA
# 访问 http://mitm.it 下载安装
```

### 步骤 2: 抓包

**简单场景**：

```bash
gimbal capture start -s my-sid
# 浏览器代理: 127.0.0.1:8080
# 业务操作
# Ctrl+C
```

**复杂场景**（多 profile / 跨文件 / 排除静态资源）：

```bash
# 写 filters.yaml
cat > filters.yaml <<'EOF'
mode: include
default_profile: e2e
profiles:
  e2e:
    rules:
      - path_glob: "/api/*"
        methods: [GET, POST, PUT, DELETE]
      - mode: exclude
        path: /api/static
      - mode: exclude
        path_regex: "\\.(png|jpg|css|js)$"
EOF

gimbal capture start -s my-sid \
    --filter-file ./filters.yaml \
    --filter-profile e2e
```

### 步骤 3: 转换为 Scenario

**Web 方式**（适合需要精修）：

```bash
gimbal prism start
# 浏览器: http://127.0.0.1:8765/configure?session=my-sid
# 编辑 → Export → 落地到 $GIMBAL_HOME/scenarios/my-sid.yaml
```

**CLI 方式**（适合 CI / 一次性生成）：

```bash
# 找到最新归档的 NDJSON
NDJSON=$(ls -t $GIMBAL_HOME/captures/archive/2026-06-25/my-sid-*.ndjson | head -1)

# 写 config.yaml
cat > config.yaml <<'EOF'
services:
  api.example.com: order_api
  auth.example.com: auth_api
users:
  admin:
    url: https://auth.example.com/login
    username: admin
    password: secret123
    expires_in: 7200
    token_type: Authorization
time_policy:
  kind: timeout
  seconds: 120
EOF

# 转换
gimbal prism convert -i $NDJSON -c config.yaml -o $GIMBAL_HOME/scenarios/my-sid.yaml
```

### 步骤 4: 验证

```bash
# 校验 config 完整性
gimbal prism validate -c config.yaml

# 看摘要
gimbal prism explain $GIMBAL_HOME/scenarios/my-sid.yaml

# 完整结构校验 (等价于 web 的 /api/draft/{sid}/yaml)
# 通过 web 端:
gimbal prism start
# 浏览器: PUT draft → POST yaml (看 422 错误)
```

### 步骤 5: 执行

```bash
# GIMBAL 执行器在其他项目, 通过 $GIMBAL_HOME/scenarios/{sid}.yaml 加载
# 这里只列出环境变量和路径
ls $GIMBAL_HOME/scenarios/
# e2e.yaml
# login.yaml
# my-sid.yaml  ← 新生成的
```

---

## 5. 关键概念

### 5.1 NDJSON = "数据驱动" = capture-driven

**注意**：gimbal 的"数据驱动"是 **capture-driven**，不是 parameter × rows。

- ✅ 一条 NDJSON 就是一个**完整业务流**（登录→加购→下单→支付）
- ❌ 不是 "用 1 个模板 × 100 个用户"

每个 NDJSON 事件 → Scenario step，1:1 映射。

### 5.2 Schema = SSOT

`gimbal/schema/` 下的 Pydantic model 是**单一事实源**：

- 后端构建用
- Web 前端表单从 `/api/schema/ui-spec` 反射生成
- CLI flag 名直接对应 schema 字段

**改 schema = 改协议**，要同时更新：
1. `gimbal/schema/*.py` (model 定义)
2. `gimbal/prism/builder/*.py` (Draft → schema 转换)
3. Web 前端 (`gimbal/prism/static/`) - 若已构建
4. 测试

### 5.3 4 种 Resource

| kind | 用途 | 必填字段 |
|---|---|---|
| `mock` | 内嵌 mock 服务（起 docker 容器） | `image`, `portMapping`, `config` |
| `mock_ref` | 引用 ModelRegistry 已注册的 mock | `ref` |
| `file` | 内嵌文件（注入到容器） | `path` |
| `file_ref` | 引用已注册的文件 | `ref` |

### 5.4 Strategy 三种

| kind | phase | 作用 |
|---|---|---|
| `assertion` | `verifying` | 校验值（status/body 等） |
| `extract` | `after_request` | 提取变量给后续 step 用 |
| `assign` | `before_request` | 在请求前赋值（如随机 trace_id） |

### 5.5 Time Policy 两种

| kind | 含义 |
|---|---|
| `record` | 录制模式（默认）。按 capture 的时间间隔重放，模拟真实用户节奏 |
| `timeout` | 超时模式。每个 step 等 N 秒无响应就 fail（不重放时间） |

### 5.6 Retry Policy

```
retry:
  enabled: true
  max_attempts: 3
  backoff_seconds: 20.0
  retry_on: [500, 502, 503]    # 哪些状态码触发重试
```

---

## 6. $GIMBAL_HOME 目录约定

```
$GIMBAL_HOME/                  默认 ~/.gimbal
├── captures/                  capture 子系统落地
│   ├── active/                正在写入
│   │   ├── {sid}.ndjson
│   │   └── {sid}.lock         哨兵文件 (v0.5.2+)
│   └── archive/{YYYY-MM-DD}/  Ctrl+C / 手动归档
│       └── {sid}-{epoch}.ndjson
│
├── scenarios/                 落地 Scenario YAML (prism 输出)
│   ├── e2e.yaml
│   ├── login.yaml
│   └── checkout.yaml
│
└── (其他: logs/, exports/, ... 各子系统按需添加)
```

**多项目隔离**：

```bash
# 项目 A
export GIMBAL_HOME=~/.gimbal/project-a
gimbal prism start

# 项目 B
export GIMBAL_HOME=~/.gimbal/project-b
gimbal prism start --port 8766
```

---

## 7. Web vs CLI 决策树

```
开始：你要做什么？
│
├─ 一次性抓包并生成 scenario
│  ├─ 需要精修（拖拽、调断言、写 extracts）
│  │  └─→ capture + prism (web)            [capture.md, prism.md]
│  └─ 标准流程（不改 event）
│     └─→ capture + prism convert (CLI)    [capture.md, prism-cli.md]
│
├─ 改已有 scenario
│  ├─ 改 1-2 个字段（meta/user/config）
│  │  └─→ prism meta/user/config set (CLI) [prism-cli.md §4]
│  ├─ 改 step 顺序 / 调断言 / 写 extracts
│  │  └─→ prism (web)                       [prism.md]
│  └─ 看 scenario 摘要
│     └─→ prism explain (CLI)               [prism-cli.md §3.5]
│
├─ CI/CD
│  └─→ prism convert + validate + explain   [prism-cli.md §7.2]
│
├─ 批量处理 10+ scenarios
│  └─→ prism CLI 循环                       [prism-cli.md §7.3]
│
└─ 调试 / 探索
   ├─ 看 capture 统计
   │  └─→ prism inspect (CLI)               [prism-cli.md §3.2]
   ├─ 看 capture → step 转换
   │  └─→ prism to-steps (CLI)              [prism-cli.md §3.4]
   └─ 校验 config
      └─→ prism validate (CLI)              [prism-cli.md §3.3]
```

---

## 8. 常见任务速查

### 8.1 第一次跑通

```bash
# A 终端
gimbal capture start -s hello

# B 终端
curl -x http://127.0.0.1:8080 https://httpbin.org/get?x=1

# A 终端 Ctrl+C

# 生成 scenario
gimbal prism convert -i ~/.gimbal/captures/archive/*/hello-*.ndjson -o /tmp/hello.yaml

# 看结果
gimbal prism explain /tmp/hello.yaml
```

### 8.2 在已有 scenario 上加 user

```bash
gimbal prism user add scenarios/e2e.yaml \
    --key admin \
    --url https://auth.example.com/login \
    --username admin \
    --password secret123
```

### 8.3 启用 retry

```bash
gimbal prism config set scenarios/e2e.yaml \
    --retry-enabled \
    --retry-max-attempts 3 \
    --retry-backoff-seconds 5.0
```

### 8.4 改时间策略为 timeout

```bash
gimbal prism config set scenarios/e2e.yaml \
    --time-policy-kind timeout \
    --time-policy-seconds 120
```

### 8.5 加 mock 资源

```bash
# 方式 1: CLI
gimbal prism resource add scenarios/e2e.yaml \
    --name order_db --kind mock \
    --image postgres:16 --port 5432:5432

# 方式 2: 直接编辑 YAML
vim scenarios/e2e.yaml
# 在 resource: 块加:
#   order_db:
#     kind: mock
#     image: postgres:16
#     portMapping: {5432: 5432}
```

### 8.6 多 capture 合并

```bash
# 把多个 NDJSON 拼成一个
cat $GIMBAL_HOME/captures/archive/2026-06-25/a-*.ndjson \
    $GIMBAL_HOME/captures/archive/2026-06-25/b-*.ndjson \
    > /tmp/merged.ndjson

gimbal prism convert -i /tmp/merged.ndjson -o /tmp/merged.yaml
```

### 8.7 排除静态资源

写 `filters.yaml`：

```yaml
mode: include
default_profile: api-only
profiles:
  api-only:
    rules:
      - path_glob: "/api/*"
      - mode: exclude
        path_regex: "\\.(png|jpg|jpeg|gif|css|js|ico|svg|woff2?)$"
```

```bash
gimbal capture start -s e2e --filter-file ./filters.yaml
```

### 8.8 看 scenario 长什么样

```bash
gimbal prism explain scenarios/e2e.yaml
gimbal prism explain scenarios/e2e.yaml --section meta
gimbal prism explain scenarios/e2e.yaml --json | jq '.steps_count'
```

### 8.9 调试 capture → step 转换

```bash
# 看每条 event 转成什么 step
gimbal prism to-steps -i capture.ndjson | jq '.[0]'

# 对比转换前后的字段映射
gimbal prism inspect -i capture.ndjson --json > before.json
gimbal prism to-steps -i capture.ndjson | jq 'map({method: .api.method, path: .api.path, status: ._captured_response.status})' > after.json
diff <(jq -S 'sort' before.json) <(jq -S 'sort' after.json)
```

### 8.10 清理

```bash
# 清空某个 session 的 active 文件
gimbal prism start  # web
# 浏览器: DELETE /api/captures?sid=xxx

# 或直接 rm
rm $GIMBAL_HOME/captures/active/xxx.ndjson
rm $GIMBAL_HOME/captures/active/xxx.lock  # 如果残留

# 删除 30 天前的归档
find $GIMBAL_HOME/captures/archive/ -name "*.ndjson" -mtime +30 -delete
```

---

## 附录 A: 一页纸 cheat sheet

```bash
# 抓包
gimbal capture start -s SID [--filter-file FILE] [--filter-profile PROF] [--filter CSV]
gimbal capture list
gimbal capture show SID [-n 50]
gimbal capture archive SID

# 转换 + 校验
gimbal prism convert -i NDJSON [-c CONFIG] [-o OUTPUT]
gimbal prism inspect -i NDJSON [--json]
gimbal prism validate -c CONFIG
gimbal prism to-steps -i NDJSON [-c CONFIG] [-o OUTPUT]
gimbal prism explain SCENARIO [--section KEY] [--json]

# 增量编辑
gimbal prism meta {get|set} SCENARIO [--name N] [--description D] [--module M] [--priority P]
gimbal prism user {list|add|remove} SCENARIO [--key K] [--url U] [--username U] [--password P]
gimbal prism resource {list|add|remove} SCENARIO [--name N] [--kind K] [--image I] [--port H:C]
gimbal prism config {get|set} SCENARIO [--time-policy-kind K] [--time-policy-seconds S]
                                       [--retry-enabled/--no-retry-enabled]
                                       [--retry-max-attempts N] [--retry-backoff-seconds S]

# Web UI
gimbal prism start [--host H] [--port P] [--home DIR] [--reload]
```

## 附录 B: 关键文件路径

| 路径 | 作用 |
|---|---|
| `$GIMBAL_HOME/captures/active/{sid}.ndjson` | capture 落地 NDJSON |
| `$GIMBAL_HOME/captures/active/{sid}.lock` | 哨兵文件（v0.5.2+） |
| `$GIMBAL_HOME/captures/archive/{YYYY-MM-DD}/{sid}-{epoch}.ndjson` | 归档 |
| `$GIMBAL_HOME/scenarios/{sid}.yaml` | prism 输出 Scenario |
| `gimbal/schema/*.py` | SSOT Pydantic model |
| `gimbal/prism/core.py` | 共享 pipeline (web + CLI 入口) |
| `gimbal/prism/builder/*.py` | Draft → schema 转换 |
| `gimbal/prism/server/` | FastAPI web 后端 |
| `gimbal/prism/cli/` | Typer CLI 子命令 |
| `gimbal/prism/static/` | Web 前端 (index.html, app.js, style.css) |
| `gimbal/capture/*.py` | 抓包子系统 |
| `tests/test_prism_core_builder_parity.py` | web/CLI 字节级一致 canary |

## 附录 C: 版本演进

| 版本 | 关键变化 |
|---|---|
| v0 | capture (mitmproxy 抓包) + prism (web 配置) |
| v0.4 | capture filter 从 CSV 升级到 YAML 策略文件 + profile + include |
| v0.5.2 | capture 锁从 msvcrt 改为哨兵文件，Windows 可多读 |
| v0.5.5 | prism dev 模式 Cache-Control 修复 |
| v0.5.8 | new session draft 默认值 (`name="template"`) |
| v0.6 | + **prism-cli** (10 子命令: convert/inspect/validate/to-steps/explain/meta/user/resource/config/start) |
