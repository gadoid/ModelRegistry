"""CLI integration tests for `gimbal prism to-steps`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_to_steps_to_stdout():
    result = runner.invoke(prism_app, ["to-steps", "-i", str(FIXTURES / "minimal_captures.ndjson")])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "api" in data[0]


def test_to_steps_to_file(tmp_path):
    out = tmp_path / "steps.json"
    result = runner.invoke(prism_app, [
        "to-steps", "-i", str(FIXTURES / "minimal_captures.ndjson"), "-o", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_to_steps_exit_code_2(tmp_path):
    result = runner.invoke(prism_app, ["to-steps", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2
