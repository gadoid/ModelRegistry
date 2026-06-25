"""CLI integration tests for `gimbal prism explain`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner()


def _make_scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    p = tmp_path / "sc.yaml"
    core.save_scenario(scenario, p)
    return p


def test_explain_full(tmp_path):
    p = _make_scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["explain", str(p)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "meta" in data
    assert "steps_count" in data
    assert data["steps_count"] == 1


def test_explain_section(tmp_path):
    p = _make_scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["explain", str(p), "--section", "meta"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "scenarioId" in data or "name" in data


def test_explain_exit_code_2(tmp_path):
    result = runner.invoke(prism_app, ["explain", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
