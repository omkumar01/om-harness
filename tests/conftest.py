"""Shared test fixtures: hermetic user-home isolation for every test.

Tests must never read or write the developer's real ~/.om-harness.
Because the offline echo model is no longer auto-selected (mock was removed
from the provider registry and routing entirely), tests that need a runnable
model without network access explicitly configure ``mock:echo`` as their
default via this fixture. Individual tests can still point OM_HARNESS_HOME
elsewhere via the `home` fixture or monkeypatch.
"""

from __future__ import annotations

from typing import Any

import pytest


def _write_mock_default(home_dir: Any) -> None:
    config = home_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.toml").write_text(
        '[routing]\ndefault_model = "mock:echo"\n', encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _isolated_user_home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: Any) -> Any:
    home_dir = tmp_path_factory.mktemp("om-home")
    monkeypatch.setenv("OM_HARNESS_HOME", str(home_dir))
    # Keep skill/plugin discovery hermetic too: tests must never see the
    # developer's real ~/.agents/skills or installed plugins. Tests that
    # need skills/plugins point these env vars at their own fixtures.
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(home_dir / "skills"))
    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(home_dir / "plugins"))
    _write_mock_default(home_dir)
    return home_dir
