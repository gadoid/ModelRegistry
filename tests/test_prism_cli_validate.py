"""CLI integration tests for `gimbal prism validate`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_validate_ok():
    result = runner.invoke(prism_app, ["validate", "-c", str(FIXTURES / "sample_config.yaml")])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_validate_exit_code_4_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario_id: x\nname: ''\n")
    result = runner.invoke(prism_app, ["validate", "-c", str(bad)])
    assert result.exit_code == 4


def test_validate_exit_code_2_missing(tmp_path):
    result = runner.invoke(prism_app, ["validate", "-c", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
