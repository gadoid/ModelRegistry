"""gimbal capture 子命令组注册。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.capture.cli import (
    archive_cmd,
    list_sessions_cmd,
    show_session_cmd,
    start_cmd,
)
from gimbal.capture.strategy import FilterMode

capture_app = typer.Typer(help="gimbal 流量捕获模块", no_args_is_help=True)


@capture_app.command("start")
def start(
    session: str = typer.Option(..., "--session", "-s", help="会话 ID"),
    port: int = typer.Option(8080, "--port", "-p"),
    filter: str = typer.Option("/api/", "--filter", "-f"),
    home: Optional[Path] = typer.Option(None, "--home"),
    mitmdump: str = typer.Option("mitmdump", help="mitmdump 可执行文件路径"),
    # ── v0.4 新增 (Capture Filter Strategy) ────────────────────────────────
    filter_file: Optional[Path] = typer.Option(
        None,
        "--filter-file",
        help="YAML 筛选配置文件; 未传则按 .gimbal/filters.yaml 等自动查找",
    ),
    filter_profile: Optional[str] = typer.Option(
        None,
        "--filter-profile",
        help="要使用的 profile 名; 多 profile 时必填",
    ),
    filter_mode: FilterMode = typer.Option(
        FilterMode.INCLUDE,
        "--filter-mode",
        help="CLI --filter 追加规则的默认 mode (include / exclude)",
    ),
    strict_files_only: bool = typer.Option(
        False,
        "--strict-files-only",
        help="关闭自动文件查找, 只用 --filter-file",
    ),
):
    """启动 mitmproxy 抓包, Ctrl+C 停止并自动归档。"""
    start_cmd(
        session=session,
        port=port,
        filter=filter,
        home=home,
        mitmdump=mitmdump,
        filter_file=filter_file,
        filter_profile=filter_profile,
        filter_mode=filter_mode,
        strict_files_only=strict_files_only,
    )


@capture_app.command("list")
def list_cmd(home: Optional[Path] = typer.Option(None, "--home")):
    """列出 active 下所有 session。"""
    list_sessions_cmd(home)


@capture_app.command("show")
def show_cmd(
    session: str = typer.Argument(..., help="会话 ID"),
    home: Optional[Path] = typer.Option(None, "--home"),
    limit: int = typer.Option(50, "--limit", "-n"),
):
    """查看某 session 的事件(默认最近 50 条)。"""
    show_session_cmd(session, home, limit)


@capture_app.command("archive")
def archive_cli(
    session: str = typer.Argument(..., help="会话 ID"),
    home: Optional[Path] = typer.Option(None, "--home"),
):
    """手动归档一个 session(从 active 移到 archive)。"""
    archive_cmd(session, home)
