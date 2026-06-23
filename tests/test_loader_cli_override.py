"""gimbal.capture.loader — CLI --filter CSV 追加。

覆盖 (spec §7.2 test_loader_cli_override):
  - CSV 元素作为 Rule 追加
  - 空 CSV → 不追加
  - --filter-mode 决定 CLI rule 的 mode
  - 文件 rules + CLI rules 共存
  - 纯 CSV (无文件) → CSV 路径
  - 无文件 + 无 CSV → sentinel 全匹配 (v0 兜底)
"""
from __future__ import annotations

from gimbal.capture.loader import build_matcher
from gimbal.capture.strategy import FilterMode, Profile, Rule, StrategyFile


def test_csv_appended_as_include_rules():
    sf = StrategyFile(profiles={
        "p": Profile(rules=[Rule(path="/from_file")])
    })
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="/from_cli1,/from_cli2",
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert m.match({"path": "/from_file/x"})
    assert m.match({"path": "/from_cli1"})
    assert m.match({"path": "/from_cli2"})


def test_csv_appended_as_exclude_rules():
    sf = StrategyFile(profiles={
        "p": Profile(rules=[Rule(path="/from_file")])
    })
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="/exclude_me",
                      cli_mode=FilterMode.EXCLUDE, _strategy_file=sf)
    assert m.match({"path": "/from_file/x"})
    assert not m.match({"path": "/exclude_me"})


def test_empty_csv_not_appended():
    sf = StrategyFile(profiles={"p": Profile(rules=[Rule(path="/only")])})
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="", cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert len(m.rules) == 1
    assert m.match({"path": "/only/x"})


def test_csv_whitespace_stripped():
    sf = StrategyFile(profiles={"p": Profile(rules=[])})
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv=" /a , /b ,",  # 含空格 + 末尾空
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert m.match({"path": "/a/x"})
    assert m.match({"path": "/b/x"})


def test_pure_csv_no_file_include():
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="/api/,/user", cli_mode=FilterMode.INCLUDE)
    assert m.match({"path": "/api/order"})
    assert m.match({"path": "/user/1"})
    assert not m.match({"path": "/static/x"})


def test_pure_csv_no_file_exclude():
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="/api/auth", cli_mode=FilterMode.EXCLUDE)
    assert not m.match({"path": "/api/auth/login"})
    assert m.match({"path": "/api/order"})


def test_sentinel_no_file_no_csv():
    """v0 兜底: 无文件 + 无 CSV → 全匹配 sentinel。"""
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv="", cli_mode=FilterMode.INCLUDE)
    assert m.match({"path": "/anything"})
    assert m.match({"path": "/api/order"})
    assert m.match({"path": "/static/x"})


def test_sentinel_csv_only_whitespace():
    m = build_matcher(filter_file=None, profile=None,
                      cli_csv=",, , ", cli_mode=FilterMode.INCLUDE)
    assert m.match({"path": "/anything"})
