"""v0.5.x 修复: #clear-captures 必须也清空已加载的 step 内容。

Bug: 当前 #clear-captures handler 在以下两种场景下不清 state.steps:
  1) early return `if (!state.captures.length) return;` —
     用户加载了带 step 的 draft 但内存无 capture 时, 点击清空完全没反应
  2) handler 体只动 state.captures, 不动 state.steps / expandedStepSid /
     renderSteps() / scheduleSave() / pushHistory()

期望: #clear-captures 是一站式"重置本 session 数据"按钮, 同时清:
  - state.captures (已有)
  - state.steps (新增, 修 bug)
  - state.expandedStepSid (UI 派生)
  - undo / redo 栈 (可恢复, 与 switchSession 对齐)
  - persist 到 server (scheduleSave)
  - 触发 renderSteps() 同步 DOM
  - pushHistory() 让 undo 能恢复

Why: `state.steps` 是 step 数据的 SSOT (见 [[gimbal-prism-frontend-state]]);
     仅清 captures 不动 steps 的话, 步骤 tab 仍显示旧数据, reload 后旧 draft
     还在 server (因没 saveDraft), 用户以为"清空"成功但其实没生效。
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _extract_handler_body(text: str) -> str:
    """提取 $('clear-captures').addEventListener('click', async () => { ... }); 的函数体。"""
    # 匹配: $('clear-captures').addEventListener('click', async () => { ... });
    m = re.search(
        r"\$\(['\"]clear-captures['\"]\)\.addEventListener\(['\"]click['\"],\s*async\s*\(\)\s*=>\s*\{(.*?)^\}\);",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "未找到 #clear-captures click handler"
    return m.group(1)


# ─── 核心 bug: handler 必须清 state.steps ─────────────────────────────────


def test_clear_handler_resets_state_steps():
    """#1 — handler 必须执行 state.steps = [] (或等价的 length 归零)。"""
    body = _extract_handler_body(_read())
    assert re.search(r"state\.steps\s*=\s*\[\s*\]", body), (
        "clear-captures handler 未清 state.steps, "
        "导致已加载的 step 仍在 UI 显示 (Bug 报告: '清空 未能清空 加载的step内容')"
    )


def test_clear_handler_resets_expanded_step_sid():
    """#2 — handler 必须清 state.expandedStepSid, 否则残留展开态。"""
    body = _extract_handler_body(_read())
    assert re.search(r"state\.expandedStepSid\s*=\s*null", body), (
        "clear-captures handler 未重置 state.expandedStepSid, "
        "下次 loadDraft 时可能引用已删 step 的 __sid"
    )


def test_clear_handler_invokes_render_steps():
    """#3 — handler 必须调 renderSteps() 同步 DOM (state 改了 UI 没刷 = 视觉残留)。"""
    body = _extract_handler_body(_read())
    assert "renderSteps()" in body, (
        "clear-captures handler 未调 renderSteps(), "
        "即使 state.steps 清空, Steps tab 仍显示旧 step 卡片"
    )


def test_clear_handler_persists_to_server():
    """#4 — handler 必须调 scheduleSave() (或 saveDraft()), 否则 reload 会把 step 灌回来。"""
    body = _extract_handler_body(_read())
    assert "scheduleSave" in body or "saveDraft" in body, (
        "clear-captures handler 未触发 server 持久化, "
        "server 端 draft.steps 仍是旧值, 下次 loadDraft 重新灌回"
    )


def test_clear_handler_pushes_history():
    """#5 — handler 应 pushHistory() 以便用户误清后能用 Ctrl+Z 撤销。"""
    body = _extract_handler_body(_read())
    assert "pushHistory" in body, (
        "clear-captures handler 未 pushHistory(), "
        "误清空后 Ctrl+Z 无法恢复, 与 v0.5 撤销栈契约不符"
    )


# ─── early return 守卫: 不应再以 captures 长度为唯一条件 ─────────────────


def test_clear_handler_no_early_return_on_empty_captures():
    """#6 — handler 不应以 `if (!state.captures.length) return;` 早返。
    该守卫会让"加载了 draft 但无 capture"的场景下清空按钮完全无响应。"""
    body = _extract_handler_body(_read())
    assert "if (!state.captures.length) return" not in body, (
        "clear-captures handler 仍有 `if (!state.captures.length) return` 早返守卫, "
        "会导致 state.steps 非空但 state.captures 为空时, 清空按钮完全无响应"
    )


# ─── 文案契约: 确认/Toast 必须反映新行为 ────────────────────────────────


def test_confirm_message_no_longer_says_steps_wont_be_deleted():
    """#7 — confirm 文案不应再承诺 "steps 不会被删除", 行为已变。"""
    text = _read()
    # 找到调用 confirmModal 的位置, 限定在 clear-captures handler 附近
    m = re.search(
        r"\$\(['\"]clear-captures['\"]\)\.addEventListener\(['\"]click['\"].*?confirmModal\((.*?)\{",
        text,
        re.DOTALL,
    )
    assert m, "未找到 clear-captures 内的 confirmModal 调用"
    call_args = m.group(1)
    assert "steps 不会被删除" not in call_args, (
        "confirm 文案仍说 'steps 不会被删除', 但行为已变, 文案与实际不符会误导用户"
    )
