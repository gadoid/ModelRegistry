"""v0.5.5 修复: #step-empty 触发文件选择器不能双触发。

Bug: #step-empty 同时挂了 2 套触发源:
  1) HTML 内联 onclick / onkeydown (index.html:290-291) → 调 `i.click()`
  2) JS addEventListener('click' / 'keydown') (app.js:1291-1298) → 调 triggerFilePicker()

用户在 #step-empty 上点击 (或按 Enter/Space), 两套 handler 都会跑,
导致 <input type="file">.click() 被调 2 次, 原生文件选择器弹出 2 次,
用户不得不选两次文件 (这就是用户报的"上传文件两次")。

修复方向: JS addEventListener 是 v0.5.5 新加的可访问性友好实现
(用 preventDefault + ARIA role/tabindex/aria-label), HTML 内联 handler
是旧实现残留, 删 inline, 保留 JS。
"""
from __future__ import annotations

import re
from pathlib import Path

INDEX_HTML = Path("D:/M/ModelRegistry/gimbal/prism/static/index.html")
APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step_empty_block(text: str) -> str:
    """提取 index.html 里 #step-empty 那一行 div 块。"""
    m = re.search(
        r'<div\s+id="step-empty"[^>]*>(.*?)</div>',
        text,
        re.DOTALL,
    )
    assert m, "未找到 #step-empty 元素"
    return m.group(0)


# ─── 核心 bug: HTML 内联 onclick / onkeydown 必须删 ──────────────────────


def test_step_empty_has_no_inline_onclick():
    """#1 — #step-empty 不应有 inline onclick。inline onclick 与 JS addEventListener
    双触发会让原生文件选择器弹 2 次。"""
    block = _step_empty_block(_read(INDEX_HTML))
    assert "onclick=" not in block, (
        "#step-empty 仍带 inline onclick, 与 app.js 的 click listener 双触发; "
        "用户点击一次会让 ndjson-file-input.click() 跑两次, 文件选择器弹两次"
    )


def test_step_empty_has_no_inline_onkeydown():
    """#2 — #step-empty 不应有 inline onkeydown。Enter/Space 双触发同理。"""
    block = _step_empty_block(_read(INDEX_HTML))
    assert "onkeydown=" not in block, (
        "#step-empty 仍带 inline onkeydown, 与 app.js 的 keydown listener 双触发; "
        "用户按 Enter/Space 会让 ndjson-file-input.click() 跑两次, 文件选择器弹两次"
    )


# ─── 回归: JS 端不能因此被删, 可访问性路径必须保留 ─────────────────────


def test_js_step_empty_click_listener_still_present():
    """#3 — app.js 的 click listener 必须仍在 (修复删 HTML, 不能把 JS 也删了)。
    这是 v0.5.5 新加的可访问性友好实现, 取代 inline onclick。"""
    text = _read(APP_JS)
    assert "_stepEmpty.addEventListener('click'" in text, (
        "app.js 缺失 _stepEmpty.addEventListener('click', triggerFilePicker); "
        "若删了 HTML inline onclick 但保留 JS listener 缺失, 点击 #step-empty 会无响应"
    )


def test_js_step_empty_keydown_listener_still_present():
    """#4 — app.js 的 keydown listener 必须仍在 (修复删 HTML, 不能把 JS 也删了)。"""
    text = _read(APP_JS)
    assert "_stepEmpty.addEventListener('keydown'" in text, (
        "app.js 缺失 _stepEmpty.addEventListener('keydown', ...); "
        "若删了 HTML inline onkeydown 但 JS listener 缺失, 按 Enter/Space 无响应"
    )


def test_step_empty_a11y_attributes_kept():
    """#5 — 修复删 inline handler 不能误删 a11y 属性 (role/tabindex/aria-label)。
    这些是 #step-empty 充当按钮的语义凭证, JS 监听依赖它们。"""
    block = _step_empty_block(_read(INDEX_HTML))
    assert 'role="button"' in block, "#step-empty 缺 role=\"button\""
    assert 'tabindex="0"' in block, "#step-empty 缺 tabindex=\"0\""
    assert 'aria-label=' in block, "#step-empty 缺 aria-label"