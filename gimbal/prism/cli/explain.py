"""gimbal prism explain — scenario YAML 结构化摘要。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def explain_cmd(
    scenario: Path = typer.Argument(..., help="scenario YAML 路径"),
    section: Optional[str] = typer.Option(None, "--section", help="仅输出某个 section (meta/config/steps/...)"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
) -> None:
    """读 scenario YAML 输出结构化摘要。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = core.load_scenario(scenario)
    summary = core.explain_scenario(sc)
    if section:
        if section not in summary:
            print_error(f"unknown section: {section} (available: {list(summary.keys())})", 1)
        payload = summary[section]
    else:
        payload = summary

    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
