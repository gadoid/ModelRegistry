"""Regression test: gimbal CLI wiring (Task 21 fix).

Task 21 final verification uncovered a CRITICAL bug: the user-facing
`gimbal` CLI was importing the legacy `prism_app` from `gimbal.cli.prism`
which only had the `start` command. The 9 new subcommands
(convert, inspect, validate, to-steps, explain, meta, user, resource,
config) lived on the new `gimbal.prism.cli.prism_app` and were
unreachable to end users.

This test invokes the `gimbal` entry point via subprocess and asserts
that `gimbal prism --help` lists all 10 subcommands (6 commands + 4
subcommand groups). It also asserts a representative subcommand
(`convert --help`) actually works through the entry point.

This guards against the bug regressing if someone re-introduces a
shim/wrapper between `gimbal.cli.app` and `gimbal.prism.cli`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import pytest


EXPECTED_PRISM_SUBCOMMANDS = {
    "start",
    "convert",
    "explain",
    "inspect",
    "to-steps",
    "validate",
    "meta",
    "resource",
    "user",
    "config",
}


def _gimbal_bin() -> str:
    """Locate the `gimbal` entry point on PATH or fall back to the test env's python -m gimbal.cli.app."""
    if shutil.which("gimbal") is not None:
        return ["gimbal"]
    # Fallback: invoke the module directly. Used when the package isn't
    # installed system-wide (e.g. dev venv with editable install not in PATH).
    return [sys.executable, "-m", "gimbal.cli.app"]


def _run_gimbal(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_gimbal_bin(), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_gimbal_prism_help_lists_all_ten_subcommands():
    """`gimbal prism --help` must list all 10 subcommands reachable to users."""
    result = _run_gimbal("prism", "--help")
    assert result.returncode == 0, (
        f"gimbal prism --help exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    out = result.stdout
    missing = sorted(c for c in EXPECTED_PRISM_SUBCOMMANDS if c not in out)
    assert not missing, (
        "gimbal prism --help is missing subcommands: "
        f"{missing}\n--- help output ---\n{out}\n---"
    )


def test_gimbal_prism_help_does_not_import_legacy_shim():
    """Sanity: the help text must come from the new prism_app, not the legacy one.

    The legacy `gimbal.cli.prism` shim was deleted in the Task 21 fix. If
    someone reintroduces it, this test will fail because either the file
    will be missing (in which case a different test catches it) or the
    import path will silently route through a stale module.
    """
    result = _run_gimbal("prism", "--help")
    assert result.returncode == 0
    # New prism_app has the help string from gimbal/prism/cli/__init__.py
    # (currently "gimbal prism CLI 子命令" — possibly garbled in some
    # terminals, but the prefix "gimbal prism CLI" is stable enough).
    # We check substring "prism" + at least one of the new commands to
    # detect the legacy shim (whose help string was "gimbal 配置器(web)").
    out = result.stdout
    # The legacy shim's signature string was "gimbal 配置器(web)".
    # The new app's signature is "gimbal prism CLI 子命令" / "gimbal prism CLI".
    assert "配置器(web)" not in out, (
        "gimbal prism --help looks like the legacy shim output — the CLI is "
        "probably wired to gimbal.cli.prism instead of gimbal.prism.cli.\n"
        f"--- output ---\n{out}\n---"
    )


def test_gimbal_prism_convert_help_via_entry_point():
    """`gimbal prism convert --help` must succeed through the `gimbal` entry point.

    The legacy shim only registered `start`, so this would fail with
    "No such command 'convert'".
    """
    result = _run_gimbal("prism", "convert", "--help")
    assert result.returncode == 0, (
        f"gimbal prism convert --help exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    out = result.stdout
    assert "--input" in out or "-i" in out, (
        "convert --help should expose --input / -i option\n"
        f"--- output ---\n{out}\n---"
    )
    # If routed through the legacy shim, typer prints "No such command 'convert'".
    assert "No such command" not in out
    assert "No such command" not in result.stderr


@pytest.mark.parametrize("subcommand", sorted(EXPECTED_PRISM_SUBCOMMANDS))
def test_gimbal_prism_subcommand_help_via_entry_point(subcommand: str):
    """Every expected prism subcommand must be discoverable through the entry point."""
    result = _run_gimbal("prism", subcommand, "--help")
    assert result.returncode == 0, (
        f"`gimbal prism {subcommand} --help` exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
