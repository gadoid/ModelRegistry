"""CLI integration tests for `gimbal prism resource`."""
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


def test_resource_add_and_list(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "resource", "add", str(p),
        "--name", "redis", "--kind", "mock", "--image", "redis:7",
        "--port", "6379:6379",
    ])
    assert r.exit_code == 0
    r = runner.invoke(prism_app, ["resource", "list", str(p)])
    assert r.exit_code == 0
    assert "redis" in r.stdout


def test_resource_remove(tmp_path):
    p = _scenario_file(tmp_path)
    runner.invoke(prism_app, [
        "resource", "add", str(p), "--name", "redis", "--kind", "mock",
    ])
    r = runner.invoke(prism_app, ["resource", "remove", str(p), "--name", "redis"])
    assert r.exit_code == 0
    sc = core.load_scenario(p)
    assert "redis" not in sc.get("resource", {})


def test_resource_remove_exit_code_6(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["resource", "remove", str(p), "--name", "ghost"])
    assert r.exit_code == 6
