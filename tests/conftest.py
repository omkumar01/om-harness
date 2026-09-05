"""Shared test fixtures: hermetic user-home isolation for every test.

Tests must never read or write the developer's real ~/.om-harness.
Individual tests can still point OM_HARNESS_HOME elsewhere via the `home`
fixture or monkeypatch.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: Any) -> None:
    monkeypatch.setenv("OM_HARNESS_HOME", str(tmp_path_factory.mktemp("om-home")))
