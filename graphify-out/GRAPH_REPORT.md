# Graph Report - .  (2026-09-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1439 nodes · 3750 edges · 67 communities (60 shown, 7 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 377 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2983b296`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app.py
- Harness
- test_models_json.py
- EventBus
- test_repl.py
- plugins/__init__.py
- SkillTool
- load_config
- TaskResult
- Task
- ProviderRegistry
- runner.py
- harness.py
- LocalStore
- test_shell.py
- ChatRepl
- ContextAssembler
- EventType
- providers/registry.py
- ToolResult
- test_cli.py
- test_runner.py
- ToolContext
- RepoIndex
- files.py
- test_tools_files.py
- test_tools_system.py
- repl.py
- test_approval.py
- ._render_event
- .run_turn
- mock.py
- apply_config_update
- user_settings.py
- shell.py
- BaseTool
- slash.py
- tools/__init__.py
- ._cmd_setup
- Coordinator
- ContextLedger
- _write_mock_default
- test_local_gateway.py
- store.py
- SlashCompleter
- test_models.py
- status_bar
- test_model_selection.py
- _FakePromptSession
- check.py
- header_line
- test_shift_tab_binding_key_is_valid
- test_no_binding_conflicts_with_enter
- om-harness
- BaseModel
- Exception

## God Nodes (most connected - your core abstractions)
1. `ChatRepl` - 83 edges
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
- `demo()` --calls--> `event_to_display()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `outcome_to_summary()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `TerminalRenderer`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/terminal.py
- `_Doc` --uses--> `Verbosity`  [INFERRED]
  tests/unit/test_shell.py → src/om_harness/config/loader.py
- `_Repl` --uses--> `Verbosity`  [INFERRED]
  tests/unit/test_shell.py → src/om_harness/config/loader.py

## Import Cycles
- None detected.

## Communities (67 total, 7 thin omitted)

### Community 0 - "app.py"
Cohesion: 0.05
Nodes (67): Context, agent(), _build_harness(), chat(), config_show(), doctor(), init(), install() (+59 more)

### Community 1 - "Harness"
Cohesion: 0.05
Nodes (60): demo(), main(), make_sample_repo(), FunctionModel, Path, End-to-end demo without API keys: a scripted "coder" model performs a real codin, A model script: read the file, fix the bug, run tests, then summarize., scripted_coder_model() (+52 more)

### Community 2 - "test_models_json.py"
Cohesion: 0.05
Nodes (58): CustomModelSpec, CustomProviderSpec, _is_local_or_private_host(), load_models_json(), ModelCost, ModelsJsonConfig, ModelsJsonError, BaseModel (+50 more)

### Community 3 - "EventBus"
Cohesion: 0.05
Nodes (40): Queue, _is_sensitive_key(), Any, Secret redaction: credentials never reach events, logs, or checkpoints., Replaces known secret values and obviously-secret keys with a marker.      Appli, Recursively redact strings in dicts/lists/tuples and by key name., SecretRedactor, Event (+32 more)

### Community 4 - "test_repl.py"
Cohesion: 0.09
Nodes (60): _pinned_repl(), Any, Harness, Tests for the chat REPL logic (input loop mocked, harness is real)., Thinking deltas stream inline and the line is closed before the reply., A REPL whose scripted model runs one shell command then replies., /model with no args opens the selector; without a TTY it no-ops safely., A turn whose scripted model edits a file shows the activity line. (+52 more)

### Community 5 - "plugins/__init__.py"
Cohesion: 0.08
Nodes (35): install_plugin(), load_plugin(), load_plugins(), merge_plugin_skills(), _name_from_url(), parse_source(), Plugin, PluginError (+27 more)

### Community 6 - "SkillTool"
Cohesion: 0.08
Nodes (35): discover_skills(), load_skill_body(), parse_skill_md(), BaseModel, Path, Skill discovery: SKILL.md files parsed into small, loadable units.  A skill is a, Compact prompt-ready listing: one line per skill., One discovered skill: identifying frontmatter plus its SKILL.md path. (+27 more)

### Community 7 - "load_config"
Cohesion: 0.08
Nodes (41): _apply_env(), _config_table(), ConfigError, _deep_merge(), load_config(), parse_timeout(), Any, Exception (+33 more)

### Community 8 - "TaskResult"
Cohesion: 0.14
Nodes (28): RoleLiteral, Core runtime contracts (Pydantic models, events, sessions)., Checkpoint, Message, MessageRole, BaseModel, StrEnum, Session, message, run, and checkpoint contracts.  Checkpoints store *compact sta (+20 more)

### Community 9 - "Task"
Cohesion: 0.13
Nodes (31): HarnessConfig, Plan, BaseModel, Deterministic topological order (declaration order breaks ties)., A unit of work assigned to one agent invocation., An execution plan produced by the planner or the model itself., Task, Planner (+23 more)

### Community 10 - "ProviderRegistry"
Cohesion: 0.09
Nodes (35): Task-type -> model routing with explicit user overrides., RoutingConfig, ProviderRegistry, Names of providers registered via models.json (sorted)., ModelRouter, Model routing: pick the right model per task type, with overrides.  Order of pre, Pick from whichever provider has a key; strong/cheap per task type., Primary model plus configured fallbacks, all validated. (+27 more)

### Community 11 - "runner.py"
Cohesion: 0.09
Nodes (29): BaseModel, BudgetConfig, Optional per-run ceilings; ``None`` means unlimited for that axis., AssembledContext, Scoped context assembly: small role prompts, selective history, reports.  Design, Everything one agent invocation will receive, plus its token report., Execute one goal end-to-end: plan, coordinate, persist, checkpoint., make_event() (+21 more)

### Community 12 - "harness.py"
Cohesion: 0.10
Nodes (28): ApprovalConfig, ApprovalPolicy, ContextConfig, BaseModel, StrEnum, Harness configuration: TOML files + environment variables, validated.  Precedenc, Context-minimization knobs (see context.assembler)., Skill/plugin discovery knobs (see skills and plugins packages). (+20 more)

### Community 13 - "LocalStore"
Cohesion: 0.09
Nodes (22): _atomic_write_json(), LocalStore, Exception, Path, Raised for missing, corrupt, or unwritable persistent state., File-backed session/event/checkpoint store rooted at one directory., All sessions, most recently updated first., StoreError (+14 more)

### Community 14 - "test_shell.py"
Cohesion: 0.10
Nodes (35): add_custom_provider(), Register a custom provider in ~/.om-harness/config/models.json.      Validates t, Map a thinking level to provider model settings.      Graceful degradation by de, thinking_settings(), _completions(), _Doc, Any, Contract tests for the interactive-shell building blocks: thinking settings mapp (+27 more)

### Community 15 - "ChatRepl"
Cohesion: 0.09
Nodes (9): ChatRepl, Harness, Arrow-key model picker; falls back gracefully without a TTY., Re-print a recorded command's output inline, capped., Alt+O handler and /output command: re-open executed command output.          Wit, True (after warning) when plan mode owns the thing being changed., Handle a /command; returns False if it should go to the agent., TerminalRenderer (+1 more)

### Community 16 - "ContextAssembler"
Cohesion: 0.12
Nodes (26): HarnessConfig, Message, RepoIndex, Skill, ContextAssembler, Tiny listing of available skills; empty when none are installed., Compact, structured rendering of prior agent outputs (no transcripts)., Extractive, model-free summary of older conversation turns. (+18 more)

### Community 17 - "EventType"
Cohesion: 0.12
Nodes (22): Console, Verbosity, RunOutcome, EventType, StrEnum, Namespaced event categories. Values are stable API for UI consumers., DisplayLine, LineLevel (+14 more)

### Community 18 - "providers/registry.py"
Cohesion: 0.09
Nodes (20): ModelSpec, ProviderInfo, ProviderSpec, BaseModel, Provider abstraction built on PydanticAI's already-unified model interface.  om-, Runtime view of a provider: availability and its known models., A parsed ``provider:model`` string., Static description of a supported provider. (+12 more)

### Community 19 - "ToolResult"
Cohesion: 0.10
Nodes (25): cap_text(), Structured tool outcome returned to the model and the event log., Truncate text to ``limit`` chars, appending a notice when cut., ToolResult, GitAdd, GitAddArgs, GitCommit, GitCommitArgs (+17 more)

### Community 20 - "test_cli.py"
Cohesion: 0.17
Nodes (27): Wrap a registry tool as a PydanticAI tool via the guarded executor., _invoke(), _make_git_plugin(), Any, MonkeyPatch, Contract tests for the CLI: commands, exit codes, and --json output.  Uses Typer, Running bare `om-harness` must start an interactive chat session., repo() (+19 more)

### Community 21 - "test_runner.py"
Cohesion: 0.13
Nodes (22): GuardedToolExecutor, Name-keyed catalog of available tools with schema introspection., JSON-friendly tool descriptions (for UIs and model schemas)., The only path the agent runtime uses to execute tools.      Sequence per call: v, ToolRegistry, Any, FunctionModel, Contract tests for the agent runtime runner (PydanticAI bridge, events, timeouts (+14 more)

### Community 22 - "ToolContext"
Cohesion: 0.15
Nodes (28): Shared execution context handed to every tool instance., ToolContext, RunShell, ctx(), pipe(), Any, Contract tests for native pipeline support in the run_shell tool.  Pipes run as, A quoted `python -c ...` fragment that parses cross-platform. (+20 more)

### Community 23 - "RepoIndex"
Cohesion: 0.11
Nodes (18): _cache_file(), _CachePayload, FileEntry, BaseModel, Path, Repository index: a compact, cached file map used for context scoping.  The inde, Drop the in-memory index and any persisted cache entry., Compact text form for a system/user prompt, with a tail marker. (+10 more)

### Community 24 - "files.py"
Cohesion: 0.15
Nodes (18): Exception, Path, Raised by tools for expected failures (bad input, timeout, ...)., Resolve ``path_str`` strictly inside the repository root., resolve_in_repo(), ToolError, EditFileArgs, iter_repo_files() (+10 more)

### Community 25 - "test_tools_files.py"
Cohesion: 0.15
Nodes (19): EditFile, ListFiles, ReadFile, SearchFiles, ctx(), Any, Contract tests for file tools: list/read/write/edit/search + path safety., test_edit_file_errors_on_ambiguous_match() (+11 more)

### Community 26 - "test_tools_system.py"
Cohesion: 0.12
Nodes (23): GitStatus, build_env(), Any, Snapshot os.environ minus anything that looks like a credential., Run an argv list; returns (returncode, stdout, stderr, truncated).      ``input_, run_process(), detect_test_runner(), BaseModel (+15 more)

### Community 27 - "repl.py"
Cohesion: 0.14
Nodes (13): _enable_vt_output(), _PinnedBar, Interactive shell for `om-harness` — Claude-Code-style, uniquely om.  One input, State for the bottom-row status bar pin active during one turn., Make sure stdout accepts ANSI escape sequences.      POSIX terminals always do., Await a turn with the status bar pinned to the terminal bottom.          ``botto, Reserve the terminal's bottom row for the status bar.          Returns the pin s, Repaint the bar row (outside the scroll region).          Save/restore wraps the (+5 more)

### Community 28 - "test_approval.py"
Cohesion: 0.23
Nodes (20): ctx(), _engine(), _executor(), Any, Contract tests for the approval engine and guarded tool executor.  Key safety pr, test_allowlist_policy(), test_ask_policy_gates_both(), test_auto_policy_approves_mutating_but_gates_destructive() (+12 more)

### Community 29 - "._render_event"
Cohesion: 0.11
Nodes (12): Event, Exception, CommandRun, _ModelSelectorRequested, Internal signal: Ctrl+M pressed inside the prompt., One executed command, kept so its output can be re-opened later., Report a live-stream failure without ending the turn., Flush partial (end="") writes to the terminal.          Rich only auto-flushes o (+4 more)

### Community 30 - ".run_turn"
Cohesion: 0.16
Nodes (8): (provider, model) that the NEXT turn will actually use.          Goes through th, One user turn: live-render events and stream the reply., Terminate an open partial line (text/thinking printed with end="")., Inline-stream state for one turn.      Tracks both text (for reply de-duplicatio, _TurnStream, mode_glyph(), thinking_glyph(), test_glyphs()

### Community 31 - "mock.py"
Cohesion: 0.14
Nodes (16): Agent, ScriptFn, make_echo_model(), make_scripted_model(), make_tool_call_then_answer(), Any, FunctionModel, Mock provider: scripted models for deterministic tests and offline demos.  Wraps (+8 more)

### Community 32 - "apply_config_update"
Cohesion: 0.26
Nodes (17): apply_config_update(), Apply one ``/config set`` update to the live config and persist it.      Returns, harness(), Any, Contract tests for live config updates persisted to ~/.om-harness., test_disable_timeouts_round_trips_off(), test_invalid_enum_value_rejected(), test_invalid_key_rejected() (+9 more)

### Community 33 - "user_settings.py"
Cohesion: 0.21
Nodes (16): apply_model(), available_model_strings(), _deep_merge(), _dump_toml(), load_user_overrides(), persist_updates(), Any, User-level settings persistence: /config set writes to ~/.om-harness.  Values ar (+8 more)

### Community 34 - "shell.py"
Cohesion: 0.23
Nodes (10): _find_unquoted_metachar(), _parse_stage(), BaseModel, Process execution: the shell tool and the shared async subprocess helper.  Safet, Split on ``|`` outside of quotes., First shell-control character outside of quotes, if any.      Metacharacters ins, Parse one pipeline stage: argv plus optional 2>&1 and > / >> redirect., RunShellArgs (+2 more)

### Community 35 - "BaseTool"
Cohesion: 0.20
Nodes (5): ArgsT, BaseTool, Any, BaseModel, Base class for all tools.      Subclasses declare a module-level ``Args`` pydant

### Community 36 - "slash.py"
Cohesion: 0.17
Nodes (15): args_hint_for(), cycle(), cycle_approval(), cycle_thinking(), cycle_verbosity(), find_command(), Slash-command registry and typing hints for the interactive shell.  Shared by th, Inline hint for the slash command currently being typed, if any. (+7 more)

### Community 37 - "tools/__init__.py"
Cohesion: 0.18
Nodes (11): Permission, StrEnum, Tool system foundation: permissions, context, results, and the base class.  Ever, BaseModel, Environment/repository inspection (read-only)., RepoInfo, RepoInfoArgs, build_default_registry() (+3 more)

### Community 38 - "._cmd_setup"
Cohesion: 0.18
Nodes (6): _PlainSession, Any, Guided configuration: provider → model → mode → verbosity → thinking., Optionally add a custom OpenAI-compatible provider. True to continue., Fallback prompt for terminals where prompt_toolkit cannot attach.      Still pri, PromptSession with keybindings, completer, and live status bar.          If prom

### Community 39 - "Coordinator"
Cohesion: 0.26
Nodes (6): Protocol, Semaphore, Coordinator, The runner seam the coordinator depends on (AgentRunner implements it)., Run the whole plan; returns results in deterministic plan order., TaskExecutor

### Community 40 - "ContextLedger"
Cohesion: 0.20
Nodes (7): ContextLedger, ContextReport, estimate_tokens(), BaseModel, Token accounting: estimation heuristic and per-run context ledger., What was sent to the model, by component, in estimated tokens., Accumulates estimated token counts per context component.

### Community 41 - "_write_mock_default"
Cohesion: 0.23
Nodes (10): _isolated_user_home(), Any, MonkeyPatch, Shared test fixtures: hermetic user-home isolation for every test.  Tests must n, _write_mock_default(), home(), Any, MonkeyPatch (+2 more)

### Community 42 - "test_local_gateway.py"
Cohesion: 0.33
Nodes (8): _chunk(), _gateway_app(), gateway_url(), Any, FastAPI, End-to-end test: om-harness against a real local OpenAI-compatible gateway (in-p, Start the OpenAI-compatible gateway on an ephemeral localhost port., test_run_against_local_gateway_via_models_json()

### Community 43 - "store.py"
Cohesion: 0.25
Nodes (11): datetime, _utcnow(), Durable local persistence: JSON sessions, JSONL events, checkpoint files.  Layou, _manager(), Any, Contract tests for the session manager (lifecycle, messages, checkpoints)., test_add_message_updates_and_persists(), test_create_session_publishes_and_persists() (+3 more)

### Community 44 - "SlashCompleter"
Cohesion: 0.38
Nodes (4): Completer, Any, Autocomplete slash commands and their arguments with descriptions., SlashCompleter

### Community 45 - "test_models.py"
Cohesion: 0.29
Nodes (5): Contract tests for core Pydantic runtime models., test_event_has_identity_and_defaults(), test_event_roundtrip_preserves_type(), test_task_result_defaults_are_compact(), test_token_usage_add()

### Community 46 - "status_bar"
Cohesion: 0.33
Nodes (6): Ten-segment context gauge: ▮▮▮▯▯▯ 3k/20k., Always-on status line: approval mode, provider, model, thinking,     context gau, status_bar(), usage_bar(), test_status_bar_always_shows_provider_model_thinking_mode(), test_usage_bar_rendering()

### Community 47 - "test_model_selection.py"
Cohesion: 0.50
Nodes (4): Any, Regression test: selecting a custom models.json model in the interactive shell m, repo_with_custom_provider(), test_selected_model_reaches_the_runner()

### Community 50 - "header_line"
Cohesion: 0.67
Nodes (3): header_line(), Top border of the input box with state baked in., test_header_line_shows_state()

## Knowledge Gaps
- **1 isolated node(s):** `om-harness`
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ChatRepl` connect `ChatRepl` to `app.py`, `test_repl.py`, `._cmd_setup`, `SlashCompleter`, `test_shell.py`, `_FakePromptSession`, `repl.py`, `._render_event`, `.run_turn`?**
  _High betweenness centrality (0.136) - this node is a cross-community bridge._
- **Why does `Harness` connect `Harness` to `app.py`, `test_models_json.py`, `EventBus`, `plugins/__init__.py`, `SkillTool`, `TaskResult`, `Task`, `ProviderRegistry`, `runner.py`, `harness.py`, `LocalStore`, `test_shell.py`, `ContextAssembler`, `EventType`, `RepoIndex`, `apply_config_update`, `Coordinator`, `test_local_gateway.py`, `test_model_selection.py`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Why does `ToolContext` connect `ToolContext` to `Harness`, `BaseTool`, `tools/__init__.py`, `SkillTool`, `harness.py`, `ToolResult`, `test_runner.py`, `files.py`, `test_tools_files.py`, `test_tools_system.py`, `test_approval.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `ChatRepl` (e.g. with `SlashCompleter` and `_FakePromptSession`) actually correct?**
  _`ChatRepl` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Harness` (e.g. with `ApprovalPolicy` and `HarnessConfig`) actually correct?**
  _`Harness` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `EventBus` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`EventBus` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Task` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`Task` has 15 INFERRED edges - model-reasoned connections that need verification._