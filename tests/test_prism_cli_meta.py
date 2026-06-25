"""CLI integration tests for `gimbal prism meta`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner()


def _scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    p = tmp_path / "sc.yaml"
    core.save_scenario(core.render(draft), p)
    return p


def test_meta_get(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "get", str(p)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "name" in data


def test_meta_get_field(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "get", str(p), "--field", "name"])
    assert result.exit_code == 0


def test_meta_set(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, [
        "meta", "set", str(p), "--name", "Renamed", "--description", "new desc",
    ])
    assert result.exit_code == 0
    sc = core.load_scenario(p)
    assert sc["meta"]["name"] == "Renamed"
    assert sc["meta"]["description"] == "new desc"


def test_meta_set_dry_run(tmp_path):
    p = _scenario_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    result = runner.invoke(prism_app, [
        "meta", "set", str(p), "--name", "DryRun", "--dry-run",
    ])
    assert result.exit_code == 0
    # 不写文件
    assert p.read_text(encoding="utf-8") == before


def test_meta_set_no_fields(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "set", str(p)])
    assert result.exit_code == 1
