"""Shared unit-test fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import _write_mock_default


@pytest.fixture
def home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Redirect the om-harness user home (~/.om-harness) into the test dir.

    Pre-seeded with the offline mock default so tests that run without an
    injected model keep working.
    """
    home_dir = tmp_path / "om-home"
    monkeypatch.setenv("OM_HARNESS_HOME", str(home_dir))
    _write_mock_default(home_dir)
    return home_dir
