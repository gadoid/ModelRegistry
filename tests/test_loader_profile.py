"""gimbal.capture.loader — profile 选择。

覆盖 (spec §7.2 test_loader_profile):
  - 显式 --filter-profile
  - default_profile 自动选
  - 单 profile 自动选
  - 多 profile 未指定 → ProfileNotFound
  - 指定不存在的 profile → ProfileNotFound
"""
from __future__ import annotations

import pytest

from gimbal.capture.loader import (
    ProfileNotFound,
    build_matcher,
)
from gimbal.capture.strategy import FilterMode, Profile, Rule, StrategyFile


def test_explicit_profile():
    sf = StrategyFile(profiles={
        "a": Profile(rules=[Rule(path="/a")]),
        "b": Profile(rules=[Rule(path="/b")]),
    })
    m = build_matcher(filter_file=None, profile="a", cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert m.match({"path": "/a/x"})
    assert not m.match({"path": "/b/x"})


def test_default_profile_auto_selected():
    sf = StrategyFile(
        default_profile="b",
        profiles={
            "a": Profile(rules=[Rule(path="/a")]),
            "b": Profile(rules=[Rule(path="/b")]),
        },
    )
    m = build_matcher(filter_file=None, profile=None, cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert m.match({"path": "/b/x"})
    assert not m.match({"path": "/a/x"})


def test_single_profile_auto_selected():
    sf = StrategyFile(profiles={"only": Profile(rules=[Rule(path="/only")])})
    m = build_matcher(filter_file=None, profile=None, cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
    assert m.match({"path": "/only/x"})


def test_multi_profile_no_default_no_arg():
    sf = StrategyFile(profiles={
        "a": Profile(rules=[Rule(path="/a")]),
        "b": Profile(rules=[Rule(path="/b")]),
    })
    with pytest.raises(ProfileNotFound, match="必须"):
        build_matcher(filter_file=None, profile=None, cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)


def test_missing_profile():
    sf = StrategyFile(profiles={"a": Profile(rules=[Rule(path="/a")])})
    with pytest.raises(ProfileNotFound, match="不存在"):
        build_matcher(filter_file=None, profile="nope", cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)


def test_default_profile_pointing_to_nonexistent():
    sf = StrategyFile(
        default_profile="ghost",
        profiles={"a": Profile(rules=[Rule(path="/a")])},
    )
    with pytest.raises(ProfileNotFound, match="ghost"):
        build_matcher(filter_file=None, profile=None, cli_csv=None,
                      cli_mode=FilterMode.INCLUDE, _strategy_file=sf)
