"""Tag 删除 + 拖拽静态测试。"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_tag_delete_handler_exists():
    text = _read()
    assert "querySelectorAll('.step-tag .del')" in text, "未找到 tag 删除按钮事件绑定"
    assert "confirmModal('删除 Step'" in text, "未走 confirmModal"


def test_drag_reorder_handler_exists():
    text = _read()
    for evt in ["'dragstart'", "'dragover'", "'drop'", "'dragend'", "'dragleave'"]:
        assert evt in text, f"未找到拖拽事件: {evt}"
    assert "_dragFromIdx" in text, "未使用 _dragFromIdx 状态"
    assert "state.steps.splice" in text, "未调用 splice 重排"
    # 跨页守卫
    assert "range.start" in text and "range.end" in text, "未做跨页拖拽守卫"
