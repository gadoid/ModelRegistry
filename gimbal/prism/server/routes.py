"""gimbal.prism.server.routes — HTTP + WebSocket route handlers.

Routes are defined on a FastAPI APIRouter and mounted on the main app
via `app.include_router(router)` in `gimbal.prism.server.app`.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from gimbal.prism.builder import build_scenario
from gimbal.prism.render import build_registry_spec, build_ui_spec, walk_fields
from gimbal.schema import Scenario
from gimbal.prism.server.conversions import _draft_from_in
from gimbal.prism.server.wire import ExportIn
from gimbal.prism.state import CaptureReader, CaptureWatcher, DraftIn, SessionStore

router = APIRouter()


# ────────────────────────────────────────────────────────────────────────────
# 通用
# ────────────────────────────────────────────────────────────────────────────


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "sessions": len(request.app.state.sessions),
        "captures_active": len(request.app.state.capture_reader.list_active()),
    }


# ────────────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────────────


@router.get("/api/schema/ui-spec")
def schema_ui_spec(request: Request) -> dict[str, Any]:
    """返回 schema → 前端可消费 JSON (Phase 2 SSOT)。"""
    cache = getattr(request.app.state, "ui_spec_cache", None)
    if cache is None:
        cache = build_ui_spec(Scenario)
        request.app.state.ui_spec_cache = cache
    return cache


@router.get("/api/schema/dot-paths")
def schema_dot_paths() -> dict[str, Any]:
    """返回所有合法的 dot-path(供前端校验 / 未来 AI 工具)。"""
    paths = [path for path, _fi, _m in walk_fields(Scenario)]
    return {"paths": paths, "count": len(paths)}


@router.get("/api/registry/ui-spec")
def registry_ui_spec(request: Request) -> dict[str, Any]:
    """返回 ModelRegistry → 前端 UI spec (Phase 3)。"""
    cache = getattr(request.app.state, "registry_spec_cache", None)
    if cache is None:
        cache = build_registry_spec()
        request.app.state.registry_spec_cache = cache
    return cache


# ────────────────────────────────────────────────────────────────────────────
# captures (文件视角)
# ────────────────────────────────────────────────────────────────────────────


@router.get("/api/captures")
def list_captures(
    request: Request, sid: str = Query(..., description="会话 ID"),
    limit: int = Query(500, ge=1, le=10000),
) -> dict[str, Any]:
    reader: CaptureReader = request.app.state.capture_reader
    events = reader.read(sid, limit=limit)
    return {"count": len(events), "events": events, "sid": sid}


@router.delete("/api/captures")
def clear_captures(
    request: Request, sid: str = Query(..., description="会话 ID"),
) -> dict[str, str]:
    reader: CaptureReader = request.app.state.capture_reader
    reader.truncate(sid)
    return {"status": "cleared", "sid": sid}


@router.post("/api/captures/inject")
def inject_capture(
    request: Request, sid: str = Query(..., description="会话 ID"),
    payload: dict[str, Any] = ...,
) -> dict[str, str]:
    """单 event 追加(给测试 / replay 工具用)。"""
    reader: CaptureReader = request.app.state.capture_reader
    reader.append(sid, payload)
    return {"status": "ok", "sid": sid}


@router.post("/api/captures/import-from-path")
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


@router.get("/api/captures/stream")
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


@router.websocket("/ws/captures")
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


@router.get("/api/draft/{session_id}")
def get_draft(request: Request, session_id: str) -> dict[str, Any]:
    sess: SessionStore = request.app.state.sessions
    s = sess.get_or_create(session_id)
    return {
        "draft": s.draft,
        "history_len": len(s.history),
        "redo_len": len(s.redo_stack),
    }


@router.put("/api/draft/{session_id}")
def put_draft(
    request: Request, session_id: str, payload: DraftIn,
) -> dict[str, str]:
    sess: SessionStore = request.app.state.sessions
    s = sess.get_or_create(session_id)
    s.push_history(s.snapshot())
    s.draft = payload.model_dump()
    return {"status": "ok", "session_id": session_id}


@router.post("/api/draft/{session_id}/export")
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


@router.post("/api/draft/{session_id}/yaml")
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