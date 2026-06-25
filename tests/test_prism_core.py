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


def test_inspect_ndjson_stats():
    stats = core.inspect_ndjson(FIXTURES / "sample_captures.ndjson", sample_limit=2)
    assert stats.event_count == 3
    assert stats.method_counts == {"POST": 1, "GET": 2}
    assert stats.host_counts == {"api.example.com": 3}
    assert stats.status_counts == {200: 2, 404: 1}
    assert len(stats.sample_events) == 2


def test_validate_config_returns_empty_for_valid():
    errors = core.validate_config(FIXTURES / "sample_config.yaml")
    assert errors == []


def test_validate_config_returns_errors_for_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario_id: 123\nname: ''\n")  # name 不能为空
    errors = core.validate_config(bad)
    assert any("name" in e.lower() for e in errors)


def test_ndjson_to_step_fragments_returns_list():
    frags = core.ndjson_to_step_fragments(FIXTURES / "minimal_captures.ndjson", None)
    assert isinstance(frags, list)
    assert len(frags) == 1
    assert "api" in frags[0]
    assert "request" in frags[0]


def test_load_save_scenario_roundtrip(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    p = tmp_path / "sc.yaml"
    core.save_scenario(scenario, p)
    loaded = core.load_scenario(p)
    assert loaded["scenarioId"] == scenario["scenarioId"]


def test_validate_scenario_passes_for_valid():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    core.validate_scenario(scenario)  # 不抛 = 通过


def test_explain_scenario_returns_summary():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    summary = core.explain_scenario(scenario)
    assert "meta" in summary
    assert "steps_count" in summary
    assert summary["steps_count"] == 1


def _make_scenario():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    return core.render(core.load_config(None, events))


def test_set_meta_roundtrip():
    sc = _make_scenario()
    sc2 = core.set_meta(sc, name="New name", description="New desc")
    assert sc2["meta"]["name"] == "New name"
    assert sc2["meta"]["description"] == "New desc"


def test_user_add_remove_roundtrip():
    sc = _make_scenario()
    sc = core.add_user(sc, "ops", url="https://x", username="ops", password="p")
    assert "ops" in sc["config"]["users"]
    users = core.list_users(sc)
    assert any(k == "ops" for k, _ in users)
    sc = core.remove_user(sc, "ops")
    assert "ops" not in sc["config"]["users"]


def test_remove_user_raises_for_missing():
    sc = _make_scenario()
    with pytest.raises(KeyError):
        core.remove_user(sc, "ghost")


def test_resource_add_remove_roundtrip():
    sc = _make_scenario()
    sc = core.add_resource(sc, "redis", kind="mock", image="redis:7",
                           portMapping={6379: 6379})
    assert "redis" in sc["resource"]
    resources = core.list_resources(sc)
    assert any(n == "redis" for n, _ in resources)
    sc = core.remove_resource(sc, "redis")
    assert "redis" not in sc["resource"]


def test_config_get_set_section():
    sc = _make_scenario()
    tp = core.get_config_section(sc, "timePolicy")
    assert tp is not None
    sc = core.set_config_section(sc, timePolicy={"kind": "timeout", "seconds": 120})
    tp = core.get_config_section(sc, "timePolicy")
    assert tp["kind"] == "timeout"
    assert tp["seconds"] == 120


def test_ndjson_to_step_fragments_does_not_leak_services_across_calls(tmp_path):
    """Regression: load_rules(None) must return a fresh copy, not the singleton.

    Calling ndjson_to_step_fragments twice with different config services must
    not leak the first config's services into the second call's output.
    """
    from gimbal.prism.convert import DEFAULT_RULES

    cfg_a = tmp_path / "cfg_a.yaml"
    cfg_a.write_text(
        "services:\n  api.example.com: service-A\n",
        encoding="utf-8",
    )
    cfg_b = tmp_path / "cfg_b.yaml"
    cfg_b.write_text(
        "services:\n  api.example.com: service-B\n",
        encoding="utf-8",
    )

    frags_a = core.ndjson_to_step_fragments(
        FIXTURES / "minimal_captures.ndjson", cfg_a,
    )
    frags_b = core.ndjson_to_step_fragments(
        FIXTURES / "minimal_captures.ndjson", cfg_b,
    )

    # cfg_A → service-A
    assert frags_a[0]["api"]["service"] == "service-A"
    # cfg_B → service-B (not service-A leaking from prior call)
    assert frags_b[0]["api"]["service"] == "service-B"
    # The shared DEFAULT_RULES module singleton must remain pristine
    assert DEFAULT_RULES["services"] == {}
