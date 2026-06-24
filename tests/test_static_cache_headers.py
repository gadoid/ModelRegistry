"""Bug 3 修复测试: ``/static/*`` 必须发 ``Cache-Control`` 头。

背景:
- FastAPI ``StaticFiles`` 默认不发 ``cache-control`` 头, 浏览器会按启发式缓存
  (通常缓存 (now - last_modified) 的 10%)。
- 在 dev server 上这会导致: 改完 ``app.js`` / ``style.css`` 后, 浏览器仍加载缓存
  的旧版本, 用户看到的是过期行为 (例如点击 新增 step 无响应)。
- 修复: 给所有 ``/static/*`` 响应加 ``Cache-Control: no-cache``, 让浏览器每次
  都要走 ETag 协商, 保证拿到的永远是最新的。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from gimbal.prism.server import app


def test_static_app_js_has_cache_control_header():
    """/static/app.js 响应必须含 Cache-Control 头 (防 dev 缓存陷阱)。"""
    with TestClient(app) as client:
        r = client.get("/static/app.js")
    assert r.status_code == 200
    cc = r.headers.get("cache-control")
    assert cc is not None, (
        "FastAPI StaticFiles 默认不发 cache-control, "
        "dev server 上浏览器会缓存旧 app.js, 导致修复不生效"
    )
    # 必须 no-cache 或 no-store —— 都强制浏览器 revalidate
    assert "no-cache" in cc.lower() or "no-store" in cc.lower(), \
        f"cache-control 应含 no-cache/no-store, 实际: {cc}"


def test_static_style_css_has_cache_control_header():
    """/static/style.css 也必须含 Cache-Control 头。"""
    with TestClient(app) as client:
        r = client.get("/static/style.css")
    assert r.status_code == 200
    cc = r.headers.get("cache-control")
    assert cc is not None, "/static/style.css 缺 cache-control 头"
    assert "no-cache" in cc.lower() or "no-store" in cc.lower(), \
        f"cache-control 应含 no-cache/no-store, 实际: {cc}"


def test_static_index_html_has_cache_control_header():
    """/ 不归 StaticFiles 管 (走 HTMLResponse 路由), 但同样应当 no-cache 防 dev 缓存。"""
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    # index.html 是 HTML 页面, 至少应发 no-cache 让 dev 时改完立即见效
    cc = r.headers.get("cache-control")
    assert cc is not None, "/ 应发 cache-control 头 (index.html 在 dev 期常改)"
    assert "no-cache" in cc.lower() or "no-store" in cc.lower(), \
        f"index.html cache-control 应含 no-cache/no-store, 实际: {cc}"
