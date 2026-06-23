"""Step 分页原语静态测试: 验证 _syncStepPagination / _computePageRanges / PAGE_SIZE
在 app.js 中被正确声明, 且符合预期签名。

不依赖浏览器, 仅做文件读取 + 正则匹配。
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    assert APP_JS.exists(), f"app.js 不存在: {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


def test_page_size_constant_declared():
    """PAGE_SIZE = 10 必须存在, 在 app.js 顶部声明。"""
    text = _read()
    m = re.search(r"const\s+PAGE_SIZE\s*=\s*(\d+)\s*;", text)
    assert m, "未找到 `const PAGE_SIZE = N;` 声明"
    assert int(m.group(1)) == 10, f"PAGE_SIZE 必须是 10, 实际 {m.group(1)}"


def test_state_has_current_page():
    text = _read()
    assert re.search(r"currentPage\s*:\s*1", text), "state.currentPage 初始值缺失或不是 1"


def test_state_has_expanded_step_sid():
    text = _read()
    assert re.search(r"expandedStepSid\s*:\s*null", text), "state.expandedStepSid 初始值缺失或不是 null"


def test_sync_step_pagination_declared():
    text = _read()
    m = re.search(r"function\s+_syncStepPagination\s*\(\s*\)\s*\{", text)
    assert m, "未找到 _syncStepPagination 函数声明"


def test_sync_step_pagination_corrects_current_page():
    """函数体必须含 `state.currentPage = pageCount` 修正逻辑。"""
    text = _read()
    m = re.search(
        r"function\s+_syncStepPagination\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m, "未匹配到 _syncStepPagination 函数体"
    body = m.group(1)
    assert "state.currentPage" in body, "函数体未引用 state.currentPage"
    assert "pageCount" in body, "函数体未计算 pageCount"


def test_sync_step_pagination_clears_orphaned_sid():
    text = _read()
    m = re.search(
        r"function\s+_syncStepPagination\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "state.expandedStepSid" in body, "函数体未处理 expandedStepSid 失效"
    assert "state.steps.some" in body, "函数体未检查 sid 是否仍存在"


def test_compute_page_ranges_declared():
    text = _read()
    m = re.search(r"function\s+_computePageRanges\s*\(\s*\)\s*\{", text)
    assert m, "未找到 _computePageRanges 函数声明"


def test_compute_page_ranges_returns_labeled_ranges():
    text = _read()
    m = re.search(
        r"function\s+_computePageRanges\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "label" in body, "函数体未生成 label 字段"
    assert "start" in body and "end" in body, "函数体未生成 start/end 字段"
    assert "PAGE_SIZE" in body, "函数体未引用 PAGE_SIZE"
