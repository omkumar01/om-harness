# Contributing to om-harness

Thanks for your interest! This guide gets you from clone to first merged
PR. It also documents the practices the codebase follows so new code looks
like old code.

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.11+ (any of
3.11/3.12/3.13).

```bash
git clone https://github.com/om-harness/om-harness
cd om-harness
uv sync                 # creates .venv and installs everything
uv run om-harness --version
uv run pytest           # the full suite runs offline — no API keys needed
```

With provider keys set (`OPENAI_API_KEY`, …) you can also run the live
integration round-trips:

```bash
uv run pytest -m integration
```

## Quality gates

All PRs must pass the same checks CI runs (Linux + Windows, Python 3.11 and
3.13):

```bash
make check          # or: uv run python scripts/check.py
```

which runs, in order:

1. `uv run ruff format --check .`
2. `uv run ruff check .`
3. `uv run mypy src`
4. `uv run pytest --cov=om_harness --cov-fail-under=85`

Auto-fix formatting/lint before committing:

```bash
make format         # ruff format + ruff check --fix
```

## Test-driven development

This project is developed test-first. Before implementing a module or
behavior, its contract is expressed as tests; implementation is the minimum
that passes them, then refactoring. Practically:

- tests live in `tests/unit/` (mirroring `src/om_harness/` layout),
  `tests/e2e/` (complete flows in temp git repos), and
  `tests/integration/` (live provider round-trips, deselected by default);
- the default suite must stay **deterministic and offline** — provider
  calls are scripted with PydanticAI `FunctionModel`/`TestModel`, which
  exercise the real agent loop without network;
- async race coverage uses sentinels + `asyncio.wait_for`, never real
  sleeps.

When fixing a bug: add the failing test that reproduces it first.

## Architecture rules

These are enforced in review (see [docs/architecture.md](docs/architecture.md)):

- `models/` and `config/` are pure: no I/O, no imports from runtime layers.
- Runtime services depend on each other through narrow protocols (e.g.
  `Coordinator` depends on the `TaskExecutor` protocol, not `AgentRunner`).
- Presentation (`cli/`, `ui/`) touches the runtime only via
  `harness.Harness` and the event stream.
- Provider SDK imports live only inside `providers/registry.make_model`.
- Every user-visible runtime operation publishes a typed `Event`.

## Common tasks

### Add a tool

1. Define the tool in `src/om_harness/tools/<area>.py`:

```python
class FormatCodeArgs(BaseModel):
    path: str = Field(description="Repo-relative path")

class FormatCode(BaseTool[FormatCodeArgs]):
    name = "format_code"
    description = "Run the repository formatter on one file."
    permission = Permission.mutating
    Args = FormatCodeArgs

    async def run(self, args: FormatCodeArgs) -> ToolResult:
        path = resolve_in_repo(self.ctx, args.path)
        ...
        return ToolResult(output=f"formatted {args.path}")
```

2. Register it in `tools/build_default_registry`.
3. Add tests: happy path, permission gating (`read_only`/`mutating`/
   `destructive`), error paths, path confinement.

### Add a provider

1. Add a `ProviderSpec` to `PROVIDERS` in `src/om_harness/providers/base.py`
   (prefix, env keys, default/strong models).
2. Add a construction branch in `providers/registry.make_model`.
3. Add a registry test (availability, parsing) and an integration test in
   `tests/integration/` gated on the env key.

### Add an orchestration strategy

1. Extend `StrategyKind` and the planner heuristic.
2. Prefer expressing the strategy as plan *shape* (tasks + dependencies);
   only add coordinator behavior when the pattern truly isn't a DAG
   property.
3. Add deterministic scheduling tests (see the sentinel pattern in
   `tests/unit/test_orchestration.py`).

### Change a runtime contract

Contracts live in `src/om_harness/models/`. They are versioned API for
sessions/checkpoints on disk and event consumers, so:

- keep changes additive where possible,
- if serialization changes, bump `HarnessConfig.version` and note a
  migration in the PR description.

## Running the CLI locally

```bash
uv run om-harness init
uv run om-harness run "summarize this repo" -v
uv run om-harness chat
# web reference client (needs the `web` extra):
uv sync --extra web
uv run python -m om_harness.ui.web.server
```

om-harness state lives in `.om-harness/` of whatever repository you're in —
safe to delete at any time.

## Commit / PR conventions

- Small, focused PRs with tests.
- Conventional commit style is appreciated (`feat:`, `fix:`, `docs:`,
  `refactor:`, `test:`, `chore:`).
- The CI must be green before review.

## Reporting issues

Include: the command run, `om-harness doctor --json` output, the relevant
`.om-harness/events/*.jsonl` excerpt (redacted automatically), and expected
vs. actual behavior. **Never paste API keys** — om-harness redacts its own
logs; check before you paste anything manually.
