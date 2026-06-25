"""gimbal.prism.cli — Typer subcommands for `gimbal prism`.

v0.6+ adds: convert, inspect, validate, to_steps, explain, meta, user,
resource, config. The legacy `start` command (web server launcher) is
re-exported here for backward compatibility with code that did
`from gimbal.prism.cli import start_cmd`.
"""
from __future__ import annotations

import typer

from .convert import convert_cmd
from .explain import explain_cmd
from .inspect import inspect_cmd
from .start import start_cmd
from .to_steps import to_steps_cmd
from .validate import validate_cmd

# 各子命令的 cmd 函数在 Task 10+ 由对应模块注册到 prism_app。
# 现阶段只注册 start。
prism_app = typer.Typer(help="gimbal prism CLI 子命令", no_args_is_help=True)
prism_app.command("start")(start_cmd)
prism_app.command("convert")(convert_cmd)
prism_app.command("explain")(explain_cmd)
prism_app.command("inspect")(inspect_cmd)
prism_app.command("to-steps")(to_steps_cmd)
prism_app.command("validate")(validate_cmd)

__all__ = ["prism_app", "start_cmd", "convert_cmd", "explain_cmd", "inspect_cmd", "to_steps_cmd", "validate_cmd"]