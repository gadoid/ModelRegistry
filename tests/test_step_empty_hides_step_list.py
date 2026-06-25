"""Bug 1 修复测试: ``syncStepEmpty`` 必须同时控制 #step-list 的 hidden。

背景: ``#step-empty`` 由 syncStepEmpty() 控制显示;但当 state.steps.length===0 时,
整个 #step-list (含 step-sidebar 96px 空栏) 也应该被隐藏,而不是留个空 grid 露馅。
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    assert APP_JS.exists(), f"app.js 不存在: {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


def test_sync_step_empty_function_declared():
    text = _read()
    m = re.search(r"function\s+syncStepEmpty\s*\(\s*\)\s*\{", text)
    assert m, "未找到 syncStepEmpty 函数声明"


def test_sync_step_empty_hides_step_list():
    """syncStepEmpty 函数体内必须引用 'step-list' (联动隐藏整列)。"""
    text = _read()
    m = re.search(
        r"function\s+syncStepEmpty\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m, "未匹配到 syncStepEmpty 函数体"
    body = m.group(1)
    assert "step-list" in body, (
        "syncStepEmpty 必须联动控制 #step-list 的 hidden 属性; "
        "否则空 step 时会出现 96px 空白侧栏"
    )
    # 必须设置 hidden 属性 (而不是 display: none 之类的旁路)
    assert re.search(r"\$?\(['\"]step-list['\"]\)?\.hidden\s*=", body), (
        "syncStepEmpty 必须对 step-list 设置 .hidden 属性"
    )


def test_sync_step_empty_inverts_step_empty_state():
    """step-list 的 hidden 状态必须与 step-empty 相反(空 step 时 list 藏,empty 显)。"""
    text = _read()
    m = re.search(
        r"function\s+syncStepEmpty\s*\(\s*\)\s*\{(.*?)\n\}",
        text, re.DOTALL,
    )
    assert m
    body = m.group(1)
    # 提取两行 hidden 赋值
    list_match = re.search(r"step-list['\"]\)?\.hidden\s*=\s*([^;]+);", body)
    empty_match = re.search(r"step-empty['\"]\)?\.hidden\s*=\s*([^;]+);", body)
    assert list_match and empty_match, "必须同时给 step-list 和 step-empty 赋值 .hidden"
    list_expr = list_match.group(1).strip()
    empty_expr = empty_match.group(1).strip()
    # 关键: 两边的 boolean 表达式必须语义相反 (一个非空即 list 显、empty 藏)
    # 允许中间变量 (hasSteps / hasStep / notEmpty / etc.) —— 不限制实现形式
    # 1) 表达式文本必须不同 (不允许两边写一样)
    assert list_expr != empty_expr, (
        f"step-list 和 step-empty 的 hidden 表达式必须相反, 实际两边都是: {list_expr}"
    )
    # 2) 至少一边要能"看出" 跟 state.steps.length 有关 (避免被误改成两个常量)
    assert "state.steps" in body, (
        "syncStepEmpty 必须基于 state.steps 判断, 不应硬编码 true/false"
    )
    # 3) 至少一边要含 state.steps.length 比较运算符
    assert "length" in body and (">" in body or "===" in body or "!" in body), (
        "syncStepEmpty 必须用 state.steps.length 做空/非空判断"
    )


def test_init_renders_step_empty_state_when_no_draft():
    """当 server 没有 draft 时, init 也必须触发一次 step 渲染 (空 step 也要 hide list)。

    Bug 复现: loadDraft 早期 return (无 draft) → 不调 renderAll → syncStepEmpty 没跑 →
    step-list.hidden 保持 HTML 初始值 false → 空 step 时还会看到 96px 空栏。
    """
    text = _read()
    # init 是 IIFE: (async function init() { ... })();
    m = re.search(
        r"\(\s*async\s+function\s+init\s*\(\s*\)\s*\{(.*?)\}\s*\)\s*\(\s*\)\s*;",
        text,
        re.DOTALL,
    )
    assert m, "未找到 init() IIFE"
    body = m.group(1)
    # init 必须在 loadDraft 之后调一次 renderAll/renderSteps (确保 step-list 隐藏联动生效)
    after_load_draft = body.split("await loadDraft()", 1)
    assert len(after_load_draft) == 2, "init 内必须有 await loadDraft()"
    tail = after_load_draft[1]
    assert re.search(r"\brenderAll\s*\(\s*\)", tail) or re.search(r"\brenderSteps\s*\(\s*\)", tail), (
        "init() 在 loadDraft 之后必须再调一次 renderAll() 或 renderSteps(), "
        "否则 loadDraft 早返时 syncStepEmpty 永远不被触发,空 step 时 step-list 不会藏"
    )
