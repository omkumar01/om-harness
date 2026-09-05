"""Cross-platform verification entry point: the same checks CI runs.

Usage: uv run python scripts/check.py [--fast]

Runs, in order: ruff format --check, ruff check, mypy, pytest (with coverage
enforcement). ``--fast`` skips coverage. Exits non-zero on the first failure.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="skip coverage enforcement")
    fast = parser.parse_args().fast

    failures: list[str] = []

    print("\n=== ruff format --check ===", flush=True)
    if subprocess.run(
        ["uv", "run", "ruff", "format", "--check", "."], cwd=ROOT, shell=False
    ).returncode:
        failures.append("ruff format --check")

    print("\n=== ruff check ===", flush=True)
    if subprocess.run(["uv", "run", "ruff", "check", "."], cwd=ROOT, shell=False).returncode:
        failures.append("ruff check")

    print("\n=== mypy ===", flush=True)
    if subprocess.run(["uv", "run", "mypy", "src"], cwd=ROOT, shell=False).returncode:
        failures.append("mypy")

    print("\n=== pytest ===", flush=True)
    if fast:
        pytest_rc = subprocess.run(["uv", "run", "pytest"], cwd=ROOT, shell=False).returncode
    else:
        pytest_rc = subprocess.run(
            ["uv", "run", "pytest", "--cov=om_harness", "--cov-fail-under=85", "--cov-report=term"],
            cwd=ROOT,
            shell=False,
        ).returncode
    if pytest_rc:
        failures.append("pytest")

    if failures:
        print("\nFAILED: " + ", ".join(failures))
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
