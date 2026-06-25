"""Unit tests for gimbal.prism.core."""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.prism import core

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