"""gimbal.prism.core — shared pipeline + edit primitives used by prism-cli.

OBLIGATION: This module must call builder.build_scenario() under the hood
and stay in sync with it. tests/test_prism_core_builder_parity.py is the
canary that detects drift.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gimbal.prism.builder import (
    AuthDraft,
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
    build_scenario,
)
from gimbal.schema import Scenario


@dataclass
class ConvertResult:
    scenario: dict[str, Any]
    output_path: Path | None
    yaml_text: str
    warnings: list[str] = field(default_factory=list)
    event_count: int = 0
    step_count: int = 0


@dataclass
class NdjsonStats:
    event_count: int
    method_counts: dict[str, int]
    host_counts: dict[str, int]
    status_counts: dict[int, int]
    sample_events: list[dict[str, Any]]


def render(draft: ScenarioDraft) -> dict[str, Any]:
    """Render ScenarioDraft to a validated scenario dict.

    Calls builder.build_scenario() and validates against Scenario schema.
    Raises pydantic.ValidationError on invalid scenarios.
    """
    scenario = build_scenario(draft)
    Scenario.model_validate(scenario)
    return scenario


def parse_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read an NDJSON file and return all events as a list of dicts.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if file is empty (no events).
        json.JSONDecodeError: propagated from json.loads for malformed lines.
    """
    if not path.exists():
        raise FileNotFoundError(f"ndjson not found: {path}")
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if not events:
        raise ValueError(f"ndjson has no events: {path}")
    return events


def _scenario_id_from_events(events: list[dict[str, Any]]) -> str:
    """Derive scenario_id from first event's host/path. Default: 'sc_default'."""
    if not events:
        return "sc_default"
    first = events[0]
    host = (first.get("host") or "default").replace(".", "_").replace("-", "_")
    path = (first.get("path") or "").replace("/", "_").strip("_") or "x"
    return f"sc_{host}_{path}"[:64]


def load_config(
    path: Path | None, events: list[dict[str, Any]],
) -> ScenarioDraft:
    """Load scenario config YAML into a ScenarioDraft.

    If path is None, returns a default draft populated only with steps from events.
    Field names in YAML use snake_case (time_policy, retry); translated to
    snake_case Draft fields (timePolicyKind projection happens later in
    builder.build_scenario()).
    """
    if path is None:
        sid = _scenario_id_from_events(events)
        return ScenarioDraft(
            scenario_id=sid,
            name=sid,
            steps=[StepDraft(capture=e) for e in events],
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"config YAML must be a mapping, got {type(raw).__name__}: {path}"
        )
    users: dict[str, AuthDraft] = {}
    for k, v in (raw.get("users") or {}).items():
        users[k] = AuthDraft(
            url=v.get("url", ""),
            username=v.get("username", ""),
            password=v.get("password", ""),
            expires_in=v.get("expires_in", 7200),
            token_type=v.get("token_type", "Authorization"),
            token=v.get("token"),
        )
    resources: dict[str, ResourceDraft] = {}
    for r in (raw.get("resources") or []):
        resources[r["name"]] = ResourceDraft(
            name=r["name"],
            kind=r.get("kind", "mock"),
            image=r.get("image", ""),
            config=r.get("config") or {},
            port_mapping={str(k): v for k, v in (r.get("port_mapping") or {}).items()},
            path=r.get("path", ""),
            ref=r.get("ref", ""),
            value=r.get("value"),
        )
    tp = raw.get("time_policy") or {}
    rt = raw.get("retry") or {}
    return ScenarioDraft(
        scenario_id=raw.get("scenario_id", _scenario_id_from_events(events)),
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        module=raw.get("module", "default"),
        priority=raw.get("priority", 1),
        author=raw.get("author", "prism"),
        owner=raw.get("owner", "prism"),
        tags=raw.get("tags") or ["smoke"],
        version=raw.get("version", "1.0.0"),
        expire=raw.get("expire", False),
        requirement_ref=raw.get("requirement_ref") or [],
        services=raw.get("services") or {},
        users=users,
        time_policy_kind=tp.get("kind", "record"),
        time_policy_seconds=tp.get("seconds", 60),
        retry_enabled=rt.get("enabled", False),
        retry_max_attempts=rt.get("max_attempts", 3),
        retry_backoff_seconds=rt.get("backoff_seconds", 20.0),
        retry_on=rt.get("retry_on") or [],
        setup_refs=raw.get("setup_refs") or [],
        teardown_refs=raw.get("teardown_refs") or [],
        resources=resources,
        steps=[StepDraft(capture=e) for e in events],
    )


def write(result: ConvertResult, output_path: Path | None) -> None:
    """Serialize result.scenario to YAML and write to output_path (if given).

    Mutates result.yaml_text and result.output_path.
    """
    yaml_text = yaml.safe_dump(
        result.scenario, allow_unicode=True, sort_keys=False,
    )
    result.yaml_text = yaml_text
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")
        result.output_path = output_path


def convert_ndjson_to_scenario(
    ndjson_path: Path,
    config_path: Path | None,
    output_path: Path | None = None,
) -> ConvertResult:
    """Full pipeline: NDJSON + optional config → Scenario YAML.

    Pipeline: parse → load_config → render → write.
    """
    events = parse_ndjson(ndjson_path)
    draft = load_config(config_path, events)
    scenario = render(draft)
    enabled_steps = [s for s in draft.steps if s.enabled]
    result = ConvertResult(
        scenario=scenario,
        output_path=None,
        yaml_text="",
        event_count=len(events),
        step_count=len(enabled_steps),
    )
    write(result, output_path)
    return result


def inspect_ndjson(path: Path, sample_limit: int = 3) -> NdjsonStats:
    """Compute stats over NDJSON events."""
    events = parse_ndjson(path)
    methods: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    statuses: Counter[int] = Counter()
    for e in events:
        methods[(e.get("method") or "GET").upper()] += 1
        hosts[e.get("host") or ""] += 1
        st = (e.get("response") or {}).get("status")
        if st is not None:
            statuses[st] += 1
    return NdjsonStats(
        event_count=len(events),
        method_counts=dict(methods),
        host_counts=dict(hosts),
        status_counts=dict(statuses),
        sample_events=events[:sample_limit],
    )


def validate_config(path: Path) -> list[str]:
    """Validate a config YAML against Scenario schema (after loading events).

    Returns a list of error strings; empty list means valid.
    For pure config validation without events, we use a synthetic event so
    build_scenario doesn't reject on empty steps.
    """
    events = [{"host": "_validate", "method": "GET", "path": "/_validate",
               "headers": {}, "body": "", "response": {"status": 200}}]
    try:
        draft = load_config(path, events)
        render(draft)
        return []
    except Exception as e:  # noqa: BLE001
        return [str(e)]


def ndjson_to_step_fragments(
    ndjson_path: Path, config_path: Path | None,
) -> list[dict[str, Any]]:
    """Convert NDJSON to step fragment dicts (no scenario assembly)."""
    from gimbal.prism.convert import convert_record, load_rules  # noqa: PLC0415

    events = parse_ndjson(ndjson_path)
    rules = load_rules(None)  # default rules; config file's services handled later
    if config_path is not None:
        cfg_raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        rules["services"].update(cfg_raw.get("services") or {})
    return [convert_record(e, rules) for e in events]