"""gimbal prism user — list/add/remove scenario users."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

user_app = typer.Typer(help="scenario users 编辑")


@user_app.command("list")
def user_list(scenario: Path = typer.Argument(...)):
    """列出所有 users。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    users = core.list_users(sc)
    typer.echo(json.dumps([{"key": k, **v} for k, v in users],
                          ensure_ascii=False, indent=2, default=str))


@user_app.command("add")
def user_add(
    scenario: Path = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
    url: str = typer.Option("", "--url"),
    username: str = typer.Option("", "--username"),
    password: str = typer.Option("", "--password"),
    expires_in: int = typer.Option(7200, "--expires-in"),
    token_type: str = typer.Option("Authorization", "--token-type"),
):
    """新增 user。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    sc = core.add_user(
        sc, key,
        url=url, username=username, password=password,
        expires_in=expires_in, token_type=token_type,
    )
    save_yaml(sc, scenario)
    typer.echo(f"[prism user add] added: {key}", err=True)


@user_app.command("remove")
def user_remove(
    scenario: Path = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
):
    """删除 user。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    try:
        sc = core.remove_user(sc, key)
    except KeyError:
        print_error(f"user not found: {key}", 6)
    save_yaml(sc, scenario)
    typer.echo(f"[prism user remove] removed: {key}", err=True)
