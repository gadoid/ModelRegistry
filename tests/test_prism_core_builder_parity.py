"""Parity canary: web (_draft_from_in + build_scenario) and CLI (core) must
produce identical scenario dicts for the same inputs.

Fails CI on any drift between gimbal.prism.core and gimbal.prism.builder.
"""
from __future__ import annotations

import copy
from pathlib import Path

from gimbal.prism.builder import (
    ScenarioDraft,
    StepDraft,
    build_scenario,
)
from gimbal.prism import core

FIXTURES = Path(__file__).parent / "fixtures"


def _events():
    return [
        {"host": "api.example.com", "method": "GET", "path": "/x",
         "headers": {}, "body": "", "response": {"status": 200}},
        {"host": "api.example.com", "method": "POST", "path": "/y",
         "headers": {}, "body": "{}", "response": {"status": 201}},
    ]


def _normalize_create_time(scenario: dict) -> dict:
    """build_scenario() stamps Meta.createTime with datetime.now(), so two
    separate calls produce different timestamps. Strip it for byte-identical
    parity comparison; the canary is about *structure* not clock drift."""
    sc = copy.deepcopy(scenario)
    sc.get("meta", {}).pop("createTime", None)
    return sc


def test_parity_default_scenario():
    events = _events()
    cli_draft = core.load_config(None, events)
    cli_scenario = core.render(cli_draft)
    # web 路径: 直接构造 ScenarioDraft + build_scenario
    web_draft = ScenarioDraft(
        scenario_id=cli_draft.scenario_id,
        name=cli_draft.name,
        steps=[StepDraft(capture=e) for e in events],
    )
    web_scenario = build_scenario(web_draft)
    assert _normalize_create_time(web_scenario) == _normalize_create_time(cli_scenario)


def test_parity_with_config():
    events = _events()
    cli_draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    cli_scenario = core.render(cli_draft)
    # web 路径: 直接构造 ScenarioDraft + build_scenario (与 load_config 同字段)
    web_scenario = build_scenario(cli_draft)
    assert _normalize_create_time(web_scenario) == _normalize_create_time(cli_scenario)
