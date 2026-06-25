"""gimbal.prism.server.app — FastAPI app + lifespan + middleware + static mount.

This module assembles the FastAPI application, wires the lifespan
context manager, mounts the static UI assets, and includes the routes
submodule's APIRouter.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from gimbal.prism.state import (
    CaptureReader,
    CaptureWatcher,
    SessionStore,
)

logger = logging.getLogger("gimbal.prism.server")

STATIC_DIR = Path(__file__).parent.parent / "static"


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


# Build app; routes are registered via include_router in routes module.
# To avoid a circular import, we import routes after `app` is defined
# (lifespan closure over `app` is needed by routes module? No — they
# use Request, not lifespan directly).
# However, `lifespan` is referenced as a string in FastAPI(...) which
# resolves at decoration time. So we must import routes here, AFTER
# the `app` is constructed.
app = FastAPI(title="gimbal prism configurator", version="0.1.0", lifespan=lifespan)


# Register routes
from gimbal.prism.server.routes import router as _routes_router  # noqa: E402
app.include_router(_routes_router)


# ────────────────────────────────────────────────────────────────────────────
# 静态 + index
# ────────────────────────────────────────────────────────────────────────────


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ────────────────────────────────────────────────────────────────────────────
# v0.5.5: dev 期 Cache-Control 修复 — 防止浏览器启发式缓存过期 app.js / style.css
# ────────────────────────────────────────────────────────────────────────────
# FastAPI StaticFiles 默认不发 cache-control 头, 浏览器按启发式规则 (now - last_modified) * 10%
# 缓存 dev server 上的静态文件。改完 app.js 后用户刷新仍看到旧版, 点 新增 step 无响应等。
# 中间件强制加 no-cache, 让浏览器每次走 ETag 协商拿最新内容。
@app.middleware("http")
async def _no_cache_static_and_index(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path in ("/", "/configure"):
        # no-cache 而非 no-store: 浏览器可本地缓存, 但每次 revalidate
        if "cache-control" not in response.headers:
            response.headers["cache-control"] = "no-cache"
    return response


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