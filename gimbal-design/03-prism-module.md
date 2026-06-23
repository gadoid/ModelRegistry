# 03 · prism 配置器详细设计

> 本文档描述 `gimbal prism` 配置器的实现细节:目录结构、HTTP API、状态管理、文件契约、lifespan 改造、前端接入点。

---

## 1. 模块职责与边界

### 1.1 职责

`gimbal prism` 是 gimbal 平台的**配置器组件**,提供:

| 功能 | 表现 |
|---|---|
| HTTP web UI | 配置器 4 Tab(元信息/配置/资源/Steps) |
| draft 编辑会话 | 多 session 隔离,含 undo/redo |
| captures 读取 | 通过 FileBus 读 `captures/active/*.ndjson`,watchdog 实时推 |
| NDJSON → Scenario | convert + builder 链路 |
| Scenario YAML 导出 | 经 schema 校验后写盘 |
| Schema + ModelRegistry 驱动 UI | `/api/schema/ui-spec` + `/api/registry/ui-spec` |

### 1.2 不做(明确排除)

| 不做 | 理由 |
|---|---|
| 启动 mitmproxy 子进程 | 由 `gimbal capture start` 独立启动 |
| 实时捕获 HTTP 流量 | capture 模块职责 |
| 执行 Scenario | `gimbal run` v0 不实现(后续看用户需求) |
| AI 助手(`gimbal/prism/ai/`) | 用户明确"先不考虑 AI" |
| 跨进程 sessions 共享 | uvicorn `--workers 1` 限制(v0) |
| 实时协作 / 多用户编辑 | v0 单用户 |

### 1.3 代码位置

```
gimbal/
└── prism/
    ├── __init__.py
    ├── server.py              # FastAPI app + lifespan
    ├── state.py               # DraftStore / SessionStore / ai 状态
    ├── builder.py             # draft → scenario(原 prism/builder.py)
    ├── convert.py             # NDJSON → step 片段
    ├── doc2model.py           # 样本 → pydantic(原 prism/doc2model.py)
    ├── cli.py                 # prism 子命令注册
    ├── render/                # schema + ModelRegistry → UI spec
    │   ├── ui_spec.py         # 序列化 Pydantic 模型为前端可消费 JSON
    │   ├── walk_model.py      # 遍历 Pydantic 模型生成 dot-path 列表
    │   └── registry_spec.py   # ★ 新增:ModelRegistry → UI spec(下拉/选项)
    └── static/
        ├── index.html         # 基于 D:/M/ModelRegistry 的样式
        ├── app.js
        └── style.css          # 基线为 D:/M/ModelRegistry
```

---

## 2. HTTP API(v0)

### 2.1 路由总览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 index.html |
| GET | `/configure?session=<sid>` | 同上,带 session 注入 |
| GET | `/static/*` | 静态资源 |
| GET | `/api/health` | 健康检查 + session 数 + 文件锁状态 |
| GET | `/api/schema/ui-spec` | **新增**:schema 序列化后的前端 spec |
| GET | `/api/schema/dot-paths` | **新增**:合法 dot-path 白名单(供 AI tools 用) |
| GET | `/api/captures?sid=<sid>` | 列出会话下的 captures(active 文件) |
| DELETE | `/api/captures?sid=<sid>` | truncate 文件(清空 UI 列表) |
| GET | `/api/captures/stream?sid=<sid>` | **新增**:SSE 推送 capture 事件(watchdog) |
| POST | `/api/captures/import-from-path` | 从 NDJSON 路径批量导入(保留兼容) |
| POST | `/api/build` | 旧 UI 兼容:DraftIn → Scenario JSON |
| GET | `/api/draft/{session_id}` | 取 session(含 draft / history / ai_config) |
| PUT | `/api/draft/{session_id}` | 覆盖 draft(保留 history 与 ai_config) |
| POST | `/api/draft/{session_id}/export` | 写 Scenario YAML 到 scenarios/{sid}.yaml |
| POST | `/api/draft/{session_id}/yaml` | 只读 YAML 预览(校验失败返回 422 + 字段错误) |
| POST | `/api/draft/{session_id}/undo` | history 弹栈 → redo |
| POST | `/api/draft/{session_id}/redo` | redo 弹栈 → history |
| GET | `/api/registry/ui-spec` | **新增**:ModelRegistry → UI spec(endpoint 下拉等) |

### 2.2 路由设计原则

| 原则 | 体现 |
|---|---|
| **REST 语义** | GET/PUT/POST/DELETE 严格对应 |
| **session 在 URL 路径或 query** | 不放 header,便于浏览器调试 |
| **失败响应结构化** | 422 错误包含字段路径(`loc`/`msg`/`type`) |
| **CORS 关闭** | v0 仅同源,未来按需放行 |

### 2.3 关键路由实现

#### 2.3.1 `/api/captures` GET

```python
@app.get("/api/captures")
def list_captures(sid: str) -> dict[str, Any]:
    """读 $GIMBAL_HOME/captures/active/{sid}.ndjson 返回事件列表。"""
    reader: CaptureReader = request.app.state.capture_reader
    path = gimbal_home / "captures" / "active" / f"{sid}.ndjson"
    if not path.exists():
        return {"count": 0, "events": []}
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return {"count": len(events), "events": events[-500:]}  # 截断保护


@app.delete("/api/captures")
def clear_captures(sid: str) -> dict[str, str]:
    path = gimbal_home / "captures" / "active" / f"{sid}.ndjson"
    if path.exists():
        # 截断而不删除(保留文件,允许 capture 继续追加)
        path.write_text("", encoding="utf-8")
    return {"status": "cleared"}
```

#### 2.3.2 `/api/captures/stream` SSE

```python
from sse_starlette.sse import EventSourceResponse

@app.get("/api/captures/stream")
async def stream_captures(sid: str) -> EventSourceResponse:
    """SSE 推送 capture 增量事件(替代原 /ws/captures WebSocket)。"""
    reader: CaptureReader = request.app.state.capture_reader
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(ev: CaptureEvent) -> None:
        queue.put_nowait(ev.to_dict())

    handle = reader.watch(sid, on_event)

    async def gen():
        try:
            while True:
                ev = await queue.get()
                yield {"event": "capture", "data": json.dumps(ev, ensure_ascii=False)}
        finally:
            handle.stop()

    return EventSourceResponse(gen())
```

**为什么从 WebSocket 改 SSE**:
- capture 是单向(server → client)推送,SSE 语义更匹配
- SSE 基于 HTTP,自动重连,无需前端维护连接状态
- EventSource API 比 WebSocket 简单

#### 2.3.3 `/api/draft/{session_id}/export`

```python
@app.post("/api/draft/{session_id}/export")
def export_draft(session_id: str, payload: ExportIn) -> dict[str, str]:
    """draft → Scenario → schema 校验 → 写 YAML。"""
    sess = request.app.state.sessions.get_or_create(session_id)
    scenario = build_scenario(sess.draft)

    # 关键:写盘前 schema 校验
    try:
        Scenario.model_validate(scenario)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"schema_errors": e.errors(include_url=False)},
        )

    out_path = payload.output_path or (
        gimbal_home / "scenarios" / f"{session_id}.yaml"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {"status": "ok", "path": str(out_path), "scenario_id": session_id}
```

---

## 3. 状态管理

### 3.1 session 存储设计

```python
# gimbal/prism/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import copy
import time


@dataclass
class Session:
    """单个 draft 会话状态。"""
    draft: dict[str, Any] = field(default_factory=lambda: DraftIn().model_dump())
    history: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        """编辑前快照(深拷贝,用于 undo)。"""
        return copy.deepcopy(self.draft)

    def push_history(self, snapshot: dict[str, Any]) -> None:
        self.history.append(snapshot)
        self.redo_stack.clear()  # 任何新编辑清空 redo

    def undo(self) -> dict[str, Any] | None:
        if not self.history:
            return None
        self.redo_stack.append(copy.deepcopy(self.draft))
        self.draft = self.history.pop()
        return self.draft

    def redo(self) -> dict[str, Any] | None:
        if not self.redo_stack:
            return None
        self.history.append(copy.deepcopy(self.draft))
        self.draft = self.redo_stack.pop()
        return self.draft


class SessionStore:
    """session_id → Session 索引。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session()
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)
```

### 3.2 app.state 取代模块级单例(功能点 11)

```python
# gimbal/prism/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动 / 关闭钩子(替代废弃的 @app.on_event)。"""
    # 启动
    app.state.gimbal_home = resolve_home()  # 解析 $GIMBAL_HOME
    app.state.sessions = SessionStore()
    app.state.capture_reader = CaptureReader(app.state.gimbal_home)
    app.state.capture_watcher = CaptureWatcher(app.state.gimbal_home)
    app.state.registry_spec_cache = None  # lazy build on first /api/registry/ui-spec

    yield

    # 关闭
    app.state.capture_watcher.stop_all()


app = FastAPI(lifespan=lifespan)


# 路由中使用
@app.get("/api/draft/{session_id}")
def get_draft(session_id: str, request: Request) -> dict[str, Any]:
    sess: SessionStore = request.app.state.sessions
    session = sess.get_or_create(session_id)
    return {
        "draft": session.draft,
        "history_len": len(session.history),
        "redo_len": len(session.redo_stack),
    }
```

### 3.3 capture 读取与监听

```python
# gimbal/prism/state.py(续)
class CaptureReader:
    """对 capture/active/*.ndjson 的只读视图。"""
    def __init__(self, home: Path) -> None:
        self.home = home

    def list_active(self) -> list[dict[str, Any]]:
        """列出所有 active session(返回 [{sid, size, mtime}])。"""
        active = self.home / "captures" / "active"
        if not active.exists():
            return []
        result = []
        for p in sorted(active.glob("*.ndjson")):
            result.append({
                "session_id": p.stem,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
        return result

    def read(self, session_id: str) -> list[dict[str, Any]]:
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        if not path.exists():
            return []
        events = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events


class CaptureWatcher:
    """watchdog 监听 active/*.ndjson 的 modify 事件。"""
    def __init__(self, home: Path) -> None:
        self.home = home
        self._observer = Observer()
        self._handlers: dict[str, "_FileHandler"] = {}
        self._observer.start()

    def watch(self, session_id: str, on_event: Callable[[dict], None]) -> "WatchHandle":
        """注册一个回调,接收该 session 的新增事件。"""
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = _FileHandler(path, on_event)
        self._observer.schedule(handler, str(path.parent), recursive=False)
        self._handlers[session_id] = handler
        return WatchHandle(self, session_id)

    def stop_all(self) -> None:
        self._observer.stop()
        self._observer.join()


class WatchHandle:
    def __init__(self, watcher: CaptureWatcher, session_id: str) -> None:
        self._watcher = watcher
        self._session_id = session_id

    def stop(self) -> None:
        # watchdog Observer.unschedule
        ...


class _FileHandler(FileSystemEventHandler):
    def __init__(self, path: Path, on_event: Callable) -> None:
        self.path = path
        self.on_event = on_event
        self._last_pos = 0

    def on_modified(self, event):
        if Path(event.src_path) != self.path:
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                f.seek(self._last_pos)
                for line in f:
                    if line.strip():
                        self.on_event(json.loads(line))
                self._last_pos = f.tell()
        except FileNotFoundError:
            pass  # 文件被归档后删除,忽略
```

---

## 4. NDJSON → Scenario 流水线

### 4.1 三段链路

```
captures/active/{sid}.ndjson
       │
       │ 1. convert.py: NDJSON → step 片段数组(只整理字段,不校验)
       ▼
step_fragments: list[dict]
       │
       │ 2. builder.py: 把 step_fragments 装进 ScenarioDraft
       ▼
ScenarioDraft dataclass
       │
       │ 3. builder.build_scenario: → dict
       ▼
scenario_dict
       │
       │ 4. schema.Scenario.model_validate
       ▼
validated Scenario
       │
       │ 5. yaml.safe_dump
       ▼
scenarios/{sid}.yaml
```

### 4.2 convert.py(从 prism/convert.py 迁入,加 session_id 过滤)

```python
# gimbal/prism/convert.py(节选)
def convert_file(source: Path, session_id: str | None = None) -> list[dict]:
    """读 NDJSON 文件,转 step 片段数组。

    session_id 不为空时,只转换 host/path 与该 session 历史匹配的请求(用于增量转换)。
    """
    steps = []
    with source.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ev = json.loads(line)
            step = convert_record(ev)
            steps.append(step)
    return steps


def convert_record(ev: dict) -> dict:
    """单条 capture → step 片段(不写 schema,只整理字段)。

    规则:
    - Authorization 头替换为占位(由 builder 在最后一步根据 default_user_key 决定是否替换为 ${auth.<key>.token})
    - body 尝试 json.loads,失败包成 {_raw: ...}
    - query 转 params
    """
    headers = dict(ev.get("headers", {}))
    # 暂时保留 Authorization(由 builder 决定怎么脱敏)
    body = ev.get("body", "")
    parsed_body: dict
    try:
        v = json.loads(body) if body else {}
        parsed_body = v if isinstance(v, dict) else {"_value": v}
    except json.JSONDecodeError:
        parsed_body = {"_raw": body}

    return {
        "method": ev["method"],
        "host": ev["host"],
        "port": ev.get("port", 80 if ev.get("scheme") == "http" else 443),
        "scheme": ev.get("scheme", "http"),
        "path": ev["path"],
        "query": ev.get("query", {}),
        "headers": headers,
        "body": parsed_body,
        "response_status": ev.get("response", {}).get("status"),
        "response_headers": ev.get("response", {}).get("headers", {}),
        "response_body": ev.get("response", {}).get("body", ""),
    }
```

### 4.3 builder.py 改造点

| 改造点 | 现状(prism/builder.py) | v0(gimbal/prism/builder.py) |
|---|---|---|
| import schema | `from schema import ...` | `from gimbal.schema import ...` |
| Step.key 字段 | 用 `setattr(step, "_step_key", ...)` 临时挂 | 改用 `Step.key = ...`(schema.Step 新增字段,见 05) |
| Meta.name 校验 | 不校验空字符串 | 不需要(builder 输出前 schema 校验会拒) |
| 默认断言 name | `assert_status_{hash(path):x}` | `assert_status_{idx}`(可复现,功能点 13) |
| Resource.kind | `if/elif` 串行(功能点 12) | 用 `Literal` 派发 + schema 校验兜底 |
| MockRef / FileRef | 不实现 | 补齐 |
| variable 资源 | 兜底为 `Mock(config={"variable": ...})` | 同上,但 schema 加 `variable` kind(可选,见 03 §8) |

### 4.4 build_scenario 出口

```python
def build_scenario(draft: ScenarioDraft) -> dict[str, Any]:
    """draft → scenario dict(供 schema 校验 + YAML 导出)。"""
    sc_cfg = ScenarioConfig(...)
    scenario = Scenario(
        scenarioId=draft.scenario_id,
        meta=Meta(...),
        config=sc_cfg,
        resource={rd.name: _build_resource(rd) for rd in draft.resources.values()},
        steps=[_build_step(...) for i, sd in enumerate(draft.steps)],
    )
    return scenario.model_dump(mode="json")  # camelCase 输出
```

---

## 5. schema 校验失败处理

### 5.1 错误响应结构

```json
// HTTP 422
{
  "detail": {
    "schema_errors": [
      {
        "type": "string_too_short",
        "loc": ["meta", "name"],
        "msg": "String should have at least 1 character",
        "input": "",
        "ctx": {"min_length": 1}
      }
    ]
  }
}
```

### 5.2 前端处理

```javascript
// app.js(节选)
async function exportDraft() {
  const resp = await fetch(`/api/draft/${sid}/export`, { method: "POST", ... });
  if (resp.status === 422) {
    const err = await resp.json();
    showValidationErrors(err.detail.schema_errors);
    // 高亮对应字段,定位到 [loc[0], loc[1], ...]
    return;
  }
  // ...
}
```

---

## 6. ModelRegistry → UI spec 接入(新增)

### 6.1 设计目标

`gimbal/contracts/ModelRegistry`(源自 D:/M/ModelRegistry)用于驱动前端下拉选项,典型场景:

| 场景 | 数据源 | 渲染 |
|---|---|---|
| 资源 `kind` 选择 | `ResourceKind` Literal | `<select>` |
| `auth.<key>` 引用 | ModelRegistry 中已注册的 auth 资源 | `<select>` 自动补全 |
| `Mock` 配置模板 | ModelRegistry 中已注册的 mock 配置 | `<select>` 选模板 |
| `Api.host` 提示 | `EndpointSpec` 集合 | `<datalist>` 自动补全 |

### 6.2 启动期反射

```python
# gimbal/prism/render/registry_spec.py
from gimbal.contracts import registry
from typing import Any

def build_registry_spec() -> dict[str, Any]:
    """启动时反射 ModelRegistry 一次,生成前端可消费的 spec。

    缺失关键字段时启动失败(显式优于隐式)。
    """
    return {
        "kinds": ["mock", "mock_ref", "file", "file_ref"],
        "endpoints": [
            {"id": ep.id, "method": ep.method, "path": ep.path, "host": ep.host}
            for ep in registry.list_endpoints()
        ],
        "auth_keys": list(registry.list_auth_keys()),
        "mock_templates": [
            {"name": t.name, "image": t.image, "config": t.config}
            for t in registry.list_mock_templates()
        ],
    }
```

### 6.3 HTTP 暴露

```python
# gimbal/prism/server.py
@app.get("/api/registry/ui-spec")
def get_registry_ui_spec(request: Request) -> dict[str, Any]:
    """返回 ModelRegistry → UI spec(供前端下拉/选项用)。"""
    if request.app.state.registry_spec_cache is None:
        request.app.state.registry_spec_cache = build_registry_spec()
    return request.app.state.registry_spec_cache
```

### 6.4 前端消费

```javascript
// app.js
const REG_SPEC = await fetch("/api/registry/ui-spec").then(r => r.json());

// 资源 kind select
const kindSelect = document.getElementById("tp-kind");
for (const k of REG_SPEC.kinds) {
  const opt = document.createElement("option");
  opt.value = k; opt.textContent = k;
  kindSelect.appendChild(opt);
}

// host 自动补全
const hostDatalist = document.getElementById("host-options");
for (const ep of REG_SPEC.endpoints) {
  const opt = document.createElement("option");
  opt.value = ep.host;
  hostDatalist.appendChild(opt);
}
```

### 6.5 ModelRegistry 字段漂移防护

如果 D:/M/ModelRegistry 后续修改了 `EndpointSpec` 等 dataclass 字段名,`build_registry_spec` 启动时会抛 AttributeError,直接阻止 prism 启动——这是**显式优于隐式**的取舍。

---

## 7. 痛点修复清单

### 7.1 功能点 11 · FastAPI lifespan 改造

| 现状 | v0 |
|---|---|
| `prism/server.py:64-69` 模块级 mutable 单例 | `app.state.*` 集中管理 |
| `@app.on_event("startup")`(已废弃) | `@asynccontextmanager async def lifespan(app)` |
| `_loop` 全局变量 | `asyncio.get_event_loop()`(或 `asyncio.get_running_loop()`) |
| `recorder` 实例挂在模块上 | `request.app.state.capture_reader` |

### 7.2 功能点 12 · 资源 kind 收敛

```python
# gimbal/prism/builder.py(节选)
from typing import Literal

ResourceKind = Literal["mock", "mock_ref", "file", "file_ref"]  # 不含 variable(v0.1)


def _build_resource(rd: ResourceDraft) -> dict[str, Any]:
    """按 rd.kind 派发构造 schema.ResourceUnion 之一。"""
    dispatch = {
        "mock": lambda: {"kind": "mock", "name": rd.name,
                          "image": rd.image or "nginx:latest",
                          "config": rd.config or {},
                          "portMapping": _parse_port_mapping(rd.port_mapping)},
        "mock_ref": lambda: {"kind": "mock_ref", "ref": rd.ref},
        "file": lambda: {"kind": "file", "name": rd.name, "path": rd.path or ""},
        "file_ref": lambda: {"kind": "file_ref", "ref": rd.ref},
    }
    if rd.kind not in dispatch:
        raise ValidationError(f"未知 resource kind: {rd.kind!r}")
    return dispatch[rd.kind]()


def _parse_port_mapping(raw: dict | None) -> dict[int, int]:
    if not raw:
        return {}
    try:
        return {int(k): int(v) for k, v in raw.items()}
    except (ValueError, TypeError) as e:
        raise ValidationError(f"portMapping 必须都是数字: {e}")
```

**variable 资源 v0 决定**:
- 选项 A:UI 移除"变量" tile,只保留 mock / mock_ref / file / file_ref(本设计采纳)
- 选项 B:在 schema.ResourceUnion 加 `Variable` 子类(留给 v0.1 单独 PR)

### 7.3 功能点 13 · 默认断言 name 可复现

```python
# 现状(builder.py:237)
name=f"assert_status_{abs(hash(path)) & 0xFFFF:x}"  # 不可复现

# v0
name=f"assert_status_{idx}"  # 进程内索引,可复现
```

唯一约束:必须保证同 step 内 strategy 唯一。改用 `f"assert_status_{idx}__{slug}"` 进一步确保跨 step 不重名。

---

## 8. CLI 子命令

### 8.1 `gimbal prism` 命令组(`gimbal/cli/prism.py`)

```python
import typer
import uvicorn
from pathlib import Path

prism_app = typer.Typer(help="gimbal 配置器(web)", no_args_is_help=True)


@prism_app.command("start")
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
    workers: int = typer.Option(1, "--workers", "-w", help="uvicorn workers,v0 仅支持 1"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
):
    """启动 prism 配置器 web UI。"""
    if workers != 1:
        typer.secho("[prism] v0 仅支持 --workers 1", fg=typer.colors.YELLOW)
        workers = 1

    if not home.exists():
        typer.secho(f"[prism] 警告: {home} 不存在,自动创建", fg=typer.colors.YELLOW)
        home.mkdir(parents=True, exist_ok=True)

    # 通过环境变量把 home 传给 server
    import os
    os.environ["GIMBAL_HOME"] = str(home)

    typer.echo(f"[prism] GIMBAL_HOME={home}")
    typer.echo(f"[prism] starting on http://{host}:{port}")

    uvicorn.run(
        "gimbal.prism.server:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="info",
    )
```

### 8.2 启动信息

```
$ gimbal prism start --port 9000
[prism] GIMBAL_HOME=C:\Users\me\.gimbal
[prism] starting on http://127.0.0.1:9000
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:9000 (Press CTRL+C to quit)
```

---

## 9. 前端接入(D:/M/ModelRegistry 样式)

### 9.1 基线选择

| 选项 | 选择 | 理由 |
|---|---|---|
| D:/M/ModelRegistry 的 `prism/static/*` | ✅ 基线 | 320 行 index.html,861 行 style.css,纯净配置器(无 AI 视图) |
| d:/mirror 现有 `prism/static/*` | 不选 | 420 行 index.html + AI 视图,与 v0 范围不符 |
| 完全重写 | 不选 | 浪费工作 |

**采纳方案**:用 D:/M/ModelRegistry 的 `index.html` / `style.css` / `app.js` 直接作为 v0 前端基线,不叠加 AI 视图。

### 9.2 迁移步骤

1. **复制基线**
   ```bash
   cp D:/M/ModelRegistry/prism/static/index.html gimbal/prism/static/index.html
   cp D:/M/ModelRegistry/prism/static/style.css gimbal/prism/static/style.css
   cp D:/M/ModelRegistry/prism/static/app.js gimbal/prism/static/app.js
   ```

2. **API 路径兼容**:D:/M/ModelRegistry 的 app.js 调 `/api/captures` 不带 `?sid=` 参数(假设单 session),需要改造为多 session 模式:

   ```javascript
   // 现状(D:/M/ModelRegistry app.js)
   fetch('/api/captures').then(...)

   // v0
   const sid = getSessionIdFromUrl();  // 或本地存储
   fetch(`/api/captures?sid=${sid}`).then(...)
   ```

3. **新增 schema 驱动渲染**(见 [04-schema-ssot.md](04-schema-ssot.md)):
   - `/api/schema/ui-spec` 返回字段定义
   - app.js 改为 fetch spec 后动态生成 input/select

4. **新增 ModelRegistry 驱动选项**(见本文件 §6):
   - `/api/registry/ui-spec` 返回 endpoint/auth/template 选项
   - app.js 渲染 `<select>` / `<datalist>`

### 9.3 样式调整点

v0 不引入 d:/mirror 现有 AI 视图,D:/M/ModelRegistry 样式即最终样式,无需合并/调整。

---

## 10. 测试策略

### 10.1 单元测试

| 测试文件 | 覆盖 |
|---|---|
| `test_state.py` | Session / SessionStore / undo-redo |
| `test_lifespan.py` | lifespan 启动关闭钩子 |
| `test_capture_reader.py` | CaptureReader 读取 + list |
| `test_capture_watcher.py` | CaptureWatcher mock watchdog 事件 |
| `test_builder.py` | build_scenario 各 kind / 各字段 |
| `test_schema_validation.py` | Schema 校验失败 → 422 响应结构 |
| `test_resource_kind.py` | 功能点 12 派发表 |
| `test_assertion_name.py` | 功能点 13 可复现性 |
| `test_prism_render.py` | schema + ModelRegistry → UI spec |
| `test_registry_spec.py` | ModelRegistry 反射 → UI spec 字段完整 |

### 10.2 集成测试(`tests/integration/`)

| 测试 | 验证 |
|---|---|
| `test_prism_capture_e2e.py` | 启动 capture → 启动 prism → UI 显示捕获 → 导出 YAML |
| `test_yaml_export_422.py` | 校验失败 → 422 + 字段路径 |
| `test_session_undo_redo.py` | undo/redo 还原 |

---

## 11. 已知限制与未来工作

| 限制 | v0 处理 | 未来 |
|---|---|---|
| uvicorn `--workers > 1` 不可用 | 文档警告 + 强制设 1 | sessions 改存 Redis |
| 长 NDJSON 内存爆炸 | 单 session 上限 500 条 | 流式分页 |
| schema ResourceUnion 无 variable | UI 移除 variable tile | 加 Variable 子类(可选) |
| ModelRegistry 字段手维护 | 启动期反射,缺失时启动失败 | 字段漂移监控(后续) |

---

## 12. 下游文档引用

- 总体架构 → [01-architecture.md](01-architecture.md) §1
- capture 模块(capture 读取面) → [02-capture-module.md](02-capture-module.md) §3
- schema 驱动 UI → [04-schema-ssot.md](04-schema-ssot.md)
- ModelRegistry 引入影响 Step.key / Meta.name → [05-model-registry-integration.md](05-model-registry-integration.md) §2
- 迁移执行步骤 → [06-migration-plan.md](06-migration-plan.md) M1/M2