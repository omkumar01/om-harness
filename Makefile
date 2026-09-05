.PHONY: check format lint type tests coverage e2e clean

# Full verification suite (same commands CI runs).
check:
	uv run python scripts/check.py

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

type:
	uv run mypy src

tests:
	uv run pytest

coverage:
	uv run pytest --cov=om_harness --cov-report=term-missing

e2e:
	uv run pytest tests/e2e -v

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist
