"""gimbal.cli.capture — 端到端集成测试。

覆盖 (spec §7.3 test_cli_integration):
  - 合法 filter-file + profile → CLI 接受
  - 缺 profile → 退出码 5
  - 坏 YAML → 退出码 5
  - --filter-file 不存在 → 退出码 5
  - --strict-files-only + 无文件 → 退出码 5
  - 旧 --filter CSV 兼容
  - addon 脚本包含 build_matcher + matcher 变量
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gimbal.capture.cli import _render_addon_script
from gimbal.cli.capture import capture_app

runner = CliRunner()
app = capture_app


def test_start_with_valid_filter_file(tmp_path: Path):
    (tmp_path / "filters.yaml").write_text(
        "mode: include\nprofiles:\n  smoke:\n    rules: [{path: /api}]\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "filters.yaml"),
        "--filter-profile", "smoke",
        "--mitmdump", "/bin/true",
    ])
    # /bin/true 立即退出, 父进程 build_matcher 成功, 错误消息不含"筛选配置错误"
    assert "筛选配置错误" not in result.output


def test_invalid_yaml_exits_5(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text("mode: include\n", encoding="utf-8")  # 缺 profiles
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "bad.yaml"),
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "筛选配置错误" in result.output


def test_missing_profile_exits_5(tmp_path: Path):
    (tmp_path / "f.yaml").write_text(
        "mode: include\nprofiles:\n  smoke: {rules: [{path: /a}]}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "f.yaml"),
        "--filter-profile", "nope",
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "profile 'nope' 不存在" in result.output


def test_explicit_file_not_found_exits_5(tmp_path: Path):
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "missing.yaml"),
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "不存在" in result.output


def test_strict_files_only_no_file_exits_5(tmp_path: Path):
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--strict-files-only",
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "未找到 filter 文件" in result.output


def test_legacy_csv_compat(tmp_path: Path):
    """旧 --filter CSV 用法: 父进程校验通过, mitmdump=/bin/true 立即退出。"""
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter", "/api/,/user",
        "--mitmdump", "/bin/true",
    ])
    assert "筛选配置错误" not in result.output
    assert "filter rules:" in result.output


def test_empty_filter_sentinel(tmp_path: Path):
    """--filter '' 走 sentinel 全匹配。"""
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter", "",
        "--mitmdump", "/bin/true",
    ])
    assert "筛选配置错误" not in result.output
    assert "filter rules: 1" in result.output


def test_empty_rules_no_csv_exits_5(tmp_path: Path):
    (tmp_path / "f.yaml").write_text(
        "mode: include\nprofiles:\n  p: {rules: []}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "f.yaml"),
        "--filter-profile", "p",
        "--filter", "",
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "无任何规则" in result.output


def test_bad_regex_exits_5(tmp_path: Path):
    (tmp_path / "f.yaml").write_text(
        "profiles:\n  p:\n    rules: [{path_regex: '[invalid'}]\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, [
        "start", "--session", "x",
        "--home", str(tmp_path),
        "--filter-file", str(tmp_path / "f.yaml"),
        "--mitmdump", "/bin/true",
    ])
    assert result.exit_code == 5
    assert "正则编译失败" in result.output


def test_addon_script_contains_build_matcher():
    """addon 脚本必须包含 build_matcher 调用 + matcher 变量。"""
    script = _render_addon_script(
        Path("/tmp/gimbal"), "dev-1",
        filter_file=None, filter_profile=None,
        cli_csv="/api/", cli_mode="include",
    )
    assert "from gimbal.capture.loader import build_matcher" in script
    assert "matcher = build_matcher" in script
    assert "CaptureAddon(bus, matcher)" in script


def test_addon_script_escapes_windows_path():
    """addon 脚本对 Windows 反斜杠和引号做转义。"""
    script = _render_addon_script(
        Path("C:\\Users\\me\\.gimbal"),
        's"id',
        filter_file=Path("C:\\filters\\test.yaml"),
        filter_profile="smoke",
        cli_csv='/api"x',
        cli_mode="include",
    )
    # Windows 路径 \ 应被转义
    assert "\\\\" in script
    # 引号应被转义
    assert '\\"' in script


def test_addon_script_executes_filter_file_as_path(tmp_path: Path):
    """回归 v0.4.1 bug: cli._render_addon_script 把 filter_file(Path) 序列化为 str,
    mitmdump 子进程 exec 时 loader.discover_filter_file 调 .expanduser() → AttributeError。

    本测试只验"addon 脚本能在子进程中被 exec" + "matcher 对象被构造" 两点;
    match 业务语义 (path_prefix/host_glob 等) 不在本测试的责任范围,
    那是 gimbal.capture.strategy 自己的测试覆盖。
    """
    f = tmp_path / "filters.yaml"
    f.write_text(
        "mode: include\nprofiles:\n  smoke:\n    rules:\n      - path: /api\n",
        encoding="utf-8",
    )

    script = _render_addon_script(
        tmp_path,
        "sess-exec",
        filter_file=f,
        filter_profile="smoke",
        cli_csv="/api/",
        cli_mode="include",
    )

    namespace: dict = {"__name__": "__not_main__"}
    exec(compile(script, "<addon>", "exec"), namespace)  # 不抛 = bug 不存在

    # KeyError if matcher 未被构造 — 真实断言,不是 dead assertion
    matcher = namespace["matcher"]
    # 类型 sanity,不耦合 strategy.py 的 match 语义
    assert callable(getattr(matcher, "match", None))


@pytest.mark.parametrize(
    "filter_file,profile",
    [
        pytest.param(None, None, id="no-file-no-profile"),
        pytest.param(Path("/some/f.yaml"), "smoke", id="file-and-profile"),
    ],
)
def test_addon_script_executes_filter_file_none_boundary(
    tmp_path: Path, filter_file, profile
):
    """边界: filter_file=None 时,addon 脚本里 `Path(None)` 必须短路为 None。

    修 v0.4.1 时引入了 `Path({file_repr}) if {file_repr} != "None" else None`,
    此测试守护 None 短路分支。
    """
    if filter_file is not None:
        filter_file = tmp_path / "filters.yaml"
        filter_file.write_text(
            "mode: include\nprofiles:\n  smoke:\n    rules:\n      - path: /api\n",
            encoding="utf-8",
        )

    script = _render_addon_script(
        tmp_path,
        "sess-exec",
        filter_file=filter_file,
        filter_profile=profile,
        cli_csv="/api/",
        cli_mode="include",
    )

    namespace: dict = {"__name__": "__not_main__"}
    exec(compile(script, "<addon>", "exec"), namespace)

    # matcher 必须被构造 (None filter_file 也应得到 default sentinel matcher)
    matcher = namespace["matcher"]
    assert matcher is not None
    assert callable(getattr(matcher, "match", None))
