"""gimbal.capture.loader — YAML 解析 + Pydantic 校验。

覆盖 (spec §7.2 test_loader_yaml):
  - 合法 YAML → StrategyFile
  - 缺 profiles 字段 → FilterConfigError
  - 坏 YAML 语法 → FilterConfigError
  - root 非 mapping → FilterConfigError
  - host/path 互斥在 YAML 层也生效
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.capture.loader import (
    FilterConfigError,
    _load_one_yaml,
    build_matcher,
)
from gimbal.capture.strategy import FilterMode, Profile, Rule, StrategyFile


def test_load_minimal_yaml(tmp_path: Path):
    p = tmp_path / "filters.yaml"
    p.write_text("profiles:\n  p:\n    rules: [{path: /api}]\n", encoding="utf-8")
    sf = _load_one_yaml(p)
    assert sf.mode == FilterMode.INCLUDE
    assert "p" in sf.profiles


def test_load_full_yaml(tmp_path: Path):
    p = tmp_path / "filters.yaml"
    p.write_text(
        "mode: exclude\n"
        "default_profile: smoke\n"
        "profiles:\n"
        "  smoke:\n"
        "    description: 日常冒烟\n"
        "    rules:\n"
        "      - host: api.example.com\n"
        "        path: /api/order\n"
        "        methods: [POST]\n",
        encoding="utf-8",
    )
    sf = _load_one_yaml(p)
    assert sf.mode == FilterMode.EXCLUDE
    assert sf.default_profile == "smoke"
    assert sf.profiles["smoke"].description == "日常冒烟"
    rule = sf.profiles["smoke"].rules[0]
    assert rule.host == "api.example.com"
    assert rule.path == "/api/order"
    assert rule.methods == ["POST"]


def test_load_missing_profiles_rejected(tmp_path: Path):
    p = tmp_path / "f.yaml"
    p.write_text("mode: include\n", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="校验失败"):
        _load_one_yaml(p)


def test_load_bad_yaml_syntax(tmp_path: Path):
    p = tmp_path / "f.yaml"
    p.write_text("mode: include\n  profiles:\n  bad indent\n :\n", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="YAML 解析失败"):
        _load_one_yaml(p)


def test_load_root_not_mapping(tmp_path: Path):
    p = tmp_path / "f.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="必须是 mapping"):
        _load_one_yaml(p)


def test_load_empty_yaml(tmp_path: Path):
    """空 YAML 文件应被当作空 mapping (无 profiles → 校验失败)。"""
    p = tmp_path / "f.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="校验失败"):
        _load_one_yaml(p)


def test_load_rule_validation_in_yaml(tmp_path: Path):
    """YAML 层的 rule 互斥校验。"""
    p = tmp_path / "f.yaml"
    p.write_text(
        "profiles:\n  p:\n    rules: [{path: /a, path_glob: /b/*}]\n",
        encoding="utf-8",
    )
    with pytest.raises(FilterConfigError, match="只能选一个"):
        _load_one_yaml(p)


def test_load_methods_lowercase_in_yaml(tmp_path: Path):
    """YAML 里的 methods 也会被归一大写。"""
    p = tmp_path / "f.yaml"
    p.write_text(
        "profiles:\n  p:\n    rules: [{methods: [get, post]}]\n",
        encoding="utf-8",
    )
    sf = _load_one_yaml(p)
    assert sf.profiles["p"].rules[0].methods == ["GET", "POST"]
