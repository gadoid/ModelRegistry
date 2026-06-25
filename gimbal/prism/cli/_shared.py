"""gimbal.prism.cli._shared — shared utilities for CLI subcommands.

YAML I/O is delegated to gimbal.prism.core.load_scenario/save_scenario
for unified semantics across web and CLI.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NoReturn


def resolve_home(home: Path | None = None) -> Path:
    """Resolve $GIMBAL_HOME; default ~/.gimbal. Create if missing."""
    if home is not None:
        h = home.expanduser()
    else:
        h = Path(os.environ.get("GIMBAL_HOME", "~/.gimbal")).expanduser()
    h.mkdir(parents=True, exist_ok=True)
    return h


def print_error(msg: str, exit_code: int) -> NoReturn:
    """Print error to stderr and exit."""
    import typer as _typer  # noqa: PLC0415
    _typer.secho(msg, fg=_typer.colors.RED, err=True)
    raise SystemExit(exit_code)
