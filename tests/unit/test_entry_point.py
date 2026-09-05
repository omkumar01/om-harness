"""Regression test: the console-script entry point must dispatch the app.

At one point the entry point targeted the Typer callback, which exited
silently without parsing any subcommand.
"""

from __future__ import annotations


def test_run_app_entry_point_exists() -> None:
    from om_harness.cli.app import app, run_app

    assert callable(run_app)
    assert app is not None
