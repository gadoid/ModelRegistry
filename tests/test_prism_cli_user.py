"""CLI integration tests for `gimbal prism user`."""
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


def test_user_add_and_list(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "user", "add", str(p), "--key", "admin",
        "--url", "https://x", "--username", "admin", "--password", "secret",
    ])
    assert r.exit_code == 0
    r = runner.invoke(prism_app, ["user", "list", str(p)])
    assert r.exit_code == 0
    assert "admin" in r.stdout


def test_user_remove(tmp_path):
    p = _scenario_file(tmp_path)
    runner.invoke(prism_app, [
        "user", "add", str(p), "--key", "ops", "--username", "ops",
    ])
    r = runner.invoke(prism_app, ["user", "remove", str(p), "--key", "ops"])
    assert r.exit_code == 0
    sc = core.load_scenario(p)
    assert "ops" not in sc["config"]["users"]


def test_user_remove_exit_code_6(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["user", "remove", str(p), "--key", "ghost"])
    assert r.exit_code == 6
