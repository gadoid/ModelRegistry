"""Bug 2 修复测试: ``_pullCaptures`` 与 clear-captures 处理器调用 ``/api/captures`` 时
必须带 ``?sid=`` query 参数,否则 server 端 422 (sid 是必填)。

背景:
- ``gimbal/prism/server.py:258-265`` 的 ``/api/captures`` 用 ``sid: str = Query(...)`` 声明为必填。
- ``gimbal/prism/static/app.js:1234`` 的 ``_pullCaptures()`` 之前漏传,导致 ndjson 导入链路里
  ``state.captures`` 始终是空数组, ``_mergeCapturesIntoSteps`` 不添加任何 step。
- 同样问题在 ``gimbal/prism/static/app.js:1478`` 的 clear-captures 处理器里。
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    assert APP_JS.exists(), f"app.js 不存在: {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


def _extract_function_body(text: str, fname: str) -> str:
    m = re.search(
        rf"function\s+{re.escape(fname)}\s*\([^)]*\)\s*\{{(.*?)\n\}}",
        text,
        re.DOTALL,
    )
    assert m, f"未找到 {fname} 函数体"
    return m.group(1)


def test_pull_captures_function_declared():
    text = _read()
    assert re.search(r"function\s+_pullCaptures\s*\(\s*\)\s*\{", text), \
        "未找到 _pullCaptures 函数声明"


def test_pull_captures_fetch_url_contains_sid_query():
    """``_pullCaptures`` 内的 fetch 调用必须带 ``?sid=`` (或模板字面量注入 sid)。"""
    text = _read()
    body = _extract_function_body(text, "_pullCaptures")
    # 必须含 fetch('/api/captures' or "/api/captures" or `...captures...
    assert "fetch" in body, "_pullCaptures 必须调 fetch"
    # 找 /api/captures 这一行 (GET) 的 fetch 调用
    # 必须出现 sid query
    assert re.search(r"/api/captures\?[^`'\"\)]*sid=", body), (
        "_pullCaptures 内 /api/captures 的 fetch URL 必须带 ?sid= query 参数 "
        "(server 端 Query(...) 是必填,否则 422)"
    )


def test_pull_captures_uses_state_session_id():
    """URL 中 sid 应来自 state.sessionId, 而不是硬编码 'default'。"""
    text = _read()
    body = _extract_function_body(text, "_pullCaptures")
    # 允许两种: 模板字面量 ${state.sessionId ...} 或字符串拼接
    assert re.search(
        r"sid\s*=\s*\$\{[^}]*state\.sessionId",
        body,
    ) or "state.sessionId" in body, (
        "应使用 state.sessionId 编码到 sid,避免硬编码 'default'"
    )


def test_clear_captures_fetch_url_contains_sid_query():
    """``$('clear-captures')`` click handler 内的 ``fetch('/api/captures', {method:'DELETE'})`` 必须带 sid。"""
    text = _read()
    # 找 'clear-captures' 监听器块
    # 模式: const handler = $('clear-captures').addEventListener('click', async (...) => { ... });
    # 用一个比较宽的窗口: 找 'clear-captures' 之后到下一个 const/_$* 之间的区域
    idx = text.find("'clear-captures'")
    assert idx > 0, "未找到 'clear-captures' 引用"
    # 取后续 2000 字符作为 handler 范围 (粗略)
    snippet = text[idx: idx + 2000]
    # 必有 DELETE 调 /api/captures
    assert re.search(
        r"fetch\(\s*['\"`]/api/captures\?[^`'\"\)]*sid=",
        snippet,
    ) or re.search(
        r"fetch\(\s*`/api/captures\?sid=",
        snippet,
    ), (
        "clear-captures 处理器内 /api/captures 的 DELETE 必须带 ?sid= query "
        "(修复 422 → 真正清空 captures)"
    )


def test_pull_captures_sid_uses_fallback_default():
    """sid 编码应允许 fallback 到 'default' (与 inject 链路一致)。"""
    text = _read()
    body = _extract_function_body(text, "_pullCaptures")
    # 允许: encodeURIComponent(state.sessionId || 'default')
    # 允许: const sid = encodeURIComponent(state.sessionId || 'default');
    assert "'default'" in body or '"default"' in body, (
        "_pullCaptures sid 编码应包含 'default' fallback, 避免 state.sessionId 为空时 NaN/undefined"
    )
