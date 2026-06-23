# gimbal 平台 v0.5.3 综合设计文档

> **日期**：2026-06-22
> **作者**：gimbal team
> **范围**：整个 gimbal 平台（capture + prism + schema + 前端）
> **状态**：实施完成（202 passed / 4 skipped）
> **取代**：`2026-06-21-capture-filter-strategy-design.md`（v0.4 设计稿，已归档）

---

## 0. 文档定位

本文档反映**当前 v0.5.3 代码状态**的完整功能与设计决策。版本演进历程见 `CHANGELOG.md`（v0.1 → v0.5.3 共 6 个版本），历史设计决策归档见 `gimbal-design/` 目录（7 份 v0.x 设计稿）。

---

## 1. 项目定位

**gimbal**：把"浏览器真实流量"转成"可复用的 GIMBAL Scenario"。

```
浏览器 → 抓包代理 (mitmproxy :8080) → NDJSON 落盘 → 配置器 (FastAPI :8765) → 导出 Scenario YAML
              gimbal capture 子进程           文件系统         gimbal prism 子进程
```

**核心价值**：
1. **真实流量**（不是手写 mock）→ 测试贴近生产
2. **可视化编辑**（4-Tab 卡片式 UI）→ 非工程师也能调测
3. **版本化配置**（YAML 策略文件）→ 团队可复用、可分层

---

## 2. 架构总览

### 2.1 双进程模型

| 进程 | 角色 | 命令 | 默认端口 |
|---|---|---|---|
| **capture** | 流量录制 (mitmproxy 代理) | `gimbal capture start --session <sid>` | 8080 |
| **prism** | Web 配置器 (FastAPI) | `gimbal prism start` | 8765 |

**进程级独立**：
- ✅ 启动顺序无关（capture 没起，prism 也能起）
- ✅ 故障隔离（prism OOM 不丢 capture 数据）
- ✅ 资源占用隔离（capture 走 mitmproxy，prism 走 uvicorn）
- ❌ 无反向依赖（`gimbal/capture/*` 0 处 import `gimbal/prism`）
- ❌ 无 in-process API（**文件系统是唯一契约**）

### 2.2 文件系统契约

```
$GIMBAL_HOME/                        (默认 ~/.gimbal)
├── captures/
│   ├── active/
│   │   ├── {session_id}.ndjson        ← capture 写, prism 读
│   │   ├── {session_id}.lock         ← 哨兵文件 (O_CREAT|O_EXCL)
│   │   └── .tmp_capture_addon.py      ← capture 启动时生成, 退出时删
│   └── archive/
│       └── {YYYY-MM-DD}/
│           └── {sid}-{epoch}.ndjson  ← capture Ctrl+C 后归档
├── scenarios/
│   └── {scenario_id}.yaml             ← prism export
└── {prism-export}/                    ← prism export 临时目录
```

### 2.3 端到端数据流

```
[浏览器]
  │ HTTPS 请求
  ▼
[gimbal capture 进程]
  │ mitmproxy addon
  │   response() → CompiledMatcher.match(event_dict)
  │   命中 → CaptureEvent → FileBus.write() (append + flush)
  ▼
$HOME/captures/active/{sid}.ndjson   ← 落盘
  │ PollingObserver (0.5s 轮询)
  ▼
[gimbal prism 进程]
  │ WS /ws/captures?sid=...
  │   hello 帧 (历史事件灌入)
  │   capture 帧 (实时推送)
  ▼
[浏览器 prism UI]
  │ app.js onmessage
  │   state.captures.push()
  │   updateCapturesBadge()
  │   renderCaptures()     ← Step tab 上方表格
  │   toast()              ← 右下角短闪
  ▼
[用户在 Step tab 手动编辑 + 点"导入"按钮]
  │ 调 POST /api/draft/{sid} (含完整 step 自定义)
  ▼
$HOME 内存 sessions 字典 (按 sid 隔离)
  │ 用户点"导出 YAML" → POST /api/draft/{sid}/export
  │   build_scenario()  → Scenario YAML
  ▼
$GIMBAL_HOME/scenarios/{scenario_id}.yaml  ← 输出
```

---

## 3. 代码清单

| 模块 | 文件 | 行数 | 职责 |
|---|---|---|---|
| **gimbal 包** | `__init__.py` | 10 | 顶层包标识 |
| **schema/** | 13 个 Pydantic 文件 + __init__.py | 895 | GIMBAL Scenario 输出格式 (SSOT) |
| **capture/** | 9 个文件 | 1179 | 流量捕获 (mitmproxy 进程) |
| **prism/** | 11 个文件 | 1939 | Web 配置器 (FastAPI 进程) |
| **前端** | 3 个文件 | 2863 | index.html + style.css + app.js |
| **测试** | 29 个文件 | — | 202 passed + 4 skipped |

### 3.1 `gimbal/capture/` (流量捕获)

| 文件 | 行 | 职责 |
|---|---|---|
| `__init__.py` | 7 | 标记为包 |
| `archive.py` | 50 | 归档逻辑 (active → archive/YYYY-MM-DD/) |
| `bus.py` | 113 | **FileBus NDJSON 总线 + 哨兵文件锁** |
| `cli.py` | 258 | typer start/list/show/archive 4 子命令 |
| `filter.py` | 28 | **PathFilter 兼容层** (v0 CSV 旧 API) |
| `loader.py` | 345 | **YAML 策略加载** + include 递归 + profile + 编译 |
| `proxy.py` | 99 | **mitmproxy addon** + CompiledMatcher.match |
| `recorder.py` | 73 | CaptureEvent dataclass |
| `strategy.py` | 206 | **Pydantic 数据类** + CompiledMatcher |

### 3.2 `gimbal/prism/` (Web 配置器)

| 文件 | 行 | 职责 |
|---|---|---|
| `__init__.py` | 7 | 标记为包 |
| `server.py` | 506 | **FastAPI 应用** (lifespan + 16 端点) |
| `builder.py` | 396 | ScenarioDraft → Scenario (build_scenario) |
| `state.py` | 219 | **CaptureReader / CaptureWatcher (PollingObserver)** + SessionStore |
| `cli.py` | 47 | typer start 子命令 |
| `convert.py` | 77 | Model 转换工具 |
| `doc2model.py` | 434 | docx → Model (离线工具) |
| `render/__init__.py` | 12 | 渲染层入口 |
| `render/ui_spec.py` | 113 | Pydantic → UI spec JSON |
| `render/registry_spec.py` | 74 | ModelRegistry → UI spec |
| `render/walk_model.py` | 54 | 字段 walker |

### 3.3 `gimbal/schema/` (Pydantic SSOT)

| 文件 | 行 | 职责 |
|---|---|---|
| `scenario.py` | 176 | `Scenario` / `Meta` / `Config` |
| `step.py` | 55 | `Step` / `Api` / `Request` |
| `strategy.py` | 108 | `Assertion` / `Extract` / `Assign` + 操作符 |
| `resource.py` | 85 | `Resource` 联合类型 (Mock/MockRef/File/FileRef) |
| `auth.py` | 109 | `AuthSession` |
| `timepolicy.py` | 54 | `TimePolicy` (record / timeout) |
| `retrypolicy.py` | 36 | `RetryPolicy` |
| `setup.py` | 23 | `Setup` / `SetupRef` |
| `teardown.py` | 23 | `Teardown` / `TeardownRef` |
| `request.py` | 37 | `Request` (body / params) |
| `ref.py` | 29 | `RefBase` |
| `api.py` | 41 | `Api` |
| `states.py` | 17 | 状态枚举 |

---

## 4. 核心模块详解

### 4.1 `gimbal/capture/bus.py` — FileBus NDJSON 总线

**职责**：把 `CaptureEvent` 追加写入 `$HOME/captures/active/{sid}.ndjson`，同时保证同 session 不会被两个 capture 进程同时写。

**关键类**：
- `SessionLockedError`：哨兵文件存在 → 另一 capture 在跑
- `FileBus`：每次 `__init__` 立即抢哨兵 → `write()` 追加 → `close()` 释放

**哨兵文件机制**（v0.5.2 引入）：
```
{sid}.lock = O_CREAT | O_EXCL | O_RDWR 创建 (0o644)
成功   → 你是第一个, 可写
失败   → 已有另一 capture 在跑, 抛 SessionLockedError
close() → unlink + close fd
```

**为什么不锁 NDJSON 本身**：Windows 的 `msvcrt.locking` 是 **mandatory lock**，锁住后其他进程**任何**读都 `PermissionError`。改用哨兵文件，NDJSON 完全无锁，prism 端可自由读。

### 4.2 `gimbal/capture/strategy.py` — 筛选数据模型

**职责**：用 Pydantic 定义 Rule / Profile / StrategyFile 三个层次，编译成高效的 `CompiledMatcher`。

**核心类型**：
```python
class FilterMode(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"

class Rule(BaseModel):
    """单条匹配规则: 内部 AND, 多 rule 间 OR"""
    mode: Optional[FilterMode] = None   # 缺省继承顶层
    host / host_glob / host_regex       # 三选一
    path / path_glob / path_regex       # 三选一
    methods: Optional[list[str]] = None  # 自动大写

class Profile(BaseModel):
    description: Optional[str]
    rules: list[Rule]

class StrategyFile(BaseModel):
    mode: FilterMode = INCLUDE
    default_profile: Optional[str]
    includes: list[Path]
    profiles: dict[str, Profile]

@dataclass(frozen=True)
class CompiledRule:
    mode: FilterMode            # 编译时已解析
    host: Optional[re.Pattern]
    path_prefix: Optional[str]
    path_re: Optional[re.Pattern]
    methods: Optional[frozenset[str]]

class CompiledMatcher:
    """含 default_mode (与 sf.mode 相反) + match(event_dict) → bool"""
    rules: list[CompiledRule]
    default_mode: FilterMode

    def match(self, event: dict) -> bool:
        for rule in self.rules:
            if self._match_one(rule, event):
                return rule.mode == FilterMode.INCLUDE
        return self.default_mode == FilterMode.INCLUDE  # 无命中走默认方向
```

**校验**：空 rule 拒绝 / host 三选一互斥 / path 三选一互斥 / methods 自动大写 / extra 字段拒绝。

### 4.3 `gimbal/capture/loader.py` — 筛选策略加载

**职责**：CLI 参数 → `CompiledMatcher` 端到端入口。

**关键函数**：
- `discover_filter_file(explicit, search_paths, strict)`：显式 > 自动搜索路径
- `_load_one_yaml(path)`：YAML 解析 + Pydantic 校验
- `resolve_includes(main_path, visited)`：递归 + 环检测（`IncludeCycleError`）
- `select_profile(sf, name)`：显式 > default_profile > 单 profile 自动
- `append_cli_rules(profile, csv, cli_mode)`：把 `--filter /a,/b` 转 Rule 追加
- `compile_matcher(sf, profile)`：正则预编译 + 派生 default_mode
- `build_matcher(...)`：端到端入口 (4 条分支：找文件 / fallback / 纯 CSV / sentinel)

**异常体系**：`FilterConfigError` (parent) → `FilterFileNotFound` / `IncludeCycleError` / `ProfileNotFound` / `RuleCompileError` / `EmptyRulesError`。父进程捕到 → 退出码 5 + 红字。

### 4.4 `gimbal/capture/proxy.py` — mitmproxy addon

**职责**：mitmproxy `-s` 加载，过滤 + 落 FileBus。

```python
class CaptureAddon:
    def __init__(self, bus: FileBus, matcher: CompiledMatcher):
        self.bus, self.matcher = bus, matcher

    def response(self, flow):
        path = flow.request.path.split("?")[0]
        event = {"method": ..., "host": ..., "path": ...}
        if not self.matcher.match(event):
            return
        # 构造 CaptureEvent, bus.write() 落 NDJSON
```

**与 v0 PathFilter 的差异**：v0 用 `PathFilter`（仅 path 前缀），v0.4+ 用 `CompiledMatcher`（host/method/glob/regex 联合）。

### 4.5 `gimbal/capture/cli.py` — 4 子命令

| 子命令 | 作用 |
|---|---|
| `start --session <sid>` | 启动 mitmproxy 抓包 (Ctrl+C 归档) |
| `list` | 列出 active 下的 session |
| `show <sid> --limit N` | 查看某 session 最近 N 条事件 |
| `archive <sid>` | 手动归档 |

**start 的关键流程**（v0.5.2.1 修复后）：
1. `build_matcher(...)` 父进程预校验（YAML/正则/include 错 → 退出码 5）
2. **临时 probe**：`FileBus(home, session); .close()` 即建即关（**父进程不持 lock**）
3. 残留检测 + 用户确认（y/N）→ `write_text("")` 清空
4. 渲染 `.tmp_capture_addon.py` addon 脚本
5. `subprocess.Popen([mitmdump, ...])` 启动子进程
6. mitmdump → addon 脚本 → `FileBus(home, session)` 抢 lock（addon 是唯一持有者）
7. Ctrl+C → addon `bus.close()` 释放 lock + 父进程归档

### 4.6 `gimbal/prism/server.py` — FastAPI 应用

**16 端点**（9 GET + 4 POST + 1 PUT + 1 DELETE + 1 WebSocket）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 健康检查 + 计数 |
| GET | `/api/schema/ui-spec` | Pydantic → UI spec |
| GET | `/api/schema/dot-paths` | 合法字段路径白名单 |
| GET | `/api/registry/ui-spec` | ModelRegistry → UI spec |
| GET | `/api/captures?sid=` | 列出会话捕获 |
| DELETE | `/api/captures?sid=` | 清空会话捕获 |
| POST | `/api/captures/inject?sid=` | 注入单条事件 |
| POST | `/api/captures/import-from-path?sid=` | 从 NDJSON 路径导入 |
| GET | `/api/captures/stream?sid=` | **SSE 实时流**（保留备用） |
| **WS** | **`/ws/captures?sid=`** | **WebSocket 实时推送**（v0.5 主力） |
| GET | `/api/draft/{sid}` | 读草稿 |
| PUT | `/api/draft/{sid}` | 写草稿（完整 step 自定义） |
| POST | `/api/draft/{sid}/yaml` | 预览 YAML |
| POST | `/api/draft/{sid}/export` | 导出 YAML |
| GET | `/` | 主页 HTML |
| GET | `/configure?session=...` | 带 session 注入的 HTML |

**WebSocket 协议**：
```
客户端:  ws://.../ws/captures?sid=<sid>
服务端:  连上后立刻发 {"type":"hello","count":N,"events":[...]}  (历史灌入)
         每条新事件发 {"type":"capture","data":<event_dict>}
```

### 4.7 `gimbal/prism/state.py` — CaptureWatcher（PollingObserver）

**v0.5.2 关键改造**：
```python
# 旧: from watchdog.observers import Observer
#     Observer() → Windows 下 21s 延迟
# 新:
from watchdog.observers.polling import PollingObserver
Observer = lambda: PollingObserver(timeout=0.5)  # 跨平台 0.5s 轮询
```

**捕获事件** → 写队列 → WS 协程读取 → 推送给前端。

### 4.8 `gimbal/prism/builder.py` — `build_scenario`

**职责**：把内存中的 `ScenarioDraft` (含 step 自定义) 序列化成 `Scenario` Pydantic 对象，再 `.model_dump(mode="json")` 出 YAML。

**Step 消费**：
- `StepDraft.capture` 原始 capture 数据
- `StepDraft.api_override` 覆盖 method/path/service
- `StepDraft.req_override` 替换 request.params/body
- `StepDraft.assertions/extracts/assigns` 生成 strategy 列表
- `StepDraft.key_hint` 影响 step.key（`{idx}-{slug}` 格式）
- `StepDraft.enabled` 过滤禁用 step

### 4.9 `gimbal/prism/static/app.js` — 前端 v1.0.0

**1544 行**，结构：

| 段 | 行号 | 内容 |
|---|---|---|
| 全局 state | 12-30 | 单一 `state` 对象（meta/services/users/tags/resources/steps/captures） |
| 工具 | 47-130 | escape / debounce / toast / confirmModal |
| session 检测 | 135-143 | URL `?session=` 或 `<meta name="prism-session">` |
| 序列化 | 191-209 | setFieldValue / getFieldValue |
| 渲染 | 211-820 | renderMeta/Tags/Services/Users/Resources/Steps/Captures |
| 历史 | 147-185 | undo/redo + snapshot |
| 网络 | 1008-1280 | _pullCaptures / import / WS / saveDraft |
| 启动 | 1469+ | init() |

**Step tab 上方**（v0.5.3 新增）`<details class="captures-panel">` 实时显示 4 列表格（METHOD / PATH / STATUS / 耗时）。

### 4.10 `gimbal/schema/scenario.py` — 输出格式 SSOT

`Scenario` 是最终输出 YAML 的 Pydantic 模型。所有其它模块（builder / render / server）都消费这个 schema。`model_config = ConfigDict(extra="forbid")` 防止意外字段泄漏到输出。

---

## 5. 数据模型

### 5.1 端到端对象生命周期

```
CaptureEvent (recorder.py)
   ↓ to_dict
NDJSON 行 (json.dumps)
   ↓ 落盘
FileBus 写
   ↓
WebSocket 帧
   ↓
state.captures[i] (app.js)
   ↓ 用户编辑
state.steps[i] (含 api_override / assertions / ...)
   ↓ PUT /api/draft
DraftIn (server.py)
   ↓ _draft_from_in
ScenarioDraft (builder.py)
   ↓ build_scenario
Scenario (schema/scenario.py)
   ↓ model_dump
YAML 输出
```

### 5.2 Wire 格式 (DraftIn)

```python
class DraftIn(BaseModel):
    scenario_id, name, description, module, priority,
    author, owner, tags, version, expire, requirement_ref
    services: dict[str, str]
    users: list[UserIn]  # {key, url, username, password, expires_in, token_type, token, confirm_password}
    time_policy_kind, time_policy_seconds
    retry_enabled, retry_max_attempts, retry_backoff_seconds, retry_on
    setup_refs, teardown_refs
    resources: list[dict]
    # v0.5.1 新增: 完整 step 自定义 (新字段, 优先使用)
    steps: list[dict]
    # 旧字段: fallback, 仅在 steps 为空时走 captures 文件
    step_ids: list[str]
```

### 5.3 YAML 策略文件 (StrategyFile)

```yaml
mode: include | exclude         # 顶层默认方向
default_profile: string        # 缺省 profile
includes: [Path, ...]           # 跨文件组合 profiles
profiles:
  <name>:
    description: string?
    rules:
      - mode?: include|exclude  # 缺省继承顶层
        host|host_glob|host_regex: string  # 三选一
        path|path_glob|path_regex: string  # 三选一
        methods: [string, ...]   # 自动大写
```

### 5.4 NDJSON 行 (CaptureEvent)

```json
{
  "ts": 1234567890.123,
  "method": "GET",
  "scheme": "https",
  "host": "api.example.com",
  "port": 443,
  "path": "/api/order",
  "query": {"id": "1"},
  "headers": {"authorization": "Bearer ..."},
  "body": "",
  "response_status": 200,
  "response_headers": {"content-type": "application/json"},
  "response_body": "{\"ok\":true}",
  "response_ms": 50
}
```

### 5.5 用户 UI spec (前端消费)

```json
{
  "groups": [
    {"name": "meta", "title": "元信息", "fields": [...]},
    {"name": "config", "title": "配置", "fields": [...]}
  ]
}
```

---

## 6. 端到端关键流程

### 6.1 启动 capture

```
gimbal capture start --session dev-1
  ↓
cli.start_cmd
  ├→ build_matcher(...)               ← filter 校验 (失败 → 退出 5)
  ├→ probe = FileBus(home, dev-1)     ← 抢 dev-1.lock 哨兵
  │   .close()                          ← 立即释放
  ├→ [if dev-1.ndjson 存在] 用户确认 y/N
  │   ├→ y: write_text("") 清空
  │   └→ N: typer.Exit(1)
  ├→ 渲染 .tmp_capture_addon.py
  └→ Popen([mitmdump, ...])
       ↓
       mitmdump 子进程
       ├→ 加载 .tmp_capture_addon.py
       │   ├→ bus = FileBus(home, dev-1)  ← 抢 dev-1.lock (父进程已释放)
       │   ├→ matcher = build_matcher(...)
       │   └→ addons = [CaptureAddon(bus, matcher)]
       └→ Ctrl+C → addon bus.close() → 父进程 archive
```

### 6.2 启动 prism + 接收实时

```
gimbal prism start --port 8765
  ↓
lifespan (server.py:166)
  ├→ app.state.gimbal_home = ...
  ├→ app.state.capture_reader = CaptureReader(home)
  └→ app.state.capture_watcher = CaptureWatcher(home)
  ↓
uvicorn 启动
  ↓
浏览器开 http://127.0.0.1:8765/?session=dev-1
  ↓
app.js init()
  ├→ detectSession() → state.sessionId = "dev-1"
  ├→ bindMeta/Tags/etc.
  ├→ loadDraft() → GET /api/draft/dev-1
  └→ connectWs()
       └→ new WebSocket("ws://.../ws/captures?sid=dev-1")
            ↓
            WS 端点 (server.py:358)
            ├→ reader.read(dev-1)  ← 历史
            ├→ send_json({"type":"hello","events":[...]})
            └→ watcher.watch(dev-1, on_event)
                 ├→ queue = asyncio.Queue()
                 ├→ on_event = lambda ev: queue.put_nowait(ev)
                 └→ while True: ev = await queue.get(); send_json({"type":"capture","data":ev})
```

### 6.3 浏览器操作触发 capture → WS 推送

```
浏览器发 GET https://api.example.com/api/order
  ↓
mitmproxy (capture 子进程)
  ├→ CaptureAddon.response(flow)
  │   ├→ event = {method, host, path}
  │   ├→ matcher.match(event) → True (假设 /api 命中)
  │   └→ bus.write(CaptureEvent(...))
  │        └→ NDJSON append + flush
  ↓
0.5s 内 (PollingObserver)
prism CaptureWatcher 监听到文件 modify
  ├→ _FileHandler.on_modified
  │   ├→ seek(_last_pos)
  │   ├→ read 新行 → on_event(event_dict)
  │   └→ _last_pos = tell()
  └→ on_event → queue.put_nowait(ev)
       ↓
       WS 协程 await queue.get()
       └→ send_json({"type":"capture","data":ev})
            ↓
            浏览器 app.js onmessage
            ├→ state.captures.push(c)
            ├→ updateCapturesBadge()   ← 顶栏数字
            ├→ renderCaptures()       ← Step tab 表格
            └→ toast(...)             ← 右下角 1.8s 短闪
```

### 6.4 用户编辑 step + 导出 YAML

```
用户在 Step tab 编辑 step.method = "PUT" (api_override)
  ↓
scheduleSave() (debounce 800ms)
  ↓
_save() → fetch PUT /api/draft/dev-1
  ↓
DraftIn.model_validate({steps: [...]})   ← v0.5.1 新增字段
  ↓
_draft_from_in
  ├→ payload.steps 非空 → 用它构造 StepDraft
  │   (含 api_override / req_override / assertions / extracts / assigns / key_hint)
  └→ scenarios[dev-1] = {"draft": payload.model_dump(), ...}
       ↓
用户点"导出 YAML"
  ↓
POST /api/draft/dev-1/export
  ├→ _draft_from_in(payload)
  ├→ build_scenario(scenario_draft)
  │   ├→ 每个 step:
  │   │   ├→ method/path 用 api_override (缺省走 capture)
  │   │   ├→ request 用 req_override (缺省走 capture)
  │   │   ├→ assertions/extracts/assigns → strategy 列表
  │   │   └→ key = f"{idx}-{slug}"  (key_hint 优先)
  │   └→ 序列化
  └→ yaml.safe_dump(..., sort_keys=False) → 写文件
       ↓
       $GIMBAL_HOME/scenarios/{scenario_id}.yaml
```

---

## 7. 关键设计决策

### 7.1 进程级独立 + 文件系统契约（spec §1.1）

| 候选方案 | 选 | 原因 |
|---|---|---|
| 单进程 (capture + prism) | ❌ | OOM 风险 + 资源争抢 |
| 跨进程 API (HTTP / RPC) | ❌ | 部署复杂, 单向依赖陷阱 |
| 消息队列 (Redis / MQ) | ❌ | 引入新依赖 |
| **文件系统 NDJSON** | ✅ | 零依赖, 多读单写, 人类可读 |

### 7.2 哨兵文件 vs msvcrt.locking (v0.5.2)

| 候选 | 结果 |
|---|---|
| msvcrt.locking 锁 NDJSON | ❌ Windows mandatory lock, 阻塞 prism 读 (PermissionError) |
| fcntl.flock 锁 NDJSON | ⚠️ POSIX 没问题, Windows 不可用 |
| **独立 .lock 哨兵 (O_CREAT\|O_EXCL)** | ✅ 跨平台, NDJSON 完全无锁, 多读安全 |

### 7.3 PollingObserver vs Observer (v0.5.2)

| 候选 | 结果 |
|---|---|
| watchdog.observers.Observer (ReadDirectoryChangesW) | ❌ Windows + uvicorn 事件循环下 21s 延迟, 事件合并 |
| **watchdog.observers.polling.PollingObserver(timeout=0.5)** | ✅ 跨平台, 0.5-1s 延迟可控 |

### 7.4 Step 自定义持久化 (v0.5.1)

| 候选 | 结果 |
|---|---|
| 仅发 `step_ids: [String(0), String(1), ...]` (基于 captures 索引) | ❌ 拖拽 / 删 step 失效, 用户编辑全丢 |
| **发完整 `steps: [StepDraft...]`** (含 api_override/req_override/...) | ✅ 完整持久化, 拖拽有效, 断言落 YAML |

### 7.5 声明式 vs 硬编码 UI

| 候选 | 结果 |
|---|---|
| `/api/schema/ui-spec` 端点反射 + 前端 7-widget 派发 | v0 老前端, 改 schema 改 UI 失效 |
| **HTML 硬编码字段 (PR1SM 视觉规范)** | v0.5 新前端, 视觉好, 但失去 schema-driven 优势 |

v0.5 选了后者（用户主动要求 PR1SM 视觉），代价是 schema 变更需要同时改 HTML。

### 7.6 父子进程双 build_matcher

- 父进程：先 `build_matcher` 一次，提前发现 YAML/正则/include 错
- mitmdump 子进程：再 `build_matcher` 一次（冗余但保证隔离，mitmdump 子进程不能传对象）

### 7.7 父进程不持 FileBus (v0.5.2.1 修复)

- 父进程用 `probe = FileBus(...); probe.close()` 抢锁后立即释放
- addon 进程才是 FileBus 的唯一持有者
- 修复 v0.5.2 引入的"父进程持锁 + addon 抢锁"必败 bug

---

## 8. 测试与质量

### 8.1 测试统计

- **29 个测试文件**
- **202 passed + 4 skipped**
- 覆盖：capture / prism / schema / frontend / 集成

### 8.2 关键测试文件

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `test_strategy_model.py` | 13 | Rule/Profile/StrategyFile 校验 |
| `test_strategy_compile.py` | 14 | CompiledMatcher 匹配语义 |
| `test_loader_yaml.py` | 8 | YAML 解析 + 校验失败 |
| `test_loader_include.py` | 7 | include 递归 + 环检测 |
| `test_loader_profile.py` | 6 | profile 选择 |
| `test_loader_cli_override.py` | 8 | CLI CSV 追加 |
| `test_filter_compat.py` | 7 | PathFilter 兼容回归 |
| `test_bus_lock_semantics.py` | 8 | 哨兵文件语义 |
| `test_cli_integration.py` | 11 | typer CliRunner 端到端 |
| `test_proxy_with_matcher.py` | 6 | CaptureAddon + CompiledMatcher |
| `test_step_persistence.py` | 16 | Step 自定义 round-trip |
| `test_frontend_v1.py` | 18 | 前端 v1.0.0 锁住关键属性 |
| 其他 (10 个) | ~80 | capture / builder / state / schema 等 |

### 8.3 关键 E2E 验证

- ✅ capture 写 → prism WS 收到 5 个 capture 事件 (延迟 < 1s)
- ✅ 5 个 Method 颜色 + Status 颜色 + 路径 + 耗时 全部正确
- ✅ 用户编辑 step.api.method = "PUT" → 保存 → YAML 含 `method: PUT`
- ✅ 用户加 assertion → 保存 → YAML 含 `strategy.assertion`
- ✅ 多 profile YAML → 显式 `--filter-profile smoke` 选中
- ✅ include 循环 → 退出码 5
- ✅ 坏正则 → 退出码 5
- ✅ 多 session 互不干扰

---

## 9. 已知限制与未来工作

### 9.1 v0.5.3 不做的事（YAGNI）

- ❌ `gimbal run` 执行引擎
- ❌ AI 助手
- ❌ 多 worker uvicorn
- ❌ `config.yaml` 加载
- ❌ header / cookie 黑名单
- ❌ 用户自定义插件 / Strategy 类
- ❌ 远程配置中心
- ❌ 热重载
- ❌ 暗色模式
- ❌ 多语言 i18n
- ❌ 移动端深度优化

### 9.2 TODO

| 优先级 | 项 | 说明 |
|---|---|---|
| P1 | `gimbal run` 执行器 | 跑导出的 Scenario YAML |
| P1 | captures 列表滚动优化 | 200 条上限可调, 或虚拟滚动 |
| P2 | captures 自动合并到 step | 用户选项开关 (避免长 session step 爆炸) |
| P2 | 资源 kind 扩展 | DB 接入 / 变量 等 4 种之外的 |
| P3 | filter-file watch 热重载 | mitmdump 重新 build_matcher |

### 9.3 已知小问题

- **多 capture 同时写同一 session**：哨兵文件阻止了，错误信息友好
- **ndjson 文件残留**：capture 崩溃后下次启动探测提示用户 y/N 清空
- **DI 列只读**：regex 编译在 `build_matcher` 一次，运行期只查 `re.Pattern.search()`

---

## 10. 部署与运行

### 10.1 启动步骤

```bash
# 1. 启动 capture (终端 1)
D:/M/ModelRegistry/.venv/Scripts/gimbal.exe capture start --session dev-1

# 2. 启动 prism (终端 2)
D:/M/ModelRegistry/.venv/Scripts/gimbal.exe prism start --port 8765

# 3. 浏览器
# 代理: 127.0.0.1:8080
# 信任 CA: http://mitm.it
# 配置器: http://127.0.0.1:8765/?session=dev-1
```

### 10.2 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `GIMBAL_HOME` | 数据目录 | `~/.gimbal` |
| `GIMBAL_FILTERS` | filter-file 搜索路径 | 无 |
| `PRISM_WEB_PORT` | prism 端口 (老 API) | 8765 |

### 10.3 目录结构

```
D:/M/ModelRegistry/
├── gimbal/                  # 平台包
│   ├── capture/             # 9 文件
│   ├── prism/               # 10 文件
│   ├── schema/              # 12 文件
│   └── cli/                 # 顶层 CLI
├── ModelRegistry/           # 契约模型仓库
├── tests/                   # 29 文件
├── docs/superpowers/
│   ├── specs/               # 设计文档
│   │   ├── 2026-06-22-current-state-design.md  ← 本文档
│   │   └── archive/         # 旧设计稿归档
│   └── plans/
├── gimbal-design/           # v0.x 设计归档 (7 份)
├── pyproject.toml
└── requirements.txt
```

---

## 11. 文档版本历史

| 版本 | 日期 | 主题 |
|---|---|---|
| v0.1 | 2026-06-18 | 平台首发 (capture + prism 双进程) |
| v0.2 | 2026-06-18 | UI 注解全覆盖 + 前端声明式 |
| v0.3 | 2026-06-18 | 删旧 `prism/` 顶层包 |
| v0.4 | 2026-06-21 | **Capture Filter Strategy** (YAML 筛选) |
| v0.5 | 2026-06-21 | **前端 v1.0.0** (PR1SM 视觉) |
| v0.5.1 | 2026-06-21 | **Step 自定义字段持久化** (P0 修复) |
| v0.5.2 | 2026-06-22 | **capture-prism 数据流通** (Windows 修复) |
| v0.5.3 | 2026-06-22 | **前端 captures 实时列表** |

---

**附录**：
- 端点完整列表见 §4.6
- 配置文件示例见 `docs/superpowers/specs/2026-06-21-capture-filter-strategy-design.md`（已归档）
- 用户操作手册见 `USER_MANUAL.md`
- API + 测试用例见 `tests/` 目录
