# Graph Report - .  (2026-09-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1449 nodes · 3737 edges · 90 communities (81 shown, 9 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 374 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1240c1fb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_repl.py
- harness.py
- .__init__
- plugins/__init__.py
- Task
- ContextAssembler
- runner.py
- EventType
- EventBus
- tools/__init__.py
- test_cli.py
- LocalStore
- files.py
- ToolContext
- RepoIndex
- TaskType
- app.py
- ChatRepl
- ApprovalEngine
- DoctorReport
- ProviderRegistry
- test_tools_system.py
- test_approval.py
- Any
- test_harness.py
- server.py
- test_models_json.py
- paths.py
- ModelRouter
- slash.py
- mock.py
- .run_forever
- load_config
- apply_config_update
- providers/registry.py
- test_shell.py
- test_runner.py
- ToolResult
- .run_turn
- test_tools_files.py
- shell.py
- ._pin_bar_setup
- repl.py
- TaskResult
- loader.py
- validate_provider_url
- Permission
- models_json.py
- .make_model
- test_user_config.py
- ContextLedger
- _write_mock_default
- _build_harness
- test_coding_flow.py
- demo
- Harness
- test_local_gateway.py
- test_session_manager.py
- EventReader
- test_models.py
- SlashCompleter
- ._status_bar
- status_bar
- ._cmd_output
- run_app
- BaseModel
- ModelsJsonConfig
- test_model_selection.py
- .__init__
- ValueError
- ._show_file_change
- main
- check.py
- header_line
- om-harness
- BaseModel
- Any
- Exception
- Harness

## God Nodes (most connected - your core abstractions)
1. `ChatRepl` - 85 edges
2. `Harness` - 79 edges
3. `EventBus` - 72 edges
4. `ToolContext` - 65 edges
5. `Task` - 57 edges
6. `ProviderRegistry` - 57 edges
7. `Event` - 48 edges
8. `HarnessConfig` - 43 edges
9. `Plan` - 42 edges
10. `EventType` - 38 edges

## Surprising Connections (you probably didn't know these)
- `_TurnWatcher` --uses--> `ChatRepl`  [INFERRED]
  tests/smoke_test_plan_mode.py → src/om_harness/ui/repl.py
- `demo()` --calls--> `event_to_display()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `outcome_to_summary()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `TerminalRenderer`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/terminal.py
- `test_defaults()` --calls--> `HarnessConfig`  [EXTRACTED]
  tests/unit/test_config.py → src/om_harness/config/loader.py

## Import Cycles
- None detected.

## Communities (90 total, 9 thin omitted)

### Community 0 - "test_repl.py"
Cohesion: 0.08
Nodes (62): _FakePromptSession, _pinned_repl(), Any, Harness, Tests for the chat REPL logic (input loop mocked, harness is real)., Thinking deltas stream inline and the line is closed before the reply., A REPL whose scripted model runs one shell command then replies., /model with no args opens the selector; without a TTY it no-ops safely. (+54 more)

### Community 1 - "harness.py"
Cohesion: 0.09
Nodes (36): datetime, RoleLiteral, Harness: the composition root binding config, providers, tools, runtime, orchest, make_event(), Any, Typed event envelope: the single instrumentation spine of the harness.  Every me, Convenience constructor: keyword args become the ``data`` payload., _utcnow() (+28 more)

### Community 2 - ".__init__"
Cohesion: 0.07
Nodes (38): Confirmer, Path, Discover skills: user dir, config extra dirs, then repo (repo wins).          In, discover_skills(), load_skill_body(), parse_skill_md(), BaseModel, Path (+30 more)

### Community 3 - "plugins/__init__.py"
Cohesion: 0.08
Nodes (36): Installed plugins root: $OM_HARNESS_PLUGINS_DIR or ~/.om-harness/plugins., user_plugins_dir(), install_plugin(), load_plugin(), load_plugins(), merge_plugin_skills(), _name_from_url(), parse_source() (+28 more)

### Community 4 - "Task"
Cohesion: 0.15
Nodes (30): HarnessConfig, Plan, BaseModel, Deterministic topological order (declaration order breaks ties)., A unit of work assigned to one agent invocation., An execution plan produced by the planner or the model itself., Task, Planner (+22 more)

### Community 5 - "ContextAssembler"
Cohesion: 0.12
Nodes (27): HarnessConfig, Message, RepoIndex, Skill, ContextAssembler, Scoped context assembly: small role prompts, selective history, reports.  Design, Tiny listing of available skills; empty when none are installed., Compact, structured rendering of prior agent outputs (no transcripts). (+19 more)

### Community 6 - "runner.py"
Cohesion: 0.10
Nodes (27): BaseModel, BudgetConfig, Optional per-run ceilings; ``None`` means unlimited for that axis., AssembledContext, Everything one agent invocation will receive, plus its token report., TaskStatus, AgentFactory, extract_thinking() (+19 more)

### Community 7 - "EventType"
Cohesion: 0.10
Nodes (24): Console, RunOutcome, EventType, StrEnum, Namespaced event categories. Values are stable API for UI consumers., _describe(), DisplayLine, event_to_display() (+16 more)

### Community 8 - "EventBus"
Cohesion: 0.11
Nodes (23): Queue, Event, BaseModel, One observable runtime occurrence. Small, flat, and JSON-friendly., EventBus, Any, Synchronous path for non-async callers (CLI one-shots, tests)., Fan-out event hub with bounded history and publish-time redaction. (+15 more)

### Community 9 - "tools/__init__.py"
Cohesion: 0.11
Nodes (24): GitAdd, GitAddArgs, GitCommit, GitCommitArgs, GitDiff, GitDiffArgs, GitLog, GitLogArgs (+16 more)

### Community 10 - "test_cli.py"
Cohesion: 0.17
Nodes (27): Wrap a registry tool as a PydanticAI tool via the guarded executor., _invoke(), _make_git_plugin(), Any, MonkeyPatch, Contract tests for the CLI: commands, exit codes, and --json output.  Uses Typer, Running bare `om-harness` must start an interactive chat session., repo() (+19 more)

### Community 11 - "LocalStore"
Cohesion: 0.12
Nodes (19): _atomic_write_json(), LocalStore, Path, File-backed session/event/checkpoint store rooted at one directory., All sessions, most recently updated first., Any, Contract tests for the durable local store (sessions/events/checkpoints)., A leftover temp file from a crashed write is ignored on read. (+11 more)

### Community 12 - "files.py"
Cohesion: 0.12
Nodes (23): cap_text(), Exception, Path, Raised by tools for expected failures (bad input, timeout, ...)., Resolve ``path_str`` strictly inside the repository root., Truncate text to ``limit`` chars, appending a notice when cut., resolve_in_repo(), ToolError (+15 more)

### Community 13 - "ToolContext"
Cohesion: 0.13
Nodes (30): Shared execution context handed to every tool instance., ToolContext, build_default_registry(), The standard coding-agent toolset, all sharing one ToolContext., RunShell, ctx(), pipe(), Any (+22 more)

### Community 14 - "RepoIndex"
Cohesion: 0.11
Nodes (18): _cache_file(), _CachePayload, FileEntry, BaseModel, Path, Repository index: a compact, cached file map used for context scoping.  The inde, Drop the in-memory index and any persisted cache entry., Compact text form for a system/user prompt, with a tail marker. (+10 more)

### Community 15 - "TaskType"
Cohesion: 0.14
Nodes (25): ApprovalPolicy, StrEnum, Model reasoning effort; mapped per provider by the runner.      off    — no thin, ThinkingLevel, Verbosity, apply_model(), available_model_strings(), _deep_merge() (+17 more)

### Community 16 - "app.py"
Cohesion: 0.12
Nodes (23): config_show(), doctor(), init(), install(), _json_payload(), plugins(), providers(), Path (+15 more)

### Community 17 - "ChatRepl"
Cohesion: 0.14
Nodes (3): ChatRepl, True (after warning) when plan mode owns the thing being changed., Handle a /command; returns False if it should go to the agent.

### Community 18 - "ApprovalEngine"
Cohesion: 0.13
Nodes (13): AgentFactory: turns harness specs into PydanticAI Agent instances.  The bridge b, Asynchronous event bus: one publish point, many subscribers.  Runtime components, ApprovalDecision, ApprovalEngine, StrEnum, Approval policy engine: decides whether a tool may run.  Policies (see ``config., Tool system foundation: permissions, context, results, and the base class.  Ever, GuardedToolExecutor (+5 more)

### Community 19 - "DoctorReport"
Cohesion: 0.11
Nodes (13): _is_sensitive_key(), Any, Secret redaction: credentials never reach events, logs, or checkpoints., Replaces known secret values and obviously-secret keys with a marker.      Appli, Recursively redact strings in dicts/lists/tuples and by key name., SecretRedactor, DoctorItem, DoctorReport (+5 more)

### Community 20 - "ProviderRegistry"
Cohesion: 0.16
Nodes (19): ProviderRegistry, Names of providers registered via models.json (sorted)., Contract tests for the provider layer: registry, availability, routing, and the, With no providers configured, routing returns the default and the     runner fai, Constructing model objects must not require network access., _router(), test_auto_route_prefers_available_providers(), test_explicit_override_wins() (+11 more)

### Community 21 - "test_tools_system.py"
Cohesion: 0.14
Nodes (20): build_env(), Any, Snapshot os.environ minus anything that looks like a credential., Run an argv list; returns (returncode, stdout, stderr, truncated).      ``input_, run_process(), detect_test_runner(), BaseModel, Path (+12 more)

### Community 22 - "test_approval.py"
Cohesion: 0.23
Nodes (20): ctx(), _engine(), _executor(), Any, Contract tests for the approval engine and guarded tool executor.  Key safety pr, test_allowlist_policy(), test_ask_policy_gates_both(), test_auto_policy_approves_mutating_but_gates_destructive() (+12 more)

### Community 23 - "Any"
Cohesion: 0.14
Nodes (20): add_custom_provider(), Register a custom provider in ~/.om-harness/config/models.json.      Validates t, Any, Selecting a model whose provider is unavailable must produce a clear     error i, Even without prompt_toolkit, the header + status render per prompt., _repl_for(), test_add_custom_provider_merges_with_existing(), test_add_custom_provider_rejects_bad_names() (+12 more)

### Community 24 - "test_harness.py"
Cohesion: 0.21
Nodes (18): Prepare a repository: state dir + gitignore entry (idempotent)., Any, MonkeyPatch, Contract tests for the Harness composition root (the CLI/web entry point)., CI-style default: no approvals possible, so writes are refused., repo(), test_approval_ask_non_interactive_denies_writes(), test_doctor_reports_environment() (+10 more)

### Community 25 - "server.py"
Cohesion: 0.15
Nodes (18): ChatRequest, create_app(), main(), BaseModel, FastAPI, Path, Web reference client: FastAPI app exposing the same runtime as the CLI.  This mo, Build the web app bound to one repository. (+10 more)

### Community 26 - "test_models_json.py"
Cohesion: 0.11
Nodes (31): load_models_json(), Path, Discover, parse, merge, and validate models.json; None if absent.      Sources,, load_config_from_dict(), Any, MonkeyPatch, Contract tests for custom model providers configured via ``models.json``.  Cover, Helper: validate a dict through the same path the loader uses. (+23 more)

### Community 27 - "paths.py"
Cohesion: 0.14
Nodes (28): chat(), launch_interactive(), Interactive chat session (same as running bare `om-harness`)., First-class default: `om-harness` drops you into a chat session., ensure_user_dirs(), Path, User-level storage layout under ``~/.om-harness`` (config + caches).  Layout::, The om-harness user root: $OM_HARNESS_HOME or ~/.om-harness. (+20 more)

### Community 28 - "ModelRouter"
Cohesion: 0.15
Nodes (14): Task-type -> model routing with explicit user overrides., RoutingConfig, ModelRouter, Model routing: pick the right model per task type, with overrides.  Order of pre, Pick from whichever provider has a key; strong/cheap per task type., Primary model plus configured fallbacks, all validated., The regression: /model selections must reach the runner even when     auto_route, A models.json provider selected as default must be used directly. (+6 more)

### Community 29 - "slash.py"
Cohesion: 0.14
Nodes (18): args_hint_for(), cycle(), cycle_approval(), cycle_thinking(), cycle_verbosity(), find_command(), mode_glyph(), Slash-command registry and typing hints for the interactive shell.  Shared by th (+10 more)

### Community 30 - "mock.py"
Cohesion: 0.14
Nodes (16): Agent, ScriptFn, make_echo_model(), make_scripted_model(), make_tool_call_then_answer(), Any, FunctionModel, Mock provider: scripted models for deterministic tests and offline demos.  Wraps (+8 more)

### Community 31 - ".run_forever"
Cohesion: 0.14
Nodes (6): Any, Arrow-key model picker; falls back gracefully without a TTY., Guided configuration: provider → model → mode → verbosity → thinking., Optionally add a custom OpenAI-compatible provider. True to continue., PromptSession with keybindings, completer, and live status bar.          If prom, Prepend the last assistant message (the plan) to the approval.          This ens

### Community 32 - "load_config"
Cohesion: 0.20
Nodes (16): load_config(), Load, validate, and merge harness configuration.      Raises ``ConfigError`` for, Any, MonkeyPatch, Contract tests for configuration loading and secret redaction., test_defaults(), test_env_overrides_file(), test_explicit_config_path() (+8 more)

### Community 33 - "apply_config_update"
Cohesion: 0.26
Nodes (17): apply_config_update(), Apply one ``/config set`` update to the live config and persist it.      Returns, harness(), Any, Contract tests for live config updates persisted to ~/.om-harness., test_disable_timeouts_round_trips_off(), test_invalid_enum_value_rejected(), test_invalid_key_rejected() (+9 more)

### Community 34 - "providers/registry.py"
Cohesion: 0.14
Nodes (13): ModelSpec, ProviderInfo, ProviderSpec, BaseModel, Provider abstraction built on PydanticAI's already-unified model interface.  om-, Runtime view of a provider: availability and its known models., A parsed ``provider:model`` string., Static description of a supported provider. (+5 more)

### Community 35 - "test_shell.py"
Cohesion: 0.16
Nodes (17): Map a thinking level to provider model settings.      Graceful degradation by de, thinking_settings(), _completions(), Contract tests for the interactive-shell building blocks: thinking settings mapp, Regression: 'backtab' is an invalid key name on some platforms and     used to a, Ctrl+M is physically the same key as Enter; binding the model     selector to it, test_completer_arg_completion_for_thinking(), test_completer_config_keys() (+9 more)

### Community 36 - "test_runner.py"
Cohesion: 0.25
Nodes (17): Any, FunctionModel, Contract tests for the agent runtime runner (PydanticAI bridge, events, timeouts, A streaming model produces MESSAGE_DELTA events with kind text/thinking., PydanticAI's UsageLimits defaults request_limit to 50 when left     implicit; an, The model's tool call must flow through the guarded executor., _runner(), test_budget_maps_config_to_usage_limits() (+9 more)

### Community 37 - "ToolResult"
Cohesion: 0.15
Nodes (8): ArgsT, BaseTool, Any, BaseModel, Structured tool outcome returned to the model and the event log., Base class for all tools.      Subclasses declare a module-level ``Args`` pydant, ToolResult, Trim large argument payloads before they hit the event log.

### Community 38 - ".run_turn"
Cohesion: 0.17
Nodes (9): Event, One user turn: live-render events and stream the reply., Report a live-stream failure without ending the turn., Terminate an open partial line (text/thinking printed with end="")., Flush partial (end="") writes to the terminal.          Rich only auto-flushes o, Live-render new events while the turn runs (polling drain)., Render an executed command with a collapsed output preview.          Returns Tru, Inline-stream state for one turn.      Tracks both text (for reply de-duplicatio (+1 more)

### Community 39 - "test_tools_files.py"
Cohesion: 0.19
Nodes (16): EditFile, ListFiles, ReadFile, ctx(), Any, Contract tests for file tools: list/read/write/edit/search + path safety., test_edit_file_errors_on_ambiguous_match(), test_edit_file_errors_when_not_found() (+8 more)

### Community 40 - "shell.py"
Cohesion: 0.23
Nodes (10): _find_unquoted_metachar(), _parse_stage(), BaseModel, Process execution: the shell tool and the shared async subprocess helper.  Safet, Split on ``|`` outside of quotes., First shell-control character outside of quotes, if any.      Metacharacters ins, Parse one pipeline stage: argv plus optional 2>&1 and > / >> redirect., RunShellArgs (+2 more)

### Community 41 - "._pin_bar_setup"
Cohesion: 0.18
Nodes (10): _PinnedBar, State for the bottom-row status bar pin active during one turn., Await a turn with the status bar pinned to the terminal bottom.          ``botto, Reserve the terminal's bottom row for the status bar.          Returns the pin s, Repaint the bar row (outside the scroll region).          Save/restore wraps the, Reset the scroll region and erase the bar row., Repaint the bar each tick; survives a mid-turn terminal resize., Write raw ANSI straight to the terminal, bypassing rich styling. (+2 more)

### Community 42 - "repl.py"
Cohesion: 0.12
Nodes (11): Exception, _enable_vt_output(), _ModelSelectorRequested, _PlainSession, Interactive shell for `om-harness` — Claude-Code-style, uniquely om.  One input, Make sure stdout accepts ANSI escape sequences.      POSIX terminals always do., Internal signal: Ctrl+M pressed inside the prompt., Fallback prompt for terminals where prompt_toolkit cannot attach.      Still pri (+3 more)

### Community 43 - "TaskResult"
Cohesion: 0.23
Nodes (9): Protocol, Semaphore, Structured hand-off between agents (or agent -> coordinator).      Deliberately, TaskResult, Coordinator, Coordinator: executes a plan's task graph with bounded concurrency.  Execution m, The runner seam the coordinator depends on (AgentRunner implements it)., Run the whole plan; returns results in deterministic plan order. (+1 more)

### Community 44 - "loader.py"
Cohesion: 0.21
Nodes (14): _apply_env(), _config_table(), ConfigError, _deep_merge(), parse_timeout(), Any, Exception, Path (+6 more)

### Community 45 - "validate_provider_url"
Cohesion: 0.13
Nodes (14): _is_local_or_private_host(), ModelsJsonError, Exception, URL safety, name collisions, API kinds, duplicate model ids., True for loopback, private, link-local, reserved, or local-suffix hosts., Enforce the URL safety policy; returns the URL when acceptable.      - scheme mu, Raised for malformed, unsafe, or inconsistent models.json content., validate_provider_url() (+6 more)

### Community 46 - "Permission"
Cohesion: 0.20
Nodes (8): Final verdict: may the tool execute?, Permission, StrEnum, BaseModel, Environment/repository inspection (read-only)., RepoInfo, RepoInfoArgs, test_repo_info()

### Community 47 - "models_json.py"
Cohesion: 0.16
Nodes (10): CustomModelSpec, CustomProviderSpec, ModelCost, BaseModel, Custom model providers from a local ``models.json`` file.  This feature lets use, Inline key first, then the referenced environment variable., Local gateways need no key; remote ones need inline or env key., Relative token costs; informational (all zeros for local servers). (+2 more)

### Community 48 - ".make_model"
Cohesion: 0.17
Nodes (7): _local_http_client(), Any, First real provider with a key, or None when nothing is configured.          The, Build the client for a models.json provider, or None if unavailable., Build a PydanticAI model instance, or None if unavailable.          Imports are, An HTTP client that bypasses system proxies (for local endpoints).      A config, JSON-friendly description of configured custom providers.

### Community 50 - "test_user_config.py"
Cohesion: 0.33
Nodes (12): Any, Path, Contract tests for config precedence (defaults < user < repo < env) and cross-so, _remote_provider(), test_env_models_json_wins_as_source(), test_env_overrides_both_levels(), test_global_and_repo_models_json_merge(), test_nested_table_merge() (+4 more)

### Community 51 - "ContextLedger"
Cohesion: 0.20
Nodes (7): ContextLedger, ContextReport, estimate_tokens(), BaseModel, Token accounting: estimation heuristic and per-run context ledger., What was sent to the model, by component, in estimated tokens., Accumulates estimated token counts per context component.

### Community 52 - "_write_mock_default"
Cohesion: 0.23
Nodes (10): _isolated_user_home(), Any, MonkeyPatch, Shared test fixtures: hermetic user-home isolation for every test.  Tests must n, _write_mock_default(), home(), Any, MonkeyPatch (+2 more)

### Community 53 - "_build_harness"
Cohesion: 0.24
Nodes (10): agent(), _build_harness(), _print_events(), Any, Run one coding-agent goal end-to-end., Run a single specialist agent (no planning), or list tools., run(), ApprovalConfig (+2 more)

### Community 54 - "test_coding_flow.py"
Cohesion: 0.31
Nodes (10): Any, End-to-end tests: complete coding-agent flows in a real temp git repo, driven by, Two independent read-only questions answered concurrently., Model that: reads calc.py, edits the bug, runs tests, then answers., repo(), scripted_coder(), test_complete_coding_flow_with_mocked_model(), test_parallel_plan_fans_out_and_aggregates() (+2 more)

### Community 56 - "demo"
Cohesion: 0.36
Nodes (8): demo(), main(), make_sample_repo(), FunctionModel, Path, End-to-end demo without API keys: a scripted "coder" model performs a real codin, A model script: read the file, fix the bug, run tests, then summarize., scripted_coder_model()

### Community 57 - "Harness"
Cohesion: 0.33
Nodes (4): Harness, Any, Execute one goal end-to-end: plan, coordinate, persist, checkpoint., One interactive chat turn. Errors surface in the reply text.

### Community 58 - "test_local_gateway.py"
Cohesion: 0.33
Nodes (8): _chunk(), _gateway_app(), gateway_url(), Any, FastAPI, End-to-end test: om-harness against a real local OpenAI-compatible gateway (in-p, Start the OpenAI-compatible gateway on an ephemeral localhost port., test_run_against_local_gateway_via_models_json()

### Community 59 - "test_session_manager.py"
Cohesion: 0.50
Nodes (8): _manager(), Any, Contract tests for the session manager (lifecycle, messages, checkpoints)., test_add_message_updates_and_persists(), test_create_session_publishes_and_persists(), test_list_and_latest_sessions(), test_run_lifecycle(), test_save_checkpoint_emits_event_and_persists()

### Community 60 - "EventReader"
Cohesion: 0.32
Nodes (3): EventReader, Async iterator over events published after subscription., Collect exactly ``count`` events; raises on timeout.

### Community 61 - "test_models.py"
Cohesion: 0.25
Nodes (6): Contract tests for core Pydantic runtime models., test_event_has_identity_and_defaults(), test_event_roundtrip_preserves_type(), test_task_result_defaults_are_compact(), test_task_result_roundtrip(), test_token_usage_add()

### Community 62 - "SlashCompleter"
Cohesion: 0.38
Nodes (4): Completer, Any, Autocomplete slash commands and their arguments with descriptions., SlashCompleter

### Community 64 - "status_bar"
Cohesion: 0.33
Nodes (6): Ten-segment context gauge: ▮▮▮▯▯▯ 3k/20k., Always-on status line: approval mode, provider, model, thinking,     context gau, status_bar(), usage_bar(), test_status_bar_always_shows_provider_model_thinking_mode(), test_usage_bar_rendering()

### Community 65 - "._cmd_output"
Cohesion: 0.33
Nodes (4): CommandRun, One executed command, kept so its output can be re-opened later., Re-print a recorded command's output inline, capped., Alt+O handler and /output command: re-open executed command output.          Wit

### Community 66 - "run_app"
Cohesion: 0.40
Nodes (4): Console-script entry point: dispatch the Typer application., run_app(), Regression test: the console-script entry point must dispatch the app.  At one p, test_run_app_entry_point_exists()

### Community 67 - "BaseModel"
Cohesion: 0.40
Nodes (5): ContextConfig, BaseModel, Context-minimization knobs (see context.assembler)., Skill/plugin discovery knobs (see skills and plugins packages)., SkillsConfig

### Community 68 - "ModelsJsonConfig"
Cohesion: 0.40
Nodes (3): ModelsJsonConfig, Top-level ``models.json`` document., Inline keys, for registration with the secret redactor.

### Community 69 - "test_model_selection.py"
Cohesion: 0.50
Nodes (4): Any, Regression test: selecting a custom models.json model in the interactive shell m, repo_with_custom_provider(), test_selected_model_reaches_the_runner()

### Community 70 - ".__init__"
Cohesion: 0.50
Nodes (3): Harness, TerminalRenderer, Verbosity

### Community 73 - "main"
Cohesion: 0.67
Nodes (3): Context, main(), om-harness: orchestrate coding agents in your repository.      Run without a sub

### Community 75 - "header_line"
Cohesion: 0.67
Nodes (3): header_line(), Top border of the input box with state baked in., test_header_line_shows_state()

## Knowledge Gaps
- **1 isolated node(s):** `om-harness`
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ChatRepl` connect `ChatRepl` to `test_repl.py`, `._cmd_output`, `.run_turn`, `.__init__`, `._show_file_change`, `._pin_bar_setup`, `repl.py`, `TaskType`, `app.py`, `Any`, `paths.py`, `.run_forever`, `._status_bar`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Why does `Harness` connect `Harness` to `harness.py`, `.__init__`, `plugins/__init__.py`, `Task`, `ContextAssembler`, `runner.py`, `EventType`, `EventBus`, `LocalStore`, `RepoIndex`, `TaskType`, `app.py`, `ApprovalEngine`, `DoctorReport`, `ProviderRegistry`, `Any`, `test_harness.py`, `server.py`, `test_models_json.py`, `ModelRouter`, `apply_config_update`, `TaskResult`, `_build_harness`, `test_coding_flow.py`, `demo`, `test_local_gateway.py`, `test_model_selection.py`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `EventBus` connect `EventBus` to `harness.py`, `.__init__`, `plugins/__init__.py`, `Task`, `test_runner.py`, `runner.py`, `EventType`, `TaskResult`, `ApprovalEngine`, `DoctorReport`, `test_approval.py`, `Harness`, `test_session_manager.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `ChatRepl` (e.g. with `_FakeSession` and `_TurnWatcher`) actually correct?**
  _`ChatRepl` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Harness` (e.g. with `ApprovalPolicy` and `HarnessConfig`) actually correct?**
  _`Harness` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `EventBus` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`EventBus` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Task` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`Task` has 15 INFERRED edges - model-reasoned connections that need verification._