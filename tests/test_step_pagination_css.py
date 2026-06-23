"""Step 分页 CSS 静态测试: 验证新类在 style.css 中被定义, 且复用现有 CSS 变量。"""
from __future__ import annotations

from pathlib import Path

STYLE_CSS = Path("D:/M/ModelRegistry/gimbal/prism/static/style.css")


def _read() -> str:
    assert STYLE_CSS.exists(), f"style.css 不存在: {STYLE_CSS}"
    return STYLE_CSS.read_text(encoding="utf-8")


def test_required_classes_defined():
    text = _read()
    for cls in [".step-layout", ".step-sidebar", ".step-sidebar .page-tab",
                ".step-tags", ".step-tag", ".step-tag.active",
                ".step-tag.dragging", ".step-tag.drag-over",
                ".step-tag .del", ".step-detail", ".step-main",
                "#step-empty.clickable", "#step-empty.clickable:hover"]:
        assert cls in text, f"缺 CSS 规则: {cls}"


def test_reuses_existing_variables_only():
    """不允许引入新 CSS 变量 (--xxx:); 只许读 var(--xxx)。"""
    text = _read()
    # 找新增区块 (从 v0.5.5 marker 之后)
    marker_idx = text.find("Step Pagination v0.5.5")
    assert marker_idx > 0, "未找到 v0.5.5 CSS 块 marker"
    new_block = text[marker_idx:]
    # 不允许定义新变量
    import re
    new_vars = re.findall(r"--[\w-]+\s*:", new_block)
    assert not new_vars, f"v0.5.5 块不应定义新变量: {new_vars}"


def test_grid_columns_for_sidebar():
    text = _read()
    m_idx = text.find("Step Pagination v0.5.5")
    new_block = text[m_idx:]
    assert "grid-template-columns: 96px 1fr" in new_block, \
        ".step-layout 必须用 96px 1fr 网格"


def test_sticky_sidebar():
    text = _read()
    m_idx = text.find("Step Pagination v0.5.5")
    new_block = text[m_idx:]
    assert "position: sticky" in new_block, "侧栏必须 sticky"
    assert "max-height: calc(100vh - 220px)" in new_block, \
        "侧栏必须限制最大高度并可滚动"
