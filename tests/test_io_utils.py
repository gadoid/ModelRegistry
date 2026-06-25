"""Unit tests for gimbal.io_utils.iter_ndjson_lines."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gimbal.io_utils import iter_ndjson_lines


FIXTURES = Path(__file__).parent / "fixtures"


def test_iter_ndjson_lines_happy_path():
    events = list(iter_ndjson_lines(FIXTURES / "sample_captures.ndjson"))
    assert len(events) == 3
    assert events[0]["method"] == "POST"
    assert events[0]["path"] == "/api/login"


def test_iter_ndjson_lines_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(iter_ndjson_lines(tmp_path / "nope.ndjson"))


def test_iter_ndjson_lines_empty_file_raises(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.write_text("")
    with pytest.raises(ValueError, match="no events"):
        list(iter_ndjson_lines(p))


def test_iter_ndjson_lines_minimal_fixture():
    events = list(iter_ndjson_lines(FIXTURES / "minimal_captures.ndjson"))
    assert len(events) == 1
    assert events[0]["method"] == "GET"
    assert events[0]["path"] == "/health"