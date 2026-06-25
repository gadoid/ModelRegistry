"""gimbal prism config — get/set scenario config sections (timePolicy/retry/services/...)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

config_app = typer.Typer(help="scenario config 编辑")


@config_app.command("get")
def config_get(
    scenario: Path = typer.Argument(...),
    field: str = typer.Option("timePolicy", "--field", "-f"),
):
    """读 config 某个 section。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    val = core.get_config_section(sc, field)
    typer.echo(json.dumps(val, ensure_ascii=False, indent=2, default=str))


@config_app.command("set")
def config_set(
    scenario: Path = typer.Argument(...),
    time_policy_kind: Optional[str] = typer.Option(None, "--time-policy-kind"),
    time_policy_seconds: Optional[int] = typer.Option(None, "--time-policy-seconds"),
    retry_enabled: Optional[bool] = typer.Option(None, "--retry-enabled/--no-retry-enabled"),
    retry_max_attempts: Optional[int] = typer.Option(None, "--retry-max-attempts"),
    retry_backoff_seconds: Optional[float] = typer.Option(None, "--retry-backoff-seconds"),
):
    """设 config section 字段。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    fields: dict[str, Any] = {}
    if time_policy_kind is not None:
        fields["timePolicyKind"] = time_policy_kind
    if time_policy_seconds is not None:
        fields["timePolicySeconds"] = time_policy_seconds
    if retry_enabled is not None:
        fields["retryEnabled"] = retry_enabled
    if retry_max_attempts is not None:
        fields["retryMaxAttempts"] = retry_max_attempts
    if retry_backoff_seconds is not None:
        fields["retryBackoffSeconds"] = retry_backoff_seconds
    if not fields:
        print_error("at least one --field required", 1)
    sc = load_yaml(scenario)
    sc = core.set_config_section(sc, **fields)
    save_yaml(sc, scenario)
    typer.echo(f"[prism config set] updated: {list(fields.keys())}", err=True)
