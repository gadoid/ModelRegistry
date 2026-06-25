# `gimbal capture` — 流量捕获

> **目的**：把浏览器/客户端通过本地代理发出的 HTTP 请求/响应原样追加写到
> `$GIMBAL_HOME/captures/active/{sid}.ndjson`。
>
> **v0.4+**：支持 YAML 策略文件 + profile + include 复用，替代旧版 CSV 字符串。
>
> **v0.5.2+**：使用哨兵文件 `{sid}.lock`（O_CREAT|O_EXCL）实现跨进程锁，
> 避免 Windows mandatory lock 让 prism 端无法读取。

---

## 目录

1. [架构与目录布局](#1-架构与目录布局)
2. [快速开始](#2-快速开始)
3. [子命令一览](#3-子命令一览)
   - [`start`](#31-start启动抓包)
   - [`list`](#32-list列出当前会话)
   - [`show`](#33-show查看事件)
   - [`archive`](#34-archive手动归档)
4. [筛选策略 (YAML)](#4-筛选策略-yaml)
5. [NDJSON 输出格式](#5-ndjson-输出格式)
6. [退出码约定](#6-退出码约定)
7. [常见问题](#7-常见问题)

---

## 1. 架构与目录布局

### 1.1 `GIMBAL_HOME` 解析顺序

```
1. --home 参数
2. $GIMBAL_HOME 环境变量
3. ~/.gimbal  (默认)
```

```bash
# 显式指定
gimbal capture start -s my-sid --home /tmp/gimbal-test

# 通过环境变量
export GIMBAL_HOME=/var/lib/gimbal
gimbal capture start -s prod-2026
```

### 1.2 目录结构

```
$GIMBAL_HOME/
└── captures/
    ├── active/                          # 当前正在写入的 session
    │   ├── my-sid.ndjson
    │   └── my-sid.lock                  # 哨兵文件 (v0.5.2+)
    └── archive/                         # Ctrl+C / 手动归档后落地
        └── 2026-06-25/
            ├── my-sid-1719283721.ndjson
            └── checkout-1719284500.ndjson
```

### 1.3 数据流

```
浏览器
  │ (代理指向 127.0.0.1:8080)
  ▼
mitmdump + CaptureAddon  (Python 子进程)
  │ 按 CompiledMatcher 过滤
  │ 逐条序列化 → CaptureEvent
  ▼
FileBus ──追加──▶ active/{sid}.ndjson
                 (无锁, 允许多读)

prism 端：
  CaptureReader.read()  ◀── 读历史
  CaptureWatcher        ◀── 0.2s 轮询增量
  /api/captures/stream  ◀── SSE 推送给浏览器
```

---

## 2. 快速开始

```bash
# 1. 安装依赖
pip install mitmproxy

# 2. 启动抓包 (默认端口 8080, 默认 filter /api/)
gimbal capture start -s my-sid

# 3. 浏览器/客户端配置代理
#    HTTP 代理: 127.0.0.1:8080
#    信任 CA:   访问 http://mitm.it 下载安装 mitmproxy CA 证书

# 4. 业务操作 (登录、浏览、提交订单...)

# 5. Ctrl+C 停止 → 自动归档到 archive/2026-06-25/my-sid-XXX.ndjson
```

**30 秒验证**：

```bash
# A 终端
gimbal capture start -s smoke

# B 终端
curl -x http://127.0.0.1:8080 https://httpbin.org/get?x=1
curl -x http://127.0.0.1:8080 -X POST https://httpbin.org/post \
     -H "Content-Type: application/json" \
     -d '{"hello":"world"}'

# A 终端看到:
# [capture] #1 GET /get -> 200
# [capture] #2 POST /post -> 200
# ^C
# [capture] archived → /home/user/.gimbal/captures/archive/2026-06-25/smoke-XXX.ndjson
```

---

## 3. 子命令一览

```
gimbal capture
├── start      启动 mitmproxy 抓包
├── list       列出 active 下所有 session
├── show       查看某 session 的事件 (默认最近 50 条)
└── archive    手动归档一个 session
```

---

### 3.1 `start` — 启动抓包

**用法**：

```bash
gimbal capture start --session <SID> [OPTIONS]
```

**参数**：

| 参数 | 别名 | 默认值 | 说明 |
|---|---|---|---|
| `--session` | `-s` | **必填** | 会话 ID，作为 NDJSON 文件名 |
| `--port` | `-p` | `8080` | mitmproxy 监听端口 |
| `--filter` | `-f` | `/api/` | CSV path 前缀（追加到 YAML 规则之后） |
| `--home` | | `$GIMBAL_HOME` / `~/.gimbal` | GIMBAL_HOME 路径 |
| `--mitmdump` | | `mitmdump` | mitmdump 可执行文件路径 |
| `--filter-file` | | 自动查找 | YAML 筛选配置文件 |
| `--filter-profile` | | 默认 profile | 要使用的 profile 名（多 profile 时必填） |
| `--filter-mode` | | `include` | CLI `--filter` 追加规则的默认 mode (`include` / `exclude`) |
| `--strict-files-only` | | `False` | 关闭自动文件查找，只用 `--filter-file` |

**示例**：

```bash
# 基础用法
gimbal capture start -s my-sid

# 指定端口 + filter
gimbal capture start -s checkout -p 9090 -f /api/order,/api/user

# 加载 YAML 策略文件
gimbal capture start -s e2e --filter-file ./filters.yaml --filter-profile regression

# 只用 YAML，不允许自动 fallback
gimbal capture start -s ci --filter-file ./filters.yaml --strict-files-only

# 黑名单模式 (录全部，排除 /api/static, /api/health)
gimbal capture start -s prod \
    --filter-mode exclude \
    --filter /api/static,/api/health
```

**启动输出**：

```
[capture] filter rules: 5 (mode=include)
[capture] session=my-sid  port=8080  filter-file=None  profile=None
[capture] out=/home/user/.gimbal/captures/active/my-sid.ndjson
[capture] 浏览器代理指向 127.0.0.1:8080, 信任 mitmproxy CA (http://mitm.it)
[capture] #1 GET /api/user/profile -> 200
[capture] #2 POST /api/order/submit -> 201
...
^C
[capture] stopping...
[capture] archived → /home/user/.gimbal/captures/archive/2026-06-25/my-sid-1719283721.ndjson
```

---

### 3.2 `list` — 列出当前会话

```bash
gimbal capture list [--home <PATH>]
```

**示例**：

```bash
$ gimbal capture list
my-sid                          12345 bytes  2026-06-25 14:23:01
checkout-flow                    8723 bytes  2026-06-25 14:35:42
# (无 active session)   ← 如果没有正在抓的 session
```

---

### 3.3 `show` — 查看事件

```bash
gimbal capture show <SID> [--home <PATH>] [--limit <N>]
```

| 参数 | 别名 | 默认值 | 说明 |
|---|---|---|---|
| `SID` | | **必填** | 会话 ID |
| `--limit` | `-n` | `50` | 显示最近 N 条 |

**示例**：

```bash
# 默认显示最近 50 条
gimbal capture show my-sid

# 限制 10 条
gimbal capture show my-sid -n 10
```

**输出**：

```
GET    api.example.com/user/profile          200
POST   api.example.com/order/submit          201
GET    api.example.com/order/12345           200
```

---

### 3.4 `archive` — 手动归档

```bash
gimbal capture archive <SID> [--home <PATH>]
```

把 `active/{sid}.ndjson` 移到 `archive/{YYYY-MM-DD}/{sid}-{epoch}.ndjson`。

**示例**：

```bash
# 归档 my-sid
gimbal capture archive my-sid
# 已归档 → /home/user/.gimbal/captures/archive/2026-06-25/my-sid-1719283721.ndjson

# 如果 session 不存在
$ gimbal capture archive non-existent
session 不存在: non-existent   (退出码 1)
```

---

## 4. 筛选策略 (YAML)

> v0.4+ 新增。旧的 `--filter CSV` 行为完全保留，但推荐使用 YAML 策略文件。

### 4.1 文件查找顺序

显式 `--filter-file` 优先；否则按以下顺序找第一个存在的文件：

```
1. $GIMBAL_FILTERS                       (环境变量)
2. <CWD>/.gimbal/filters.yaml
3. <CWD>/filters.yaml
4. ~/.gimbal/filters.yaml
```

`--strict-files-only` 开启后，找不到文件就报错（不 fallback 到 CSV）。

### 4.2 YAML 格式

```yaml
# filters.yaml
mode: include                    # 顶层 mode: include (白名单) / exclude (黑名单)
default_profile: regression      # 不指定 --filter-profile 时使用

includes:                        # 跨文件复用 (相对路径, 以本文件目录为基准)
  - shared-filters.yaml

profiles:
  smoke:                         # profile 名 (在 --filter-profile 里引用)
    description: "冒烟测试核心链路"
    rules:
      - path: /api/user/login
      - path: /api/order/list
      - path: /api/order/submit

  regression:                    # 另一个 profile
    description: "回归测试全集"
    rules:
      - mode: include
        path_glob: "/api/*"      # fnmatch 风格
        methods: [GET, POST]      # 仅限这些方法
      - mode: exclude             # 排除静态资源
        path: /api/static
      - host: api.example.com     # 限定 host
        path_regex: "^/api/v2/"   # 正则
      - host_glob: "*.internal.*"
        path: /api/internal
```

### 4.3 匹配语义

**单条 rule**（AND 语义）：

- `host` / `host_glob` / `host_regex` 互斥三选一
- `path` / `path_glob` / `path_regex` 互斥三选一
- `methods` 可选，若指定则 method 必须在其中
- 所有填写的字段都必须满足

**多条 rule**（OR 语义）：

- 任一 rule 命中 → 由该 rule 的 `mode` 决定（`include=True` / `exclude=False`）

**无 rule 命中** → 由 `default_mode` 决定：

- 文件 `mode: include` → `default_mode: exclude`（白名单：没在列表就不录）
- 文件 `mode: exclude` → `default_mode: include`（黑名单：没在列表就录）

### 4.4 CLI `--filter` 追加规则

`--filter` 的每条 CSV 元素被追加到所选 profile 的 `rules` 末尾，默认 mode 由 `--filter-mode` 决定：

```bash
# profile 规则 + CSV 追加 (mode=include)
gimbal capture start -s my-sid \
    --filter-file ./filters.yaml \
    --filter-profile regression \
    --filter /api/order/cancel  # 追加这条, mode=include
```

### 4.5 include 跨文件组合

```yaml
# base.yaml
mode: include
default_profile: base
profiles:
  base:
    rules:
      - path: /api/common

# regression.yaml
mode: include
default_profile: regression
includes:
  - base.yaml
profiles:
  regression:
    rules:
      - path: /api/regression-only
```

加载 `regression.yaml` 后，等价于：

```yaml
profiles:
  base:
    rules:
      - path: /api/common
  regression:
    rules:
      - path: /api/regression-only
```

**环检测**：A include B, B include A → `IncludeCycleError`，父进程退出码 5。

### 4.6 调试

使用 `CompiledMatcher.match_with_reason()` 看每条 event 命中了哪条 rule：

```python
from gimbal.capture.loader import build_matcher
from gimbal.capture.strategy import FilterMode

m = build_matcher(
    filter_file=Path("./filters.yaml"),
    profile="regression",
    cli_csv=None,
    cli_mode=FilterMode.INCLUDE,
)
print(m.match_with_reason({"method": "GET", "host": "api.x.com", "path": "/api/user"}))
# (True, 'rule #1 mode=include path_prefix=/api/user')
```

---

## 5. NDJSON 输出格式

每行一个 JSON 对象，**字节级兼容** `gimbal.prism.CaptureEvent` 解析器：

```json
{
  "ts": 1719283721.234,
  "method": "POST",
  "scheme": "https",
  "host": "api.example.com",
  "port": 443,
  "path": "/api/order/submit",
  "query": {"trace_id": "abc123"},
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer eyJhbGc...",
    "User-Agent": "Mozilla/5.0 ..."
  },
  "body": "{\"product_id\":123,\"qty\":2}",
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json",
      "Set-Cookie": "session=xyz; HttpOnly"
    },
    "body": "{\"order_id\":98765,\"status\":\"created\"}"
  }
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | float | epoch 秒 |
| `method` | str | 大写 (GET/POST/...) |
| `scheme` | str | `http` / `https` |
| `host` | str | 不含端口 |
| `port` | int | |
| `path` | str | 已去 query string |
| `query` | object | URL query 解析为 dict |
| `headers` | object | request headers |
| `body` | str | request body（binary 回退到空串） |
| `response.status` | int | HTTP 状态码 |
| `response.headers` | object | response headers |
| `response.body` | str | response body（binary 回退到空串） |

---

## 6. 退出码约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 用户取消 (残留确认 / 未知 section) |
| `2` | 文件不存在 (input/config/scenario) |
| `3` | NDJSON / JSON 解析错误 |
| `4` | session 已被另一个 capture 占用 (`SessionLockedError`) |
| `5` | 筛选配置错误 (YAML 错 / 正则错 / 循环 include / 空规则) |
| `6` | 字段未找到 |

---

## 7. 常见问题

### Q1: Windows 上 mitmdump 启动后 prism 端读不到文件

**原因**：v0.5.2 之前用 `msvcrt.locking` 锁 NDJSON 文件，Windows 是 mandatory lock。

**解决**：v0.5.2+ 已改为哨兵文件锁，NDJSON 文件本身无锁，可多读。升级到最新版本。

### Q2: session 启动时提示 "session 已被占用"

```bash
$ gimbal capture start -s my-sid
[capture] session 'my-sid' 已有残留数据 12345 bytes,如何处理? [y/N]:
```

选 `y` → 截断 NDJSON 重新开始。
选 `N` → 退出（保留旧数据）。
或先 `gimbal capture archive my-sid` 归档再重试。

### Q3: `--filter` 多个前缀用逗号还是分号？

逗号。`/api/order,/api/user,/api/product`。

### Q4: 怎么只录 POST 请求？

```yaml
# filters.yaml
mode: include
default_profile: write-ops
profiles:
  write-ops:
    rules:
      - methods: [POST, PUT, DELETE, PATCH]
        path_glob: "/api/*"
```

### Q5: 怎么排除二进制请求（如图片上传）？

v0 capture 层不做 body 内容过滤（只按 host/path/method 过滤）。
二进制 body 会被截断为 `""`（`flow.request.get_text()` 失败兜底）。
如需排除，按 path 过滤：

```yaml
rules:
  - mode: exclude
    path_glob: "/upload/*"
  - mode: exclude
    path_regex: "\\.(png|jpg|jpeg|gif|webp|mp4|zip)$"
```

### Q6: capture 和 prism 端能同时跑吗？

可以。capture 进程独占 `active/{sid}.lock` 哨兵，NDJSON 文件本身无锁。
prism 端的 `CaptureReader` / `CaptureWatcher` / SSE / WebSocket 全部只读，跨平台一致。

### Q7: 实时性？

- 写入：mitmproxy 收到 response 后立刻追加（line-buffered）
- 读取：prism 端 `CaptureWatcher` 0.2s 轮询一次 `mtime/size`，SSE / WS 推送延迟 ≤ 0.2s
