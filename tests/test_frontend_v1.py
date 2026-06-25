"""gimbal.prism.static — 前端 v1.0.0 (PR1SM 视觉规范) 测试。

v0.5 改造: 用 D:\\PR1SM 的前端三件套 (style.css / index.html / app.js) 替换旧的
声明式渲染前端。本测试锁住新前端的关键属性:
  - 4 tab (元信息 / 配置 / 资源 / Steps) 仍存在
  - 关键 DOM 元素 ID 存在 (header-sid, tab-0..3, m-name, yaml-modal 等)
  - app.js 调对端点 (REST 6 个 + WebSocket 1 个)
  - 风格文件含设计 tokens (--accent, --color-*)
  - 仍走 EventSource 替代品 (WebSocket) + 无残留 SSE
"""
from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path("D:/M/ModelRegistry/gimbal/prism/static")
APP_JS = STATIC_DIR / "app.js"
INDEX_HTML = STATIC_DIR / "index.html"
STYLE_CSS = STATIC_DIR / "style.css"


def _read(path: Path) -> str:
    assert path.exists(), f"前端文件不存在: {path}"
    return path.read_text(encoding="utf-8")


# ─── 文件存在 + 体积合理 ──────────────────────────────────────────────────


def test_app_js_exists_and_size():
    assert APP_JS.exists()
    size = APP_JS.stat().st_size
    # PR1SM 完整版 ~62KB; 若 < 30KB 视为不完整
    assert size > 30000, f"app.js 太小 ({size} bytes)"


def test_index_html_exists_and_size():
    assert INDEX_HTML.exists()
    size = INDEX_HTML.stat().st_size
    assert size > 5000, f"index.html 太小 ({size} bytes)"


def test_style_css_exists_and_size():
    assert STYLE_CSS.exists()
    size = STYLE_CSS.stat().st_size
    assert size > 10000, f"style.css 太小 ({size} bytes)"


# ─── index.html 结构 ──────────────────────────────────────────────────────


def test_index_html_title_brands_gimbal():
    text = _read(INDEX_HTML)
    assert "<title>gimbal prism" in text, "title 应包含 'gimbal prism'"


def test_index_html_has_4_tabs():
    text = _read(INDEX_HTML)
    for i in range(4):
        assert f'id="tab-{i}"' in text, f"缺 tab-{i}"


def test_index_html_has_card_stack():
    text = _read(INDEX_HTML)
    assert 'id="card-stack"' in text
    # 4 个 page 段 (元信息 / 配置 / 资源 / Steps)
    assert text.count('class="page') >= 4


def test_index_html_key_modals():
    text = _read(INDEX_HTML)
    assert 'id="yaml-modal"' in text
    assert 'id="help-modal"' in text
    assert 'id="toast-host"' in text


def test_index_html_meta_fields():
    """元信息 tab 的关键字段 ID 存在。"""
    text = _read(INDEX_HTML)
    for fid in ["m-name", "m-desc", "m-module", "m-priority",
                "m-author", "m-owner", "m-version", "m-sid"]:
        assert f'id="{fid}"' in text, f"缺字段 #{fid}"


def test_index_html_resource_tiles():
    """资源 tab 的 4 种 kind tile 存在。"""
    text = _read(INDEX_HTML)
    for kind in ["db", "mock", "file", "variable"]:
        assert f'data-rkind="{kind}"' in text, f"缺 resource kind={kind}"


def test_index_html_step_toolbar():
    """Steps tab 工具栏 / 空状态 / 文件选择器 / 列表结构的 ID 存在。"""
    text = _read(INDEX_HTML)
    for bid in ["add-step", "ndjson-file-input", "step-sidebar",
                "step-tags", "step-detail", "step-empty"]:
        assert f'id="{bid}"' in text, f"缺 step 元素 #{bid}"
    # 旧的 expand-all / collapse-all / import-row / import-btn / import-path 必须被删除
    for old in ["expand-all", "collapse-all", "import-btn", "import-path"]:
        assert f'id="{old}"' not in text, f"应已删除 #{old}"
    # step-list 必须有 step-layout 类
    assert 'id="step-list" class="step-layout"' in text, "step-list 缺少 step-layout 类"
    # step-empty 必须可点击
    assert 'id="step-empty" class="empty-state clickable"' in text, \
        "step-empty 缺 clickable 类"


# ─── app.js 端点契约 ──────────────────────────────────────────────────────


def test_app_js_uses_websocket_not_eventsource():
    """v0.5 改用 WebSocket (替代 v0 SSE)。"""
    text = _read(APP_JS)
    assert "new WebSocket" in text
    assert "ws/captures" in text
    assert "new EventSource" not in text, "v0.5 不应残留 EventSource"


def test_app_js_calls_all_draft_endpoints():
    text = _read(APP_JS)
    # /api/draft/{sid} GET + PUT
    assert "/api/draft/" in text
    # /api/draft/{sid}/yaml POST
    assert "/yaml" in text
    # /api/draft/{sid}/export POST
    assert "/export" in text


def test_app_js_calls_capture_endpoints():
    text = _read(APP_JS)
    assert "/api/captures" in text
    assert "/api/captures/inject" in text
    # v0.5.5: /api/captures/import-from-path 前端调用方已删除 (spec §0 YAGNI).
    # 后端端点保留向后兼容, 仅 UI 不再调用。
    assert "/api/captures/import-from-path" not in text
    # DELETE method
    assert "method: 'DELETE'" in text or '"DELETE"' in text


def test_app_js_handles_hello_and_capture_message_types():
    """WS 消息格式: hello (历史灌入) + capture (增量推送)。"""
    text = _read(APP_JS)
    assert "type === 'hello'" in text or "type == 'hello'" in text
    assert "type === 'capture'" in text or "type == 'capture'" in text


def test_app_js_4_tabs_via_dom():
    """新前端 4 tab 通过 DOM (id=tab-0..3) 切换, 不用 TAB_MAP。"""
    js_text = _read(APP_JS)
    html_text = _read(INDEX_HTML)
    assert "switchTo" in js_text or "data-idx" in js_text
    # tab 标签在 HTML 里
    for kw in ["元信息", "配置", "资源", "Steps"]:
        assert kw in html_text, f"HTML tab 标签缺 '{kw}'"


def test_app_js_undo_redo():
    text = _read(APP_JS)
    assert "undoStack" in text or "undo" in text.lower()
    assert "redo" in text.lower()


# ─── style.css 设计系统 ──────────────────────────────────────────────────


def test_style_css_has_design_tokens():
    text = _read(STYLE_CSS)
    # CSS 变量 (设计 tokens)
    for token in ["--accent", "--color-background-primary",
                  "--color-text-primary", "--color-border-tertiary"]:
        assert token in text, f"缺设计 token {token}"


def test_style_css_has_key_components():
    text = _read(STYLE_CSS)
    for cls in [".field-row", ".fin", ".tog", ".tag-pill",
                ".kv-row", ".modal", ".toast", ".step-card",
                ".user-block", ".resource-tile"]:
        assert cls in text, f"style.css 缺 {cls}"


def test_style_css_responsive():
    text = _read(STYLE_CSS)
    assert "@media" in text
    assert "prefers-reduced-motion" in text


# ─── 端到端集成 (lifespan + WS) ─────────────────────────────────────────


def _all_route_paths(app) -> set[str]:
    """Flatten app.routes including APIRouter mounts (handles _IncludedRouter)."""
    paths: set[str] = set()
    for r in app.routes:
        if hasattr(r, "path") and r.path:
            paths.add(r.path)
        # APIRouter-mounted subapps: unwrap _IncludedRouter.original_router
        original = getattr(r, "original_router", None)
        if original is not None and hasattr(original, "routes"):
            for sub in original.routes:
                if hasattr(sub, "path") and sub.path:
                    paths.add(sub.path)
    return paths


def test_websocket_endpoint_exists():
    """WebSocket /ws/captures 已注册到 FastAPI app。"""
    from gimbal.prism.server import app
    paths = _all_route_paths(app)
    assert "/ws/captures" in paths, f"缺 /ws/captures, 现有路由: {sorted(paths)}"


def test_rest_endpoints_still_present():
    """REST 6 端点全部保留。"""
    from gimbal.prism.server import app
    paths = _all_route_paths(app)
    for path in [
        "/api/health",
        "/api/captures",
        "/api/captures/inject",
        "/api/captures/import-from-path",
        "/api/draft/{session_id}",
    ]:
        assert path in paths, f"缺 REST 端点 {path}"
