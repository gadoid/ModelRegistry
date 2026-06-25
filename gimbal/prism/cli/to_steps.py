"""gimbal prism to-steps — NDJSON → step fragment JSON (中间产物)。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def to_steps_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="场景配置 YAML (用于 services 映射)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出 JSON 路径 (缺省 stdout)"),
) -> None:
    """NDJSON → step 片段 JSON (不组装 scenario)。"""
    try:
        frags = core.ndjson_to_step_fragments(input, config)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)

    text = json.dumps(frags, ensure_ascii=False, indent=2)
    if output is None:
        typer.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"[prism to-steps] wrote {len(frags)} steps to {output}", err=True)