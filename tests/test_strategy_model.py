"""gimbal.capture.strategy — Pydantic 模型校验。

覆盖 (spec §7.2 test_strategy_model):
  - 空 rule 拒绝
  - host 互斥
  - path 互斥
  - methods 大写归一
  - extra 字段拒绝
  - Rule.mode 继承在编译期不报错
  - StrategyFile 默认 mode=INCLUDE
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gimbal.capture.strategy import (
    FilterMode,
    Profile,
    Rule,
    StrategyFile,
)


def test_empty_rule_rejected():
    with pytest.raises(ValidationError, match="至少需要 1 个匹配字段"):
        Rule()


def test_host_mutually_exclusive():
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(host="x.com", host_glob="*.com")
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(host="x.com", host_regex=".*")
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(host_glob="*.com", host_regex=".*")


def test_path_mutually_exclusive():
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(path="/a", path_glob="/a/*")
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(path="/a", path_regex="^/a.*")
    with pytest.raises(ValidationError, match="只能选一个"):
        Rule(path_glob="/a/*", path_regex="^/a.*")


def test_methods_uppercased():
    r = Rule(methods=["get", "Post", "PUT"])
    assert r.methods == ["GET", "POST", "PUT"]


def test_methods_none_preserved():
    r = Rule(path="/a")
    assert r.methods is None


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        Rule(path="/a", foo="bar")


def test_single_field_ok():
    r = Rule(path="/a")
    assert r.path == "/a"
    r2 = Rule(host="x.com")
    assert r2.host == "x.com"
    r3 = Rule(methods=["GET"])
    assert r3.methods == ["GET"]


def test_profile_default_rules_empty():
    p = Profile()
    assert p.rules == []
    assert p.description is None


def test_profile_extra_rejected():
    with pytest.raises(ValidationError):
        Profile(rules=[], foo="bar")


def test_strategy_file_default_mode_include():
    sf = StrategyFile(profiles={"p": Profile()})
    assert sf.mode == FilterMode.INCLUDE
    assert sf.default_profile is None
    assert sf.includes == []


def test_strategy_file_explicit_mode():
    sf = StrategyFile(
        mode=FilterMode.EXCLUDE,
        default_profile="smoke",
        profiles={"smoke": Profile(rules=[Rule(path="/api")])})
    assert sf.mode == FilterMode.EXCLUDE
    assert sf.default_profile == "smoke"


def test_strategy_file_extra_rejected():
    with pytest.raises(ValidationError):
        StrategyFile(profiles={}, unknown_field=42)


def test_rule_dump_serialization():
    """验证 rule 可以序列化为 JSON (供 RuleCompileError 错误信息使用)。"""
    r = Rule(path="/api", methods=["get"])
    d = r.model_dump()
    assert d["path"] == "/api"
    assert d["methods"] == ["GET"]
