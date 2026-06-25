"""CLI integration tests for `gimbal prism config`."""
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


def test_config_get(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["config", "get", str(p), "--field", "timePolicy"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data is not None


def test_config_set_time_policy(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "config", "set", str(p),
        "--time-policy-kind", "timeout", "--time-policy-seconds", "120",
    ])
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    sc = core.load_scenario(p)
    assert sc["config"]["timePolicy"]["kind"] == "timeout"
    assert sc["config"]["timePolicy"]["seconds"] == 120


def test_config_set_retry(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "config", "set", str(p),
        "--retry-enabled",
        "--retry-max-attempts", "5",
        "--retry-backoff-seconds", "10.5",
    ])
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    sc = core.load_scenario(p)
    assert sc["config"]["retry"] is not None
    assert sc["config"]["retry"]["maxAttempts"] == 5
    assert sc["config"]["retry"]["backoffSeconds"] == 10.5


def test_config_set_retry_disable(tmp_path):
    p = _scenario_file(tmp_path)
    # 先启用 retry
    runner.invoke(prism_app, [
        "config", "set", str(p),
        "--retry-enabled", "--retry-max-attempts", "3",
    ])
    # 再禁用 retry
    r = runner.invoke(prism_app, [
        "config", "set", str(p), "--no-retry-enabled",
    ])
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    sc = core.load_scenario(p)
    assert sc["config"]["retry"] is None


def test_config_set_no_fields(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["config", "set", str(p)])
    assert r.exit_code == 1
