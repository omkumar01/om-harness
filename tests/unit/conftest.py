"""Shared unit-test fixtures."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Redirect the om-harness user home (~/.om-harness) into the test dir."""
    home_dir = tmp_path / "om-home"
    monkeypatch.setenv("OM_HARNESS_HOME", str(home_dir))
    return home_dir
