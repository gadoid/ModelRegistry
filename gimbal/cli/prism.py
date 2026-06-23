"""gimbal prism 子命令组注册。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.prism.cli import start_cmd

prism_app = typer.Typer(help="gimbal 配置器(web)", no_args_is_help=True)


@prism_app.command("start")
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    home: Optional[Path] = typer.Option(None, "--home"),
    workers: int = typer.Option(1, "--workers", "-w", help="uvicorn workers, v0 仅支持 1"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
):
    """启动 prism 配置器 web UI。"""
    start_cmd(host, port, home, workers, reload)
