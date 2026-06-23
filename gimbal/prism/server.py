"""gimbal.prism.server — FastAPI 配置器后端 (痛点 11 lifespan 改造)。

v0 vs prism/server.py 的差异:
  - 模块级单例 (recorder / ws_clients / _loop / sessions) **全部删除**
  - 走 @asynccontextmanager lifespan + app.state
  - captures 数据走文件: $GIMBAL_HOME/captures/active/{sid}.ndjson
  - WebSocket /ws/captures → SSE /api/captures/stream?sid=
  - schema 校验在 export 之前跑, 失败 → 422 + 字段错误
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from gimbal.schema import Scenario  # v0.1: 迁到 gimbal.schema (Phase 2)

from gimbal.prism.builder import (
    AuthDraft,
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
    build_scenario,
)
from gimbal.prism.state import (
    CaptureReader,
    CaptureWatcher,
    SessionStore,
)
from gimbal.prism.render import build_ui_spec, walk_fields, build_registry_spec

logger = logging.getLogger("gimbal.prism.server")

STATIC_DIR = Path(__file__).parent / "static"


# ────────────────────────────────────────────────────────────────────────────
# Pydantic wire form
# ────────────────────────────────────────────────────────────────────────────


class UserIn(BaseModel):
    key: str
    url: str = ""
    username: str = ""
    password: str = ""
    expires_in: int = 7200
    token_type: str = "Authorization"
    token: Optional[str] = None
    confirm_password: bool = False


class DraftIn(BaseModel):
    """ScenarioDraft 的 wire 形式。直接由 UI 表单序列化。

    v0.5.1: 新增 ``steps: list[dict]`` 字段, 携带 step 完整自定义
    (api_override / req_override / assertions / extracts / assigns / key_hint)。
    旧 ``step_ids`` 字段保留, 仅作为从 captures 文件派生 steps 的 fallback。

    v0.5.8: ``name`` 默认值改为 ``"template"`` (新 session 草稿创建时即带此名, 提醒用户填真实名).
    """
    scenario_id: str = "sc_new"
    name: str = "template"
    description: str = ""
    module: str = "default"
    priority: int = 1
    author: str = "prism"
    owner: str = "prism"
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    expire: bool = False
    requirement_ref: list[str] = Field(default_factory=list)
    services: dict[str, str] = Field(default_factory=dict)
    users: list[UserIn] = Field(default_factory=list)
    time_policy_kind: str = "record"
    time_policy_seconds: int = 60
    retry_enabled: bool = False
    retry_max_attempts: int = 3
    retry_backoff_seconds: float = 20.0
    retry_on: list[str] = Field(default_factory=list)
    setup_refs: list[str] = Field(default_factory=list)
    teardown_refs: list[str] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    # v0.5.1: 完整 step 自定义 (新字段, 优先使用)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    # 旧字段: 仍支持, 仅在 steps 为空时作 fallback (从 captures 文件读)
    step_ids: list[str] = Field(default_factory=list)


class ExportIn(DraftIn):
    fmt: str = "yaml"
    output_path: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _redact_user(u: UserIn) -> AuthDraft:
    """password 默认走 <REDACTED>, 仅 confirm_password=True 才落明文。"""
    pw = u.password or ""
    if not u.confirm_password and pw and pw != "<REDACTED>":
        pw = "<REDACTED>"
    return AuthDraft(
        url=u.url, username=u.username, password=pw,
        expires_in=u.expires_in, token_type=u.token_type, token=u.token,
    )


def _draft_from_in(
    payload: DraftIn, capture_reader: CaptureReader, session_id: str,
) -> ScenarioDraft:
    users = {u.key: _redact_user(u) for u in payload.users}
    resources: dict[str, ResourceDraft] = {}
    for r in payload.resources:
        resources[r["name"]] = ResourceDraft(
            name=r["name"], kind=r.get("kind", "mock"), image=r.get("image", ""),
            config=r.get("config") or {},
            port_mapping={str(k): v for k, v in (r.get("port_mapping") or {}).items()},
            path=r.get("path", ""), ref=r.get("ref", ""), value=r.get("value"),
        )
    # v0.5.1 (P0 修复): 优先用 payload.steps 携带的完整自定义
    # fallback: step_ids 索引 captures 文件 (旧客户端兼容, 但不带自定义)
    if payload.steps:
        steps = [
            StepDraft(
                capture=s["capture"],
                enabled=s.get("enabled", True),
                add_status_assertion=s.get("add_status_assertion", True),
                extracts=s.get("extracts") or [],
                assigns=s.get("assigns") or [],
                assertions=s.get("assertions") or [],
                key_hint=s.get("key_hint") or "",
                note=s.get("note") or "",
                api_override=s.get("api_override"),
                req_override=s.get("req_override"),
            )
            for s in payload.steps
        ]
    else:
        # 旧路径: 从 capture 文件读所有事件, 用 step_ids 索引
        all_events = capture_reader.read(session_id, limit=None)
        id_to_event = {str(i): e for i, e in enumerate(all_events)}
        steps = []
        for sid in payload.step_ids:
            if sid in id_to_event:
                steps.append(StepDraft(capture=id_to_event[sid]))
    return ScenarioDraft(
        scenario_id=payload.scenario_id, name=payload.name,
        description=payload.description, module=payload.module,
        priority=payload.priority, author=payload.author, owner=payload.owner,
        tags=payload.tags or ["smoke"], version=payload.version,
        expire=payload.expire, requirement_ref=payload.requirement_ref,
        services=payload.services, users=users,
        time_policy_kind=payload.time_policy_kind,
        time_policy_seconds=payload.time_policy_seconds,
        retry_enabled=payload.retry_enabled,
        retry_max_attempts=payload.retry_max_attempts,
        retry_backoff_seconds=payload.retry_backoff_seconds,
        retry_on=payload.retry_on,
        setup_refs=payload.setup_refs, teardown_refs=payload.teardown_refs,
        resources=resources, steps=steps,
    )


# ────────────────────────────────────────────────────────────────────────────
# App + lifespan (痛点 11)
# ────────────────────────────────────────────────────────────────────────────


def _resolve_gimbal_home() -> Path:
    env = os.environ.get("GIMBAL_HOME")
    if env:
        return Path(env).expanduser()
    return Path("~/.gimbal").expanduser()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动期初始化 / 关闭期清理 (痛点 11: 替代模块级单例)。"""
    home = _resolve_gimbal_home()
    home.mkdir(parents=True, exist_ok=True)
    app.state.gimbal_home = home
    app.state.sessions = SessionStore()
    app.state.capture_reader = CaptureReader(home)
    app.state.capture_watcher = CaptureWatcher(home)
    app.state.ui_spec_cache = None  # Phase 2 填充
    app.state.registry_spec_cache = None  # Phase 3 填充
    logger.info("[prism] GIMBAL_HOME=%s", home)
    try:
        yield
    finally:
        app.state.capture_watcher.stop_all()
        logger.info("[prism] shutdown complete")


app = FastAPI(title="gimbal prism configurator", version="0.1.0", lifespan=lifespan)


# ────────────────────────────────────────────────────────────────────────────
# 通用
# ────────────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "sessions": len(request.app.state.sessions),
        "captures_active": len(request.app.state.capture_reader.list_active()),
    }


# ────────────────────────────────────────────────────────────────────────────
# captures (文件视角)
# ────────────────────────────────────────────────────────────────────────────


@app.get("/api/schema/ui-spec")
def schema_ui_spec(request: Request) -> dict[str, Any]:
    """返回 schema → 前端可消费 JSON (Phase 2 SSOT)。"""
    cache = getattr(request.app.state, "ui_spec_cache", None)
    if cache is None:
        cache = build_ui_spec(Scenario)
        request.app.state.ui_spec_cache = cache
    return cache


@app.get("/api/schema/dot-paths")
def schema_dot_paths() -> dict[str, Any]:
    """返回所有合法的 dot-path(供前端校验 / 未来 AI 工具)。"""
    paths = [path for path, _fi, _m in walk_fields(Scenario)]
    return {"paths": paths, "count": len(paths)}


@app.get("/api/registry/ui-spec")
def registry_ui_spec(request: Request) -> dict[str, Any]:
    """返回 ModelRegistry → 前端 UI spec (Phase 3)。"""
    cache = getattr(request.app.state, "registry_spec_cache", None)
    if cache is None:
        cache = build_registry_spec()
        request.app.state.registry_spec_cache = cache
    return cache


@app.get("/api/captures")
def list_captures(
    request: Request, sid: str = Query(..., description="会话 ID"),
    limit: int = Query(500, ge=1, le=10000),
) -> dict[str, Any]:
    reader: CaptureReader = request.app.state.capture_reader
    events = reader.read(sid, limit=limit)
    return {"count": len(events), "events": events, "sid": sid}


@app.delete("/api/captures")
def clear_captures(
    request: Request, sid: str = Query(..., description="会话 ID"),
) -> dict[str, str]:
    reader: CaptureReader = request.app.state.capture_reader
    reader.truncate(sid)
    return {"status": "cleared", "sid": sid}


@app.post("/api/captures/inject")
def inject_capture(
    request: Request, sid: str = Query(..., description="会话 ID"),
    payload: dict[str, Any] = ...,
) -> dict[str, str]:
    """单 event 追加(给测试 / replay 工具用)。"""
    reader: CaptureReader = request.app.state.capture_reader
    reader.append(sid, payload)
    return {"status": "ok", "sid": sid}


@app.post("/api/captures/import-from-path")
def import_from_path(
    request: Request, sid: str = Query(..., description="会话 ID"),
    payload: dict[str, Any] = ...,
) -> dict[str, Any]:
    """从 NDJSON 路径批量追加到 active/{sid}.ndjson (安全约束: path 必须在 CWD 内)。"""
    raw = payload.get("path", "")
    if not raw:
        raise HTTPException(400, "path 必填")
    p = Path(raw)
    try:
        p_abs = p.resolve(strict=False)
    except OSError as e:
        raise HTTPException(400, f"无法解析 path: {p} ({e})")
    cwd = Path.cwd().resolve()
    try:
        p_abs.relative_to(cwd)
    except ValueError:
        raise HTTPException(403, f"path 必须在 CWD 之内(允许: {cwd});拒绝: {p_abs}")
    if not p_abs.exists():
        raise HTTPException(404, f"文件不存在: {p_abs}")
    if not p_abs.is_file():
        raise HTTPException(400, f"不是文件: {p_abs}")
    reader: CaptureReader = request.app.state.capture_reader
    count = 0
    with p_abs.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            reader.append(sid, json.loads(line))
            count += 1
    return {"status": "ok", "imported": count, "path": str(p_abs), "sid": sid}


@app.get("/api/captures/stream")
async def stream_captures(
    request: Request, sid: str = Query(..., description="会话 ID"),
):
    """SSE 推送 capture 增量事件 (替代原 /ws/captures WebSocket)。"""
    try:
        from sse_starlette.sse import EventSourceResponse
    except ImportError:
        raise HTTPException(500, "sse-starlette 未装")
    reader: CaptureReader = request.app.state.capture_reader
    watcher: CaptureWatcher = request.app.state.capture_watcher
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(ev: dict) -> None:
        queue.put_nowait(ev)

    handle = watcher.watch(sid, on_event)

    async def gen():
        try:
            # 启动时先发一帧现有所有事件, 让前端一次性补齐
            for ev in reader.read(sid, limit=None):
                yield {"event": "capture", "id": str(ev.get("ts", 0)), "data": json.dumps(ev, ensure_ascii=False)}
            while True:
                ev = await queue.get()
                yield {"event": "capture", "id": str(ev.get("ts", 0)), "data": json.dumps(ev, ensure_ascii=False)}
        finally:
            handle.stop()

    return EventSourceResponse(gen())


# ────────────────────────────────────────────────────────────────────────────
# WebSocket /ws/captures (v0.5 — 替代 SSE, 适配 PR1SM 前端 app.js)
# ────────────────────────────────────────────────────────────────────────────


@app.websocket("/ws/captures")
async def ws_captures(websocket: WebSocket, sid: str = Query("default")) -> None:
    """WebSocket 推送 capture 增量事件。

    协议 (兼容 PR1SM app.js):
      - 客户端:  connect ws://.../ws/captures?sid=<sid>
      - 服务端:  连上后立刻发 1 帧 {"type":"hello","count":N,"events":[...]}
      - 服务端:  每条新事件发  {"type":"capture","data":<event_dict>}
    """
    await websocket.accept()
    reader: CaptureReader = websocket.app.state.capture_reader
    watcher: CaptureWatcher = websocket.app.state.capture_watcher

    # hello 帧: 把当前 session 的历史事件一次性补齐
    existing = reader.read(sid, limit=None)
    await websocket.send_json(
        {"type": "hello", "count": len(existing), "events": existing}
    )

    queue: asyncio.Queue = asyncio.Queue()

    def on_event(ev: dict) -> None:
        queue.put_nowait(ev)

    handle = watcher.watch(sid, on_event)
    try:
        while True:
            ev = await queue.get()
            await websocket.send_json({"type": "capture", "data": ev})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        handle.stop()


# ────────────────────────────────────────────────────────────────────────────
# session / draft
# ────────────────────────────────────────────────────────────────────────────


@app.get("/api/draft/{session_id}")
def get_draft(request: Request, session_id: str) -> dict[str, Any]:
    sess: SessionStore = request.app.state.sessions
    s = sess.get_or_create(session_id)
    return {
        "draft": s.draft,
        "history_len": len(s.history),
        "redo_len": len(s.redo_stack),
    }


@app.put("/api/draft/{session_id}")
def put_draft(
    request: Request, session_id: str, payload: DraftIn,
) -> dict[str, str]:
    sess: SessionStore = request.app.state.sessions
    s = sess.get_or_create(session_id)
    s.push_history(s.snapshot())
    s.draft = payload.model_dump()
    return {"status": "ok", "session_id": session_id}


@app.post("/api/draft/{session_id}/export")
def export_draft(
    request: Request, session_id: str, payload: ExportIn,
) -> dict[str, Any]:
    reader: CaptureReader = request.app.state.capture_reader
    home: Path = request.app.state.gimbal_home
    draft = _draft_from_in(payload, reader, session_id)
    # build_scenario 内部会构造 Pydantic Meta, 校验失败要捕获
    try:
        scenario = build_scenario(draft)
        Scenario.model_validate(scenario)
    except ValidationError as e:
        raise HTTPException(
            422, detail={"schema_errors": e.errors(include_url=False)},
        )
    if payload.output_path:
        out_path = Path(payload.output_path)
    else:
        out_path = home / "scenarios" / f"{session_id}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if payload.fmt == "yaml":
        out_path.write_text(
            yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    else:
        out_path.write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return {"status": "ok", "path": str(out_path), "fmt": payload.fmt, "scenario_id": session_id}


@app.post("/api/draft/{session_id}/yaml")
def preview_yaml(
    request: Request, session_id: str, payload: DraftIn,
) -> JSONResponse:
    """只读 YAML 预览: 校验失败 → 422 + 字段错误。"""
    reader: CaptureReader = request.app.state.capture_reader
    draft = _draft_from_in(payload, reader, session_id)
    try:
        scenario = build_scenario(draft)
        Scenario.model_validate(scenario)
    except ValidationError as e:
        return JSONResponse(
            {
                "errors": [
                    {"field": ".".join(str(x) for x in err["loc"]), "msg": err["msg"]}
                    for err in e.errors()
                ]
            },
            status_code=422,
        )
    return JSONResponse({
        "yaml": yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False),
    })


# ────────────────────────────────────────────────────────────────────────────
# 静态 + index
# ────────────────────────────────────────────────────────────────────────────


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> HTMLResponse:
    idx = STATIC_DIR / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>gimbal prism UI not built</h1>", status_code=500)
    return HTMLResponse(idx.read_text(encoding="utf-8"))


@app.get("/configure")
def configure(session: str = Query(...)) -> HTMLResponse:
    """带 session 注入的同 HTML。"""
    idx = STATIC_DIR / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>gimbal prism UI not built</h1>", status_code=500)
    html = idx.read_text(encoding="utf-8")
    inject = f'<meta name="gimbal-session" content="{session}" />'
    html = html.replace("<head>", f"<head>\n  {inject}", 1)
    return HTMLResponse(html)
