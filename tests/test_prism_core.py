"""Unit tests for gimbal.prism.core."""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.prism import core
from gimbal.prism.builder import ScenarioDraft

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