# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-07

First stable release of the om-harness coding-agent harness.

### Added

- **Interactive shell** (`om-harness` / `chat`): one-input-box, always-on status
  line (model · thinking · mode · context gauge), keybindings, slash commands
  with autocomplete, and an arrow-key model selector.
- **Live streaming**: agent thinking, tool calls, file-change diffs, and shell
  command output render in real time during a turn.
- **`/timeout` slash command** (and `/config set agent_timeout|tool_timeout
  <seconds|off>`): show, set, or disable the whole-turn agent timeout and the
  per-tool-call timeout. `off`/`0` → `None`, which `asyncio.timeout` and
  `wait_for` treat as no timeout; changes apply live and persist to
  `~/.om-harness/config/config.toml`.
- **Skills**: instruction packs (`SKILL.md`) discovered from `~/.agents/skills`,
  the repo's `.agents/skills`, config extra dirs, and installed plugins; loaded
  on demand via a read-only `skill` tool.
- **Plugins**: git-installable (`om-harness install`, `plugins`, `uninstall`)
  into `~/.om-harness/plugins`, with provenance records and shallow updates.
- **Orchestration**: plan-as-data strategies, topological wave scheduling with a
  concurrency semaphore, retries with backoff, and per-task timeouts.
- **Tool safety**: argv-list execution, shell-metacharacter rejection, hard
  timeouts, output caps, scrubbed environment, and strict repo-root path
  confinement (the `skill` tool is the sole documented exemption — name, not
  path).
- **Durable state**: SQLite-backed sessions, tasks, and checkpoints; JSONL
  event log; crash-atomic writes; secret redaction at publish time.
- **Web client**: reference HTML UI with SSE event streaming.
- **Config**: TOML files (`om-harness.toml` / `pyproject.toml`), env-var
  overrides, and `/config set` with immediate live application.

### Fixed

- **Live-stream freeze**: the REPL live pump drained the event bus by positional
  offset into a 1000-event bounded deque; streaming token deltas (one per delta)
  crossed that cap at ~4800 characters and froze the view while the agent kept
  running. Events now carry a monotonic `seq` and consumers drain via
  `bus.cursor` / `bus.since()`, which is immune to history eviction; history
  window raised to 10,000.
- **Bottom status bar disappearing during streaming**: it was a prompt
  `bottom_toolbar`, which only exists while `prompt()` is active. A turn now runs
  a minimal pinned app (toolbar-only layout, refreshed each second) under
  `patch_stdout` so output scrolls above the bar; fails safely back to the
  previous plain-await behavior on non-TTY or unsupported terminals.

## [Unreleased]

<!-- Add new entries here, above the latest release. -->
