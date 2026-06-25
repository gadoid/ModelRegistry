"""gimbal prism convert — NDJSON (+ config) → Scenario YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error, resolve_home


def convert_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="场景配置 YAML"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出 YAML 路径 (缺省 stdout)"),
    home: Optional[Path] = typer.Option(None, "--home"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """NDJSON + 可选 config → Scenario YAML。"""
    resolve_home(home)  # ensure dir exists, even if unused
    try:
        result = core.convert_ndjson_to_scenario(input, config, output)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)
    except Exception as e:  # noqa: BLE001
        if not quiet:
            raise
        print_error(f"internal error: {e}", 5)

    if not quiet:
        typer.echo(
            f"[prism convert] events={result.event_count} "
            f"steps={result.step_count} "
            f"output={result.output_path or '<stdout>'}",
            err=True,
        )

    if output is None:
        typer.echo(result.yaml_text)