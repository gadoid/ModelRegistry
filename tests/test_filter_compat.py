"""gimbal.capture — v0 PathFilter 兼容层回归保护。

覆盖 (spec §7.4 回归保护):
  - 旧 --filter CSV 行为不变
  - 旧 PathFilter 类的边界行为 (前缀 / 空 / 错配)
  - filter.py 仍然可独立 import
"""
from __future__ import annotations

from gimbal.capture.filter import PathFilter
from gimbal.capture.loader import build_matcher
from gimbal.capture.strategy import FilterMode


def test_csv_default_behavior_unchanged():
    """现有 --filter /api/ 行为必须保持。

    注意: v0 PathFilter 行为是 startswith(p + "/"), 所以
    `--filter /api/` 也会匹配 `/api/orderlist` (因为它以 "/api/" 开头)。
    这与 spec §7.2 test_path_prefix_no_false_match (prefix="/api/order") 行为不同。
    """
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="/api/", cli_mode=FilterMode.INCLUDE)
    assert m.match({"path": "/api/order"})
    assert m.match({"path": "/api/order/123"})
    assert m.match({"path": "/api/orderlist"})  # v0 行为: startswith 包含
    assert not m.match({"path": "/static/foo"})
    assert not m.match({"path": "/apicake"})  # 不会误匹配
    assert not m.match({"path": "/other"})


def test_empty_csv_no_file_records_all():
    """v0 行为: --filter '' + 无文件 → 全记录 (PathFilter([]) 兜底)。"""
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="", cli_mode=FilterMode.INCLUDE)
    assert m.match({"path": "/anything"})
    assert m.match({"path": "/api/order"})
    assert m.match({"path": "/static/foo"})


def test_pathfilter_prefix_match():
    pf = PathFilter(["/api/order"])
    assert pf.match("/api/order")
    assert pf.match("/api/order/123")
    assert not pf.match("/api/orderlist")


def test_pathfilter_empty_matches_all():
    pf = PathFilter([])
    assert pf.match("/anything")
    assert pf.match("/static/x")
    assert bool(pf) is False


def test_pathfilter_from_csv():
    pf = PathFilter.from_csv("/a, /b,/c")
    assert pf.match("/a")
    assert pf.match("/b")
    assert pf.match("/c/x")
    assert not pf.match("/d")


def test_pathfilter_trailing_slash_stripped():
    pf = PathFilter.from_csv("/api/,/user/")
    assert pf.match("/api/order")
    assert pf.match("/user/1")


def test_pathfilter_dedup():
    pf = PathFilter.from_csv("/a,/a,/a")
    assert len(pf.prefixes) == 1
