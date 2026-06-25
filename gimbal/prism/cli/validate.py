"""gimbal prism validate — config YAML 校验。"""
from __future__ import annotations

from pathlib import Path

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def validate_cmd(
    config: Path = typer.Option(..., "--config", "-c", help="场景配置 YAML"),
) -> None:
    """校验 config YAML 是否合法 (Pydantic schema)。"""
    if not config.exists():
        print_error(f"config not found: {config}", 2)
    errors = core.validate_config(config)
    if errors:
        for e in errors:
            typer.secho(f"  - {e}", fg=typer.colors.RED, err=True)
        raise SystemExit(4)
    typer.echo(f"[prism validate] OK: {config}", err=True)
