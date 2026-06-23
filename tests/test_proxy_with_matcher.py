"""gimbal.capture.proxy — CaptureAddon + CompiledMatcher 集成。

覆盖 (spec §7.2 test_proxy_with_matcher):
  - 匹配 event → 写 bus + 自增 count
  - 不匹配 event → 不写
  - response=None 跳过
  - query string 剥离
  - EXCLUDE rule 命中 → 不录
  - 白名单 (default=EXCLUDE) 不在白名单的路径不录
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gimbal.capture.bus import FileBus
from gimbal.capture.proxy import CaptureAddon
from gimbal.capture.strategy import (
    CompiledMatcher,
    CompiledRule,
    FilterMode,
)


def _make_addon(suffix: str, matcher: CompiledMatcher):
    bus = FileBus(Path(tempfile.mkdtemp()), suffix)
    return bus, CaptureAddon(bus, matcher)


def _flow(path: str, host: str = "x.com", method: str = "GET",
          response_is_none: bool = False):
    flow = MagicMock()
    if response_is_none:
        flow.response = None
        return flow
    flow.response = MagicMock()
    flow.response.status_code = 200
    flow.response.headers = {}
    flow.request.method = method
    flow.request.scheme = "https"
    flow.request.host = host
    flow.request.port = 443
    flow.request.path = path
    flow.request.query = {}
    flow.request.headers = {}
    flow.request.get_text.return_value = ""
    flow.response.get_text.return_value = ""
    return flow


def test_response_matches_writes_and_increments():
    bus, addon = _make_addon("t1", CompiledMatcher(
        [CompiledRule(mode=FilterMode.INCLUDE, host=None,
                      path_prefix="/api", path_re=None, methods=None)],
        default_mode=FilterMode.EXCLUDE,
    ))
    addon.response(_flow("/api/order/123", host="api.example.com"))
    assert addon.count == 1
    bus.close()


def test_response_no_match_skipped():
    bus, addon = _make_addon("t2", CompiledMatcher(
        [CompiledRule(mode=FilterMode.INCLUDE, host=None,
                      path_prefix="/api", path_re=None, methods=None)],
        default_mode=FilterMode.EXCLUDE,
    ))
    addon.response(_flow("/static/x.css", host="static.example.com"))
    assert addon.count == 0
    bus.close()


def test_response_none_skipped():
    bus, addon = _make_addon("t3", CompiledMatcher(
        [CompiledRule(mode=FilterMode.INCLUDE, host=None,
                      path_prefix=None, path_re=None, methods=None)],
        default_mode=FilterMode.EXCLUDE,
    ))
    addon.response(_flow("/api/x", response_is_none=True))
    assert addon.count == 0
    bus.close()


def test_response_strips_query_string():
    bus, addon = _make_addon("t4", CompiledMatcher(
        [CompiledRule(mode=FilterMode.INCLUDE, host=None,
                      path_prefix="/api", path_re=None, methods=None)],
        default_mode=FilterMode.EXCLUDE,
    ))
    flow = _flow("/api/order?id=1&type=new")
    flow.request.query = {"id": "1", "type": "new"}
    addon.response(flow)
    assert addon.count == 1  # /api 匹配 (剥离 ? 后)
    bus.close()


def test_exclude_rule_hit_not_recorded():
    bus, addon = _make_addon("t5", CompiledMatcher(
        [CompiledRule(mode=FilterMode.EXCLUDE, host=None,
                      path_prefix="/api/auth", path_re=None, methods=None)],
        default_mode=FilterMode.INCLUDE,
    ))
    addon.response(_flow("/api/auth/login"))
    assert addon.count == 0
    addon.response(_flow("/api/order"))
    assert addon.count == 1  # 黑名单: 不在列表就录
    bus.close()


def test_and_within_rule_via_proxy():
    bus, addon = _make_addon("t6", CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE,
            host=__import__("re").compile(r"api\.x\.com"),
            path_prefix="/api/order",
            path_re=None,
            methods=frozenset(["POST"]),
        )],
        default_mode=FilterMode.EXCLUDE,
    ))
    addon.response(_flow("/api/order/1", host="api.x.com", method="POST"))
    assert addon.count == 1
    addon.response(_flow("/api/order/1", host="api.x.com", method="GET"))
    assert addon.count == 1  # GET 不满足 method, 不命中
    addon.response(_flow("/api/order/1", host="other.com", method="POST"))
    assert addon.count == 1  # host 不满足, 不命中
    bus.close()
