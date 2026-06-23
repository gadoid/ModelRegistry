"""gimbal.capture.loader — include 递归解析。

覆盖 (spec §7.2 test_loader_include):
  - 简单 include (一个 main + 一个 included)
  - 跨子目录 include
  - 自环 / 互环检测
  - 同名 profile 覆盖 + 警告
  - include 路径以主文件目录为基准
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.capture.loader import (
    IncludeCycleError,
    _load_one_yaml,
    build_matcher,
    resolve_includes,
)
from gimbal.capture.strategy import FilterMode, Rule


def test_resolve_simple(tmp_path: Path):
    (tmp_path / "_c.yaml").write_text(
        "mode: exclude\nprofiles:\n  _c:\n    rules: [{path: /auth}]\n",
        encoding="utf-8",
    )
    (tmp_path / "main.yaml").write_text(
        "mode: include\n"
        "includes: [./_c.yaml]\n"
        "profiles:\n"
        "  smoke:\n"
        "    rules: [{path: /api}]\n",
        encoding="utf-8",
    )
    sf = resolve_includes(tmp_path / "main.yaml")
    assert "_c" in sf.profiles
    assert "smoke" in sf.profiles


def test_include_relative_to_main_file(tmp_path: Path):
    """include 路径以主文件目录为基准, 不是 CWD。"""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "common.yaml").write_text(
        "profiles: {c: {rules: [{path: /a}]}}", encoding="utf-8"
    )
    (tmp_path / "main.yaml").write_text(
        "includes: [sub/common.yaml]\nprofiles: {m: {rules: [{path: /b}]}}",
        encoding="utf-8",
    )
    sf = resolve_includes(tmp_path / "main.yaml")
    assert {"c", "m"} <= set(sf.profiles)


def test_include_nested_chain(tmp_path: Path):
    """A → B → C 三级嵌套。"""
    (tmp_path / "c.yaml").write_text(
        "profiles: {c: {rules: [{path: /c}]}}", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "includes: [c.yaml]\nprofiles: {b: {rules: [{path: /b}]}}",
        encoding="utf-8",
    )
    (tmp_path / "a.yaml").write_text(
        "includes: [b.yaml]\nprofiles: {a: {rules: [{path: /a}]}}",
        encoding="utf-8",
    )
    sf = resolve_includes(tmp_path / "a.yaml")
    assert {"a", "b", "c"} <= set(sf.profiles)


def test_include_self_cycle(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        "includes: [a.yaml]\nprofiles: {p: {rules: [{path: /a}]}}",
        encoding="utf-8",
    )
    with pytest.raises(IncludeCycleError):
        resolve_includes(tmp_path / "a.yaml")


def test_include_two_node_cycle(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        "includes: [b.yaml]\nprofiles: {p: {rules: [{path: /a}]}}",
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        "includes: [a.yaml]\nprofiles: {p: {rules: [{path: /b}]}}",
        encoding="utf-8",
    )
    with pytest.raises(IncludeCycleError):
        resolve_includes(tmp_path / "a.yaml")


def test_include_profile_override_warns(tmp_path: Path, capsys):
    (tmp_path / "_c.yaml").write_text(
        "profiles: {p: {rules: [{path: /a}]}}", encoding="utf-8"
    )
    (tmp_path / "main.yaml").write_text(
        "includes: [_c.yaml]\nprofiles: {p: {rules: [{path: /b}]}}",
        encoding="utf-8",
    )
    resolve_includes(tmp_path / "main.yaml")
    out = capsys.readouterr().err
    assert "profile 'p' 被覆盖" in out


def test_include_top_level_fields_only_from_main(tmp_path: Path):
    """include 文件的顶层 mode/default_profile/includes 都被忽略。"""
    (tmp_path / "sub.yaml").write_text(
        "mode: exclude\ndefault_profile: sub_default\nprofiles: {s: {rules: [{path: /s}]}}",
        encoding="utf-8",
    )
    (tmp_path / "main.yaml").write_text(
        "mode: include\ndefault_profile: main_default\n"
        "includes: [sub.yaml]\n"
        "profiles: {m: {rules: [{path: /m}]}}",
        encoding="utf-8",
    )
    sf = resolve_includes(tmp_path / "main.yaml")
    # 顶层 mode/default_profile 来自 main
    assert sf.mode == FilterMode.INCLUDE
    assert sf.default_profile == "main_default"
    # 但 include 进来的 profile 仍存在
    assert "s" in sf.profiles
    assert "m" in sf.profiles
