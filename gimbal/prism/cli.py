"""gimbal prism 子命令实现 — start。

v0 仅 1 子命令: start (启动 FastAPI web 配置器)。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from gimbal.prism.server import app as fastapi_app


def start_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    home: Optional[Path] = typer.Option(None, "--home"),
    workers: int = typer.Option(1, "--workers", "-w", help="uvicorn workers, v0 仅支持 1"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
) -> None:
    """启动 prism 配置器 web UI。"""
    if workers != 1:
        typer.secho("[prism] v0 仅支持 --workers 1, 已强制设 1", fg=typer.colors.YELLOW)
        workers = 1

    if home is not None:
        os.environ["GIMBAL_HOME"] = str(home.expanduser())
    home_path = Path(os.environ.get("GIMBAL_HOME", "~/.gimbal")).expanduser()
    if not home_path.exists():
        typer.secho(f"[prism] 警告: {home_path} 不存在, 自动创建", fg=typer.colors.YELLOW)
        home_path.mkdir(parents=True, exist_ok=True)

    typer.echo(f"[prism] GIMBAL_HOME={home_path}")
    typer.echo(f"[prism] starting on http://{host}:{port}")

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="info",
    )
