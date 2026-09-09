# Graph Report - .  (2026-09-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1451 nodes · 3741 edges · 90 communities (78 shown, 12 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 374 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2ef167aa`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_repl.py
- plugins/__init__.py
- ApprovalEngine
- SkillTool
- task.py
- Harness
- ToolContext
- Task
- tools/__init__.py
- ContextAssembler
- LocalStore
- runner.py
- harness.py
- app.py
- files.py
- test_cli.py
- git.py
- TaskType
- RepoIndex
- shell.py
- ChatRepl
- EventBus
- components.py
- loader.py
- .run_forever
- ProviderRegistry
- Any
- ProviderError
- test_models_json.py
- paths.py
- ModelRouter
- slash.py
- mock.py
- apply_config_update
- ModelsJsonConfig
- test_shell.py
- .run_turn
- test_tools_files.py
- ._pin_bar_setup
- SecretRedactor
- validate_provider_url
- load_config
- load_models_json
- repl.py
- test_paths.py
- providers/registry.py
- event_to_display
- test_user_config.py
- ContextLedger
- _write_mock_default
- test_web.py
- demo
- events.py
- test_local_gateway.py
- test_session_manager.py
- EventReader
- test_models.py
- SlashCompleter
- ._enqueue
- ._status_bar
- EventCollector
- status_bar
- ._cmd_output
- run_app
- TurnActivity
- test_model_selection.py
- .__init__
- ValueError
- ._show_file_change
- main
- check.py
- header_line
- om_harness/__init__.py
- .cursor
- om-harness
- BaseModel
- Any
- Exception
- Harness

## God Nodes (most connected - your core abstractions)
1. `ChatRepl` - 86 edges
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

## Communities (90 total, 12 thin omitted)

### Community 0 - "test_repl.py"
Cohesion: 0.08
Nodes (62): _FakePromptSession, _pinned_repl(), Any, Harness, Tests for the chat REPL logic (input loop mocked, harness is real)., Thinking deltas stream inline and the line is closed before the reply., A REPL whose scripted model runs one shell command then replies., /model with no args opens the selector; without a TTY it no-ops safely. (+54 more)

### Community 1 - "plugins/__init__.py"
Cohesion: 0.08
Nodes (37): Installed plugins root: $OM_HARNESS_PLUGINS_DIR or ~/.om-harness/plugins., user_plugins_dir(), install_plugin(), load_plugin(), load_plugins(), merge_plugin_skills(), _name_from_url(), parse_source() (+29 more)

### Community 2 - "ApprovalEngine"
Cohesion: 0.08
Nodes (43): ApprovalEngine, Confirmer, GuardedToolExecutor, Name-keyed catalog of available tools with schema introspection., Trim large argument payloads before they hit the event log., JSON-friendly tool descriptions (for UIs and model schemas)., The only path the agent runtime uses to execute tools.      Sequence per call: v, ToolRegistry (+35 more)

### Community 3 - "SkillTool"
Cohesion: 0.08
Nodes (35): discover_skills(), load_skill_body(), parse_skill_md(), BaseModel, Path, Skill discovery: SKILL.md files parsed into small, loadable units.  A skill is a, Compact prompt-ready listing: one line per skill., One discovered skill: identifying frontmatter plus its SKILL.md path. (+27 more)

### Community 4 - "task.py"
Cohesion: 0.12
Nodes (30): datetime, RoleLiteral, make_event(), Any, Convenience constructor: keyword args become the ``data`` payload., Core runtime contracts (Pydantic models, events, sessions)., Checkpoint, Message (+22 more)

### Community 5 - "Harness"
Cohesion: 0.09
Nodes (35): Harness, Any, Confirmer, Path, Discover skills: user dir, config extra dirs, then repo (repo wins).          In, Prepare a repository: state dir + gitignore entry (idempotent)., Execute one goal end-to-end: plan, coordinate, persist, checkpoint., One interactive chat turn. Errors surface in the reply text. (+27 more)

### Community 6 - "ToolContext"
Cohesion: 0.11
Nodes (41): Shared execution context handed to every tool instance., ToolContext, RunShell, ctx(), pipe(), Any, Contract tests for native pipeline support in the run_shell tool.  Pipes run as, A quoted `python -c ...` fragment that parses cross-platform. (+33 more)

### Community 7 - "Task"
Cohesion: 0.15
Nodes (30): HarnessConfig, Plan, BaseModel, Deterministic topological order (declaration order breaks ties)., A unit of work assigned to one agent invocation., An execution plan produced by the planner or the model itself., Task, Planner (+22 more)

### Community 8 - "tools/__init__.py"
Cohesion: 0.09
Nodes (22): ArgsT, ApprovalDecision, StrEnum, Approval policy engine: decides whether a tool may run.  Policies (see ``config., Final verdict: may the tool execute?, BaseTool, Permission, Any (+14 more)

### Community 9 - "ContextAssembler"
Cohesion: 0.12
Nodes (26): HarnessConfig, Message, RepoIndex, Skill, ContextAssembler, Tiny listing of available skills; empty when none are installed., Compact, structured rendering of prior agent outputs (no transcripts)., Extractive, model-free summary of older conversation turns. (+18 more)

### Community 10 - "LocalStore"
Cohesion: 0.09
Nodes (22): _atomic_write_json(), LocalStore, Exception, Path, Raised for missing, corrupt, or unwritable persistent state., File-backed session/event/checkpoint store rooted at one directory., All sessions, most recently updated first., StoreError (+14 more)

### Community 11 - "runner.py"
Cohesion: 0.11
Nodes (24): BaseModel, BudgetConfig, Optional per-run ceilings; ``None`` means unlimited for that axis., AssembledContext, Scoped context assembly: small role prompts, selective history, reports.  Design, Everything one agent invocation will receive, plus its token report., AgentFactory, extract_thinking() (+16 more)

### Community 12 - "harness.py"
Cohesion: 0.15
Nodes (20): Protocol, Semaphore, DoctorItem, DoctorReport, BaseModel, Harness: the composition root binding config, providers, tools, runtime, orchest, RunOutcome, EventType (+12 more)

### Community 13 - "app.py"
Cohesion: 0.11
Nodes (29): agent(), _build_harness(), config_show(), doctor(), init(), install(), _json_payload(), plugins() (+21 more)

### Community 14 - "files.py"
Cohesion: 0.11
Nodes (24): Repository index: a compact, cached file map used for context scoping.  The inde, cap_text(), Exception, Path, Raised by tools for expected failures (bad input, timeout, ...)., Resolve ``path_str`` strictly inside the repository root., Truncate text to ``limit`` chars, appending a notice when cut., resolve_in_repo() (+16 more)

### Community 15 - "test_cli.py"
Cohesion: 0.17
Nodes (27): Wrap a registry tool as a PydanticAI tool via the guarded executor., _invoke(), _make_git_plugin(), Any, MonkeyPatch, Contract tests for the CLI: commands, exit codes, and --json output.  Uses Typer, Running bare `om-harness` must start an interactive chat session., repo() (+19 more)

### Community 16 - "git.py"
Cohesion: 0.13
Nodes (19): GitAdd, GitAddArgs, GitCommit, GitCommitArgs, GitDiff, GitDiffArgs, GitLog, GitLogArgs (+11 more)

### Community 17 - "TaskType"
Cohesion: 0.14
Nodes (25): ApprovalPolicy, StrEnum, Model reasoning effort; mapped per provider by the runner.      off    — no thin, ThinkingLevel, Verbosity, apply_model(), available_model_strings(), _deep_merge() (+17 more)

### Community 18 - "RepoIndex"
Cohesion: 0.11
Nodes (17): _cache_file(), _CachePayload, FileEntry, BaseModel, Path, Drop the in-memory index and any persisted cache entry., Compact text form for a system/user prompt, with a tail marker., Cached, bounded listing of repository files. (+9 more)

### Community 19 - "shell.py"
Cohesion: 0.11
Nodes (22): build_env(), _find_unquoted_metachar(), _parse_stage(), Any, BaseModel, Process execution: the shell tool and the shared async subprocess helper.  Safet, Split on ``|`` outside of quotes., First shell-control character outside of quotes, if any.      Metacharacters ins (+14 more)

### Community 20 - "ChatRepl"
Cohesion: 0.13
Nodes (4): ChatRepl, Handle a /command; returns False if it should go to the agent., True (after warning) when plan mode owns the thing being changed., Save the last assistant message (the plan) to .om-harness/plans/plan<N>.md.

### Community 21 - "EventBus"
Cohesion: 0.16
Nodes (19): Event, BaseModel, One observable runtime occurrence. Small, flat, and JSON-friendly., EventBus, Fan-out event hub with bounded history and publish-time redaction., Events published after ``cursor``.          Cursor-based, so draining stays corr, MonkeyPatch, Contract tests for the async event bus (fan-out, ordering, redaction). (+11 more)

### Community 22 - "components.py"
Cohesion: 0.14
Nodes (13): Console, DisplayLine, LineLevel, outcome_to_summary(), BaseModel, StrEnum, Reusable presentation primitives shared by terminal and web clients.  These comp, Plain-text body of the welcome panel (renderer wraps it in a Panel). (+5 more)

### Community 23 - "loader.py"
Cohesion: 0.14
Nodes (20): _apply_env(), ApprovalConfig, _config_table(), ConfigError, ContextConfig, _deep_merge(), parse_timeout(), Any (+12 more)

### Community 24 - ".run_forever"
Cohesion: 0.12
Nodes (8): Any, _PlainSession, Arrow-key model picker; falls back gracefully without a TTY., Guided configuration: provider → model → mode → verbosity → thinking., Optionally add a custom OpenAI-compatible provider. True to continue., Fallback prompt for terminals where prompt_toolkit cannot attach.      Still pri, PromptSession with keybindings, completer, and live status bar.          If prom, Prepend the last assistant message (the plan) to the approval.          This ens

### Community 25 - "ProviderRegistry"
Cohesion: 0.16
Nodes (19): ProviderRegistry, Names of providers registered via models.json (sorted)., Contract tests for the provider layer: registry, availability, routing, and the, With no providers configured, routing returns the default and the     runner fai, Constructing model objects must not require network access., _router(), test_auto_route_prefers_available_providers(), test_explicit_override_wins() (+11 more)

### Community 26 - "Any"
Cohesion: 0.14
Nodes (20): add_custom_provider(), Register a custom provider in ~/.om-harness/config/models.json.      Validates t, Any, Selecting a model whose provider is unavailable must produce a clear     error i, Even without prompt_toolkit, the header + status render per prompt., _repl_for(), test_add_custom_provider_merges_with_existing(), test_add_custom_provider_rejects_bad_names() (+12 more)

### Community 27 - "ProviderError"
Cohesion: 0.14
Nodes (11): _local_http_client(), ProviderError, Any, Exception, First real provider with a key, or None when nothing is configured.          The, The HTTP endpoint a model string would talk to (for diagnostics)., Build the client for a models.json provider, or None if unavailable., Build a PydanticAI model instance, or None if unavailable.          Imports are (+3 more)

### Community 28 - "test_models_json.py"
Cohesion: 0.18
Nodes (17): load_config_from_dict(), Contract tests for custom model providers configured via ``models.json``.  Cover, Helper: validate a dict through the same path the loader uses., _registry(), test_builtin_name_collision_rejected(), test_custom_availability_inline_or_env_or_local(), test_custom_provider_names_and_summaries_are_sorted_and_json_ready(), test_duplicate_model_ids_rejected() (+9 more)

### Community 29 - "paths.py"
Cohesion: 0.20
Nodes (17): chat(), launch_interactive(), Interactive chat session (same as running bare `om-harness`)., First-class default: `om-harness` drops you into a chat session., ensure_user_dirs(), Path, User-level storage layout under ``~/.om-harness`` (config + caches).  Layout::, The om-harness user root: $OM_HARNESS_HOME or ~/.om-harness. (+9 more)

### Community 30 - "ModelRouter"
Cohesion: 0.15
Nodes (14): Task-type -> model routing with explicit user overrides., RoutingConfig, ModelRouter, Model routing: pick the right model per task type, with overrides.  Order of pre, Pick from whichever provider has a key; strong/cheap per task type., Primary model plus configured fallbacks, all validated., The regression: /model selections must reach the runner even when     auto_route, A models.json provider selected as default must be used directly. (+6 more)

### Community 31 - "slash.py"
Cohesion: 0.14
Nodes (18): args_hint_for(), cycle(), cycle_approval(), cycle_thinking(), cycle_verbosity(), find_command(), mode_glyph(), Slash-command registry and typing hints for the interactive shell.  Shared by th (+10 more)

### Community 32 - "mock.py"
Cohesion: 0.14
Nodes (16): Agent, ScriptFn, make_echo_model(), make_scripted_model(), make_tool_call_then_answer(), Any, FunctionModel, Mock provider: scripted models for deterministic tests and offline demos.  Wraps (+8 more)

### Community 33 - "apply_config_update"
Cohesion: 0.26
Nodes (17): apply_config_update(), Apply one ``/config set`` update to the live config and persist it.      Returns, harness(), Any, Contract tests for live config updates persisted to ~/.om-harness., test_disable_timeouts_round_trips_off(), test_invalid_enum_value_rejected(), test_invalid_key_rejected() (+9 more)

### Community 34 - "ModelsJsonConfig"
Cohesion: 0.12
Nodes (12): CustomModelSpec, CustomProviderSpec, ModelCost, ModelsJsonConfig, BaseModel, Inline key first, then the referenced environment variable., Local gateways need no key; remote ones need inline or env key., Top-level ``models.json`` document. (+4 more)

### Community 35 - "test_shell.py"
Cohesion: 0.16
Nodes (17): Map a thinking level to provider model settings.      Graceful degradation by de, thinking_settings(), _completions(), Contract tests for the interactive-shell building blocks: thinking settings mapp, Regression: 'backtab' is an invalid key name on some platforms and     used to a, Ctrl+M is physically the same key as Enter; binding the model     selector to it, test_completer_arg_completion_for_thinking(), test_completer_config_keys() (+9 more)

### Community 36 - ".run_turn"
Cohesion: 0.17
Nodes (9): Event, Inline-stream state for one turn.      Tracks both text (for reply de-duplicatio, One user turn: live-render events and stream the reply., Report a live-stream failure without ending the turn., Terminate an open partial line (text/thinking printed with end="")., Flush partial (end="") writes to the terminal.          Rich only auto-flushes o, Live-render new events while the turn runs (polling drain)., Render an executed command with a collapsed output preview.          Returns Tru (+1 more)

### Community 37 - "test_tools_files.py"
Cohesion: 0.19
Nodes (16): EditFile, ListFiles, ReadFile, ctx(), Any, Contract tests for file tools: list/read/write/edit/search + path safety., test_edit_file_errors_on_ambiguous_match(), test_edit_file_errors_when_not_found() (+8 more)

### Community 38 - "._pin_bar_setup"
Cohesion: 0.18
Nodes (10): _PinnedBar, State for the bottom-row status bar pin active during one turn., Await a turn with the status bar pinned to the terminal bottom.          ``botto, Reserve the terminal's bottom row for the status bar.          Returns the pin s, Repaint the bar row (outside the scroll region).          Save/restore wraps the, Reset the scroll region and erase the bar row., Repaint the bar each tick; survives a mid-turn terminal resize., Write raw ANSI straight to the terminal, bypassing rich styling. (+2 more)

### Community 39 - "SecretRedactor"
Cohesion: 0.14
Nodes (10): _is_sensitive_key(), Any, Secret redaction: credentials never reach events, logs, or checkpoints., Replaces known secret values and obviously-secret keys with a marker.      Appli, Recursively redact strings in dicts/lists/tuples and by key name., SecretRedactor, MonkeyPatch, test_redactor_from_env() (+2 more)

### Community 40 - "validate_provider_url"
Cohesion: 0.13
Nodes (14): _is_local_or_private_host(), ModelsJsonError, Exception, URL safety, name collisions, API kinds, duplicate model ids., True for loopback, private, link-local, reserved, or local-suffix hosts., Enforce the URL safety policy; returns the URL when acceptable.      - scheme mu, Raised for malformed, unsafe, or inconsistent models.json content., validate_provider_url() (+6 more)

### Community 41 - "load_config"
Cohesion: 0.25
Nodes (14): load_config(), Load, validate, and merge harness configuration.      Raises ``ConfigError`` for, Any, Contract tests for configuration loading and secret redaction., test_defaults(), test_env_overrides_file(), test_explicit_config_path(), test_invalid_policy_raises() (+6 more)

### Community 42 - "load_models_json"
Cohesion: 0.21
Nodes (14): load_models_json(), Path, Discover, parse, merge, and validate models.json; None if absent.      Sources,, Any, MonkeyPatch, _repo_with_models_json(), test_doctor_reports_models_json(), test_doctor_without_models_json_is_ok() (+6 more)

### Community 43 - "repl.py"
Cohesion: 0.15
Nodes (9): Exception, _enable_vt_output(), _ModelSelectorRequested, Interactive shell for `om-harness` — Claude-Code-style, uniquely om.  One input, Make sure stdout accepts ANSI escape sequences.      POSIX terminals always do., Internal signal: Ctrl+M pressed inside the prompt., _FakeSession, End-to-end smoke test for /plan mode (uses the mock:echo model, no network).  Dr (+1 more)

### Community 44 - "test_paths.py"
Cohesion: 0.28
Nodes (12): User-level skills: $OM_HARNESS_SKILLS_DIR or ~/.agents/skills., user_skills_dir(), home(), Any, MonkeyPatch, Contract tests for user-level storage (~/.om-harness) and paths., test_user_home_defaults_to_dot_om_harness(), test_user_home_honors_env_override() (+4 more)

### Community 45 - "providers/registry.py"
Cohesion: 0.18
Nodes (9): ModelSpec, ProviderInfo, ProviderSpec, BaseModel, Provider abstraction built on PydanticAI's already-unified model interface.  om-, Runtime view of a provider: availability and its known models., A parsed ``provider:model`` string., Static description of a supported provider. (+1 more)

### Community 46 - "event_to_display"
Cohesion: 0.19
Nodes (12): _describe(), event_to_display(), Map an event to a display line, or None if filtered by verbosity.      MESSAGE_D, ChatRequest, create_app(), main(), BaseModel, FastAPI (+4 more)

### Community 47 - "test_user_config.py"
Cohesion: 0.33
Nodes (12): Any, Path, Contract tests for config precedence (defaults < user < repo < env) and cross-so, _remote_provider(), test_env_models_json_wins_as_source(), test_env_overrides_both_levels(), test_global_and_repo_models_json_merge(), test_nested_table_merge() (+4 more)

### Community 48 - "ContextLedger"
Cohesion: 0.20
Nodes (7): ContextLedger, ContextReport, estimate_tokens(), BaseModel, Token accounting: estimation heuristic and per-run context ledger., What was sent to the model, by component, in estimated tokens., Accumulates estimated token counts per context component.

### Community 49 - "_write_mock_default"
Cohesion: 0.23
Nodes (10): _isolated_user_home(), Any, MonkeyPatch, Shared test fixtures: hermetic user-home isolation for every test.  Tests must n, _write_mock_default(), home(), Any, MonkeyPatch (+2 more)

### Community 50 - "test_web.py"
Cohesion: 0.31
Nodes (10): client(), Any, Web reference client API tests (FastAPI TestClient, no network)., repo(), test_chat_continues_same_session(), test_chat_roundtrip_uses_mock_provider(), test_index_serves_html(), test_recent_events_endpoint() (+2 more)

### Community 51 - "demo"
Cohesion: 0.36
Nodes (8): demo(), main(), make_sample_repo(), FunctionModel, Path, End-to-end demo without API keys: a scripted "coder" model performs a real codin, A model script: read the file, fix the bug, run tests, then summarize., scripted_coder_model()

### Community 52 - "events.py"
Cohesion: 0.25
Nodes (6): Typed event envelope: the single instrumentation spine of the harness.  Every me, _utcnow(), make_stream_handler(), AgentFactory: turns harness specs into PydanticAI Agent instances.  The bridge b, Event-stream handler: PydanticAI stream events -> MESSAGE_DELTA events.      Bot, Asynchronous event bus: one publish point, many subscribers.  Runtime components

### Community 53 - "test_local_gateway.py"
Cohesion: 0.33
Nodes (8): _chunk(), _gateway_app(), gateway_url(), Any, FastAPI, End-to-end test: om-harness against a real local OpenAI-compatible gateway (in-p, Start the OpenAI-compatible gateway on an ephemeral localhost port., test_run_against_local_gateway_via_models_json()

### Community 54 - "test_session_manager.py"
Cohesion: 0.50
Nodes (8): _manager(), Any, Contract tests for the session manager (lifecycle, messages, checkpoints)., test_add_message_updates_and_persists(), test_create_session_publishes_and_persists(), test_list_and_latest_sessions(), test_run_lifecycle(), test_save_checkpoint_emits_event_and_persists()

### Community 55 - "EventReader"
Cohesion: 0.32
Nodes (3): EventReader, Async iterator over events published after subscription., Collect exactly ``count`` events; raises on timeout.

### Community 56 - "test_models.py"
Cohesion: 0.25
Nodes (6): Contract tests for core Pydantic runtime models., test_event_has_identity_and_defaults(), test_event_roundtrip_preserves_type(), test_task_result_defaults_are_compact(), test_task_result_roundtrip(), test_token_usage_add()

### Community 57 - "SlashCompleter"
Cohesion: 0.38
Nodes (4): Completer, Any, Autocomplete slash commands and their arguments with descriptions., SlashCompleter

### Community 60 - "EventCollector"
Cohesion: 0.33
Nodes (3): EventCollector, Any, Test/diagnostic helper that records every event passing through.

### Community 61 - "status_bar"
Cohesion: 0.33
Nodes (6): Ten-segment context gauge: ▮▮▮▯▯▯ 3k/20k., Always-on status line: approval mode, provider, model, thinking,     context gau, status_bar(), usage_bar(), test_status_bar_always_shows_provider_model_thinking_mode(), test_usage_bar_rendering()

### Community 62 - "._cmd_output"
Cohesion: 0.33
Nodes (4): CommandRun, One executed command, kept so its output can be re-opened later., Re-print a recorded command's output inline, capped., Alt+O handler and /output command: re-open executed command output.          Wit

### Community 63 - "run_app"
Cohesion: 0.40
Nodes (4): Console-script entry point: dispatch the Typer application., run_app(), Regression test: the console-script entry point must dispatch the app.  At one p, test_run_app_entry_point_exists()

### Community 64 - "TurnActivity"
Cohesion: 0.40
Nodes (4): What one chat turn actually did — files, commands, tokens., Derive the concrete activity of one turn from its event segment., turn_activity(), TurnActivity

### Community 65 - "test_model_selection.py"
Cohesion: 0.50
Nodes (4): Any, Regression test: selecting a custom models.json model in the interactive shell m, repo_with_custom_provider(), test_selected_model_reaches_the_runner()

### Community 66 - ".__init__"
Cohesion: 0.50
Nodes (3): Harness, TerminalRenderer, Verbosity

### Community 69 - "main"
Cohesion: 0.67
Nodes (3): Context, main(), om-harness: orchestrate coding agents in your repository.      Run without a sub

### Community 71 - "header_line"
Cohesion: 0.67
Nodes (3): header_line(), Top border of the input box with state baked in., test_header_line_shows_state()

## Knowledge Gaps
- **1 isolated node(s):** `om-harness`
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ChatRepl` connect `ChatRepl` to `test_repl.py`, `.__init__`, `.run_turn`, `._show_file_change`, `._pin_bar_setup`, `repl.py`, `app.py`, `TaskType`, `.run_forever`, `Any`, `._status_bar`, `paths.py`, `._cmd_output`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Why does `Harness` connect `Harness` to `plugins/__init__.py`, `ApprovalEngine`, `SkillTool`, `task.py`, `Task`, `ContextAssembler`, `LocalStore`, `runner.py`, `harness.py`, `app.py`, `TaskType`, `RepoIndex`, `EventBus`, `ProviderRegistry`, `Any`, `ModelRouter`, `apply_config_update`, `SecretRedactor`, `load_models_json`, `event_to_display`, `demo`, `test_local_gateway.py`, `test_model_selection.py`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `EventBus` connect `EventBus` to `plugins/__init__.py`, `ApprovalEngine`, `task.py`, `Harness`, `SecretRedactor`, `tools/__init__.py`, `.cursor`, `LocalStore`, `runner.py`, `harness.py`, `Task`, `events.py`, `test_session_manager.py`, `._enqueue`, `EventCollector`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `ChatRepl` (e.g. with `_FakeSession` and `_TurnWatcher`) actually correct?**
  _`ChatRepl` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Harness` (e.g. with `ApprovalPolicy` and `HarnessConfig`) actually correct?**
  _`Harness` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `EventBus` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`EventBus` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Task` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`Task` has 15 INFERRED edges - model-reasoned connections that need verification._