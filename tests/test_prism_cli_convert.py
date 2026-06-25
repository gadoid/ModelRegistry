"""CLI integration tests for `gimbal prism convert`."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_convert_basic_to_stdout():
    result = runner.invoke(
        prism_app, ["convert", "-i", str(FIXTURES / "minimal_captures.ndjson")],
    )
    assert result.exit_code == 0
    assert "scenarioId:" in result.stdout


def test_convert_with_config_to_file(tmp_path):
    out = tmp_path / "out.yaml"
    result = runner.invoke(prism_app, [
        "convert",
        "-i", str(FIXTURES / "minimal_captures.ndjson"),
        "-c", str(FIXTURES / "sample_config.yaml"),
        "-o", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    assert "scenarioId: sc_sample" in out.read_text(encoding="utf-8")


def test_convert_exit_code_2_missing_input(tmp_path):
    result = runner.invoke(prism_app, ["convert", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2


def test_convert_exit_code_3_empty_ndjson(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.write_text("")
    result = runner.invoke(prism_app, ["convert", "-i", str(p)])
    assert result.exit_code == 3