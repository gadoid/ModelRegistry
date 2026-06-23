"""gimbal.capture.strategy — CompiledMatcher 匹配语义。

覆盖 (spec §7.2 test_strategy_compile):
  - path_prefix 不误匹配 (锁住 v0 PathFilter 行为)
  - glob ** 递归匹配
  - rule 内 AND (host + path + method)
  - rule 间 OR
  - EXCLUDE mode
  - match_with_reason
  - default_mode 控制无 rule 命中时的方向
"""
from __future__ import annotations

import re

import pytest

from gimbal.capture.strategy import (
    CompiledMatcher,
    CompiledRule,
    FilterMode,
    Profile,
    Rule,
    StrategyFile,
)


def _ev(path="/x", host="x.com", method="GET"):
    return {"path": path, "host": host, "method": method}


def test_path_prefix_no_false_match():
    """锁住现有 PathFilter 行为: /api/order 不匹配 /api/orderlist。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix="/api/order",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(path="/api/order"))
    assert m.match(_ev(path="/api/order/123"))
    assert not m.match(_ev(path="/api/orderlist"))


def test_path_prefix_exact_match_only():
    """前缀匹配的精确边界: /api 不应匹配 /apicake。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix="/api",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(path="/api"))
    assert m.match(_ev(path="/api/x"))
    assert not m.match(_ev(path="/apicake"))


def test_glob_double_star_recursive():
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix=None,
            path_re=re.compile(r".*?/api/.*"),  # fnmatch '/api/**'
            methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(path="/api/order/123/sub"))
    assert not m.match(_ev(path="/other/api"))


def test_and_within_rule():
    """rule 内 host + path + method 全部满足才命中。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE,
            host=re.compile(r"api\.x\.com"),
            path_prefix="/api/order",
            path_re=None,
            methods=frozenset(["POST"]),
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(host="api.x.com", path="/api/order", method="POST"))
    assert not m.match(_ev(host="api.x.com", path="/api/order", method="GET"))
    assert not m.match(_ev(host="other.com", path="/api/order", method="POST"))


def test_or_between_rules():
    m = CompiledMatcher(
        [
            CompiledRule(mode=FilterMode.INCLUDE, host=None,
                         path_prefix="/a", path_re=None, methods=None),
            CompiledRule(mode=FilterMode.INCLUDE, host=None,
                         path_prefix="/b", path_re=None, methods=None),
        ],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(path="/a/x"))
    assert m.match(_ev(path="/b/x"))
    assert not m.match(_ev(path="/c"))


def test_exclude_mode_in_rule():
    """rule.mode=EXCLUDE 命中 → False。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.EXCLUDE, host=None, path_prefix="/api/auth",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.INCLUDE,
    )
    assert not m.match(_ev(path="/api/auth/login"))
    assert m.match(_ev(path="/api/order"))


def test_methods_case_insensitive_match():
    """event 端 method 会被归一大写后比对。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix=None,
            path_re=None, methods=frozenset(["GET", "POST"]),
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(method="get"))
    assert m.match(_ev(method="Post"))
    assert not m.match(_ev(method="DELETE"))


def test_default_mode_include_white_list():
    """default_mode=EXCLUDE: 无 rule 命中时不录 (白名单)。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix="/api",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(path="/api/x"))
    assert not m.match(_ev(path="/other"))


def test_default_mode_exclude_black_list():
    """default_mode=INCLUDE: 无 rule 命中时录 (黑名单 / 兜底)。"""
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.EXCLUDE, host=None, path_prefix="/api/auth",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.INCLUDE,
    )
    assert not m.match(_ev(path="/api/auth/login"))
    assert m.match(_ev(path="/api/order"))


def test_match_with_reason_includes():
    hit, reason = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix="/api",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    ).match_with_reason(_ev(path="/api/x"))
    assert hit and "rule #1" in reason


def test_match_with_reason_excludes():
    hit, reason = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.EXCLUDE, host=None, path_prefix="/api/auth",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.INCLUDE,
    ).match_with_reason(_ev(path="/api/auth/login"))
    assert not hit and "rule #1" in reason


def test_match_with_reason_no_match():
    hit, reason = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE, host=None, path_prefix="/api",
            path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    ).match_with_reason(_ev(path="/other"))
    assert not hit
    assert reason is None


def test_empty_matcher_default_include_returns_true():
    """空 rules + default=INCLUDE → 所有 event 都录 (sentinel 等价)。"""
    m = CompiledMatcher([], default_mode=FilterMode.INCLUDE)
    assert m.match(_ev(path="/anything"))


def test_empty_matcher_default_exclude_returns_false():
    m = CompiledMatcher([], default_mode=FilterMode.EXCLUDE)
    assert not m.match(_ev(path="/anything"))


def test_host_regex_match():
    m = CompiledMatcher(
        [CompiledRule(
            mode=FilterMode.INCLUDE,
            host=re.compile(r".*\.example\.com"),
            path_prefix=None, path_re=None, methods=None,
        )],
        default_mode=FilterMode.EXCLUDE,
    )
    assert m.match(_ev(host="api.example.com"))
    assert m.match(_ev(host="www.example.com"))
    assert not m.match(_ev(host="api.other.com"))
