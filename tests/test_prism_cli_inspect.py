"""CLI integration tests for `gimbal prism inspect`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_inspect_text_output():
    result = runner.invoke(prism_app, ["inspect", "-i", str(FIXTURES / "sample_captures.ndjson")])
    assert result.exit_code == 0
    assert "events: 3" in result.stdout
    assert "POST" in result.stdout
    assert "GET" in result.stdout


def test_inspect_json_output():
    result = runner.invoke(prism_app, ["inspect", "-i", str(FIXTURES / "sample_captures.ndjson"), "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["event_count"] == 3
    assert data["method_counts"]["POST"] == 1


def test_inspect_exit_code_2_missing(tmp_path):
    result = runner.invoke(prism_app, ["inspect", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2
