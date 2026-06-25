"""gimbal prism inspect — NDJSON 统计 + 前 N 条样本。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def inspect_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    limit: int = typer.Option(3, "--limit", help="sample 事件数"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出 (缺省人读友好)"),
) -> None:
    """读取 NDJSON 输出统计 + 前 N 条样本。"""
    try:
        stats = core.inspect_ndjson(input, sample_limit=limit)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)

    if as_json:
        typer.echo(json.dumps({
            "event_count": stats.event_count,
            "method_counts": stats.method_counts,
            "host_counts": stats.host_counts,
            "status_counts": stats.status_counts,
            "sample_events": stats.sample_events,
        }, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"events: {stats.event_count}")
        typer.echo(f"methods: {stats.method_counts}")
        typer.echo(f"hosts: {stats.host_counts}")
        typer.echo(f"statuses: {stats.status_counts}")
        typer.echo(f"sample (first {len(stats.sample_events)}):")
        for ev in stats.sample_events:
            typer.echo(f"  {ev.get('method'):6} {ev.get('path'):30} -> {ev.get('response',{}).get('status')}")
