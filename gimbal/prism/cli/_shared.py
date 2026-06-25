"""gimbal.prism.cli._shared — shared utilities for CLI subcommands."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import yaml


def resolve_home(home: Path | None = None) -> Path:
    """Resolve $GIMBAL_HOME; default ~/.gimbal. Create if missing."""
    if home is not None:
        h = home.expanduser()
    else:
        h = Path(os.environ.get("GIMBAL_HOME", "~/.gimbal")).expanduser()
    h.mkdir(parents=True, exist_ok=True)
    return h


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        print_error(f"file not found: {path}", 2)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_yaml(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def print_error(msg: str, exit_code: int) -> NoReturn:
    """Print error to stderr and exit."""
    typer = None  # type: ignore[assignment]
    import typer as _typer  # noqa: PLC0415
    _typer.secho(msg, fg=_typer.colors.RED, err=True)
    raise SystemExit(exit_code)
