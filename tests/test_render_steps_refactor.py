"""renderSteps 重构测试: 验证新子渲染器被声明, 旧 renderSteps 仍存在并调用它们。"""
from __future__ import annotations

from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_subrenderers_declared():
    text = _read()
    for fn in ["renderStepSidebar", "renderStepTags", "renderStepDetail", "renderSteps",
               "_renderStepCardBody", "attachStepCardEvents", "_syncStepPagination",
               "_computePageRanges"]:
        m = __import__("re").search(rf"function\s+{fn}\s*\(", text)
        assert m, f"未找到函数: {fn}"


def test_render_steps_orchestrator():
    """renderSteps 必须依次调用 4 个子函数。"""
    text = _read()
    m = __import__("re").search(
        r"function\s+renderSteps\s*\(\s*\)\s*\{(.*?)\n\}", text, __import__("re").DOTALL
    )
    assert m, "renderSteps 函数体未找到"
    body = m.group(1)
    assert "_syncStepPagination()" in body
    assert "renderStepSidebar()" in body
    assert "renderStepTags()" in body
    assert "renderStepDetail()" in body
    assert "syncStepEmpty()" in body


def test_attach_step_card_events_uses_correct_sid_for_delete():
    """删除事件必须用传入的 globalIdx 计算 UI 编号, 且清空 expandedStepSid。"""
    text = _read()
    assert "state.expandedStepSid === s.__sid" in text, \
        "删除 step 后未清空 state.expandedStepSid"
