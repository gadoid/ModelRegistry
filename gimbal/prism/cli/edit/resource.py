"""gimbal prism resource — list/add/remove scenario resources."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

resource_app = typer.Typer(help="scenario resources 编辑")


@resource_app.command("list")
def resource_list(scenario: Path = typer.Argument(...)):
    """列出所有 resources。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    res = core.list_resources(sc)
    typer.echo(json.dumps([{"name": n, **v} for n, v in res],
                          ensure_ascii=False, indent=2, default=str))


@resource_app.command("add")
def resource_add(
    scenario: Path = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    kind: str = typer.Option("mock", "--kind"),
    image: str = typer.Option("", "--image"),
    port: Optional[str] = typer.Option(None, "--port", help="host:container 形式"),
):
    """新增 resource。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    port_mapping: dict[str, int] = {}
    if port:
        h, c = port.split(":")
        port_mapping[h] = int(c)
    sc = load_yaml(scenario)
    fields: dict[str, Any] = {"kind": kind}
    if image:
        fields["image"] = image
    if port_mapping:
        fields["portMapping"] = {int(k): v for k, v in port_mapping.items()}
    sc = core.add_resource(sc, name, **fields)
    save_yaml(sc, scenario)
    typer.echo(f"[prism resource add] added: {name}", err=True)


@resource_app.command("remove")
def resource_remove(
    scenario: Path = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
):
    """删除 resource。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    try:
        sc = core.remove_resource(sc, name)
    except KeyError:
        print_error(f"resource not found: {name}", 6)
    save_yaml(sc, scenario)
    typer.echo(f"[prism resource remove] removed: {name}", err=True)
