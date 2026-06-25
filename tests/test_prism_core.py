"""Unit tests for gimbal.prism.core."""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.prism import core
from gimbal.prism.builder import ScenarioDraft
from gimbal.schema import Scenario

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ndjson_returns_list_of_events():
    result = core.parse_ndjson(FIXTURES / "minimal_captures.ndjson")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["method"] == "GET"
    assert result[0]["path"] == "/health"


def test_parse_ndjson_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        core.parse_ndjson(tmp_path / "nope.ndjson")


def test_parse_ndjson_empty_file_raises(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.write_text("")
    with pytest.raises(ValueError, match="no events"):
        core.parse_ndjson(p)


def test_load_config_none_returns_default_draft():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    assert isinstance(draft, ScenarioDraft)
    # scenario_id 从 first event 的 host + path 派生
    assert draft.scenario_id == "sc_api_example_com_x"
    assert len(draft.steps) == 1


def test_load_config_none_with_empty_events_uses_sc_default():
    draft = core.load_config(None, [])
    assert draft.scenario_id == "sc_default"
    assert draft.steps == []


def test_load_config_full_yaml():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    assert draft.scenario_id == "sc_sample"
    assert draft.name == "Sample scenario"
    assert "admin" in draft.users
    assert draft.services == {"api.example.com": "auth-api"}


def test_render_minimal_produces_valid_scenario():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    result = core.render(draft)
    assert isinstance(result, dict)
    # 必须能被 Scenario 验证
    Scenario.model_validate(result)
    assert result["scenarioId"].startswith("sc_")


def test_render_full_yaml():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    result = core.render(draft)
    assert result["scenarioId"] == "sc_sample"
    assert "admin" in result["config"]["users"]


def test_write_returns_yaml_when_no_output():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    result = core.ConvertResult(scenario=scenario, output_path=None, yaml_text="",
                                event_count=1, step_count=1)
    core.write(result, None)
    assert "scenarioId:" in result.yaml_text
    assert result.output_path is None


def test_write_writes_file_when_output_given(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    result = core.ConvertResult(scenario=scenario, output_path=None, yaml_text="",
                                event_count=1, step_count=1)
    out = tmp_path / "out.yaml"
    core.write(result, out)
    assert out.exists()
    assert "scenarioId:" in out.read_text(encoding="utf-8")
    assert result.output_path == out


def test_convert_ndjson_to_scenario_full_pipeline(tmp_path):
    out = tmp_path / "sc.yaml"
    result = core.convert_ndjson_to_scenario(
        FIXTURES / "minimal_captures.ndjson",
        None, out,
    )
    assert result.event_count == 1
    assert result.step_count == 1
    assert out.exists()