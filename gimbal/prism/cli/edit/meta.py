"""gimbal prism meta — get/set scenario meta fields."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error

meta_app = typer.Typer(help="scenario meta 编辑")


@meta_app.command("get")
def meta_get(
    scenario: Path = typer.Argument(..., help="scenario YAML"),
    field: Optional[str] = typer.Option(None, "--field", "-f", help="仅输出某个字段"),
):
    """读 meta 字段。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = core.load_scenario(scenario)
    meta = core.get_meta(sc)
    if field:
        if field not in meta:
            print_error(f"field not found: {field}", 6)
        typer.echo(json.dumps({field: meta[field]}, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(json.dumps(meta, ensure_ascii=False, indent=2, default=str))


@meta_app.command("set")
def meta_set(
    scenario: Path = typer.Argument(..., help="scenario YAML"),
    name: Optional[str] = typer.Option(None, "--name"),
    description: Optional[str] = typer.Option(None, "--description"),
    module: Optional[str] = typer.Option(None, "--module"),
    priority: Optional[int] = typer.Option(None, "--priority"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """设 meta 字段 (at least one required)。"""
    fields = {
        k: v for k, v in {
            "name": name, "description": description,
            "module": module, "priority": priority,
        }.items() if v is not None
    }
    if not fields:
        print_error("at least one --field required", 1)
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = core.load_scenario(scenario)
    sc2 = core.set_meta(sc, **fields)
    if dry_run:
        typer.echo(json.dumps(sc2["meta"], ensure_ascii=False, indent=2, default=str))
    else:
        core.save_scenario(sc2, scenario)
        typer.echo(f"[prism meta set] updated: {list(fields.keys())}", err=True)
