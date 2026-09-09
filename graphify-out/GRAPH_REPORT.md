# Graph Report - .  (2026-09-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1406 nodes · 3877 edges · 62 communities (58 shown, 4 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 455 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2fd5a0e2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50

## God Nodes (most connected - your core abstractions)
1. `Harness` - 103 edges
2. `ChatRepl` - 89 edges
3. `EventBus` - 72 edges
4. `ToolContext` - 65 edges
5. `Task` - 58 edges
6. `Event` - 57 edges
7. `ProviderRegistry` - 57 edges
8. `HarnessConfig` - 51 edges
9. `EventType` - 45 edges
10. `TaskResult` - 42 edges

## Surprising Connections (you probably didn't know these)
- `demo()` --calls--> `event_to_display()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `outcome_to_summary()`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/components.py
- `demo()` --calls--> `TerminalRenderer`  [INFERRED]
  scripts/demo.py → src/om_harness/ui/terminal.py
- `test_defaults()` --calls--> `HarnessConfig`  [EXTRACTED]
  tests/unit/test_config.py → src/om_harness/config/loader.py
- `test_skills_defaults_enabled()` --calls--> `HarnessConfig`  [EXTRACTED]
  tests/unit/test_config.py → src/om_harness/config/loader.py

## Import Cycles
- None detected.

## Communities (62 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (82): Harness, Any, Prepare a repository: state dir + gitignore entry (idempotent)., Execute one goal end-to-end: plan, coordinate, persist, checkpoint., One interactive chat turn. Errors surface in the reply text., Any, End-to-end tests: complete coding-agent flows in a real temp git repo, driven by, Two independent read-only questions answered concurrently. (+74 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (65): ensure_user_dirs(), Path, User-level storage layout under ``~/.om-harness`` (config + caches).  Layout::, The om-harness user root: $OM_HARNESS_HOME or ~/.om-harness., User-level skills: $OM_HARNESS_SKILLS_DIR or ~/.agents/skills., Installed plugins root: $OM_HARNESS_PLUGINS_DIR or ~/.om-harness/plugins., Create the user directory layout; returns True on the first run., user_cache_dir() (+57 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (63): _apply_env(), _config_table(), ConfigError, _deep_merge(), load_config(), parse_timeout(), Any, Exception (+55 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (58): CustomModelSpec, CustomProviderSpec, _is_local_or_private_host(), load_models_json(), ModelCost, ModelsJsonConfig, ModelsJsonError, BaseModel (+50 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (37): Protocol, Semaphore, HarnessConfig, Plan, BaseModel, Deterministic topological order (declaration order breaks ties)., A unit of work assigned to one agent invocation., An execution plan produced by the planner or the model itself. (+29 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (34): discover_skills(), load_skill_body(), parse_skill_md(), BaseModel, Path, Skill discovery: SKILL.md files parsed into small, loadable units.  A skill is a, Compact prompt-ready listing: one line per skill., One discovered skill: identifying frontmatter plus its SKILL.md path. (+26 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (31): datetime, RoleLiteral, Harness: the composition root binding config, providers, tools, runtime, orchest, Core runtime contracts (Pydantic models, events, sessions)., Checkpoint, Message, MessageRole, BaseModel (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (41): Context, agent(), _build_harness(), chat(), config_show(), doctor(), init(), install() (+33 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (42): user_models_json(), add_custom_provider(), Register a custom provider in ~/.om-harness/config/models.json.      Validates t, Map a thinking level to provider model settings.      Graceful degradation by de, thinking_settings(), _completions(), Any, Contract tests for the interactive-shell building blocks: thinking settings mapp (+34 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (41): Shared execution context handed to every tool instance., ToolContext, RunShell, ctx(), pipe(), Any, Contract tests for native pipeline support in the run_shell tool.  Pipes run as, A quoted `python -c ...` fragment that parses cross-platform. (+33 more)

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (10): DisplayLine, ChatRepl, Any, Arrow-key model picker; falls back gracefully without a TTY., Guided configuration: provider → model → mode → verbosity → thinking., Optionally add a custom OpenAI-compatible provider. True to continue., PromptSession with keybindings, completer, and live status bar.          If prom, Re-print a recorded command's output inline, capped. (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (23): Exception, Path, Raised by tools for expected failures (bad input, timeout, ...)., Structured tool outcome returned to the model and the event log., Resolve ``path_str`` strictly inside the repository root., resolve_in_repo(), ToolError, ToolResult (+15 more)

### Community 12 - "Community 12"
Cohesion: 0.10
Nodes (25): BudgetConfig, Optional per-run ceilings; ``None`` means unlimited for that axis., make_event(), Any, Convenience constructor: keyword args become the ``data`` payload., AgentFactory, extract_thinking(), make_stream_handler() (+17 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (22): _atomic_write_json(), LocalStore, Exception, Path, Raised for missing, corrupt, or unwritable persistent state., File-backed session/event/checkpoint store rooted at one directory., All sessions, most recently updated first., StoreError (+14 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (30): Completer, ApprovalPolicy, ContextConfig, BaseModel, StrEnum, Harness configuration: TOML files + environment variables, validated.  Precedenc, Context-minimization knobs (see context.assembler)., Skill/plugin discovery knobs (see skills and plugins packages). (+22 more)

### Community 15 - "Community 15"
Cohesion: 0.11
Nodes (24): _cache_file(), _CachePayload, FileEntry, BaseModel, Path, Repository index: a compact, cached file map used for context scoping.  The inde, Drop the in-memory index and any persisted cache entry., Compact text form for a system/user prompt, with a tail marker. (+16 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (20): ApprovalConfig, ApprovalDecision, ApprovalEngine, Confirmer, StrEnum, Approval policy engine: decides whether a tool may run.  Policies (see ``config., Final verdict: may the tool execute?, Permission (+12 more)

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (20): AssembledContext, ContextAssembler, BaseModel, Scoped context assembly: small role prompts, selective history, reports.  Design, Tiny listing of available skills; empty when none are installed., Compact, structured rendering of prior agent outputs (no transcripts)., Extractive, model-free summary of older conversation turns., Everything one agent invocation will receive, plus its token report. (+12 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (21): Event, BaseModel, One observable runtime occurrence. Small, flat, and JSON-friendly., EventBus, Synchronous path for non-async callers (CLI one-shots, tests)., Fan-out event hub with bounded history and publish-time redaction., Sequence number of the most recently published event (0 if none)., Events published after ``cursor``.          Cursor-based, so draining stays corr (+13 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (21): cap_text(), Truncate text to ``limit`` chars, appending a notice when cut., GitAdd, GitAddArgs, GitCommit, GitCommitArgs, GitDiff, GitDiffArgs (+13 more)

### Community 20 - "Community 20"
Cohesion: 0.20
Nodes (25): _invoke(), _make_git_plugin(), Any, MonkeyPatch, Contract tests for the CLI: commands, exit codes, and --json output.  Uses Typer, Running bare `om-harness` must start an interactive chat session., repo(), test_agent_command_lists_tools() (+17 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (21): RunOutcome, EventType, StrEnum, Namespaced event categories. Values are stable API for UI consumers., _describe(), event_to_display(), LineLevel, outcome_to_summary() (+13 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (22): build_env(), _find_unquoted_metachar(), _parse_stage(), Any, BaseModel, Process execution: the shell tool and the shared async subprocess helper.  Safet, Split on ``|`` outside of quotes., First shell-control character outside of quotes, if any.      Metacharacters ins (+14 more)

### Community 23 - "Community 23"
Cohesion: 0.22
Nodes (21): WriteFile, ctx(), _engine(), _executor(), Any, Contract tests for the approval engine and guarded tool executor.  Key safety pr, test_allowlist_policy(), test_ask_policy_gates_both() (+13 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (15): available_model_strings(), All selectable model strings with a status label, for the selector UI., args_hint_for(), cycle(), cycle_approval(), cycle_thinking(), cycle_verbosity(), find_command() (+7 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (7): _local_http_client(), Any, First real provider with a key, or None when nothing is configured.          The, Build the client for a models.json provider, or None if unavailable., Build a PydanticAI model instance, or None if unavailable.          Imports are, An HTTP client that bypasses system proxies (for local endpoints).      A config, JSON-friendly description of configured custom providers.

### Community 26 - "Community 26"
Cohesion: 0.16
Nodes (19): ProviderRegistry, Names of providers registered via models.json (sorted)., Contract tests for the provider layer: registry, availability, routing, and the, With no providers configured, routing returns the default and the     runner fai, Constructing model objects must not require network access., _router(), test_auto_route_prefers_available_providers(), test_explicit_override_wins() (+11 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (20): EditFile, ListFiles, ReadFile, SearchFiles, ctx(), Any, Contract tests for file tools: list/read/write/edit/search + path safety., test_edit_file_errors_on_ambiguous_match() (+12 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (14): header_line(), Ten-segment context gauge: ▮▮▮▯▯▯ 3k/20k., Top border of the input box with state baked in., Always-on status line: approval mode, provider, model, thinking,     context gau, status_bar(), usage_bar(), (provider, model) that the NEXT turn will actually use.          Goes through th, One user turn: live-render events and stream the reply. (+6 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (18): ChatRequest, create_app(), main(), BaseModel, FastAPI, Path, Web reference client: FastAPI app exposing the same runtime as the CLI.  This mo, Build the web app bound to one repository. (+10 more)

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (14): Task-type -> model routing with explicit user overrides., RoutingConfig, ModelRouter, Model routing: pick the right model per task type, with overrides.  Order of pre, Pick from whichever provider has a key; strong/cheap per task type., Primary model plus configured fallbacks, all validated., The regression: /model selections must reach the runner even when     auto_route, A models.json provider selected as default must be used directly. (+6 more)

### Community 31 - "Community 31"
Cohesion: 0.12
Nodes (10): Exception, Report a live-stream failure without ending the turn., Terminate an open partial line (text/thinking printed with end="")., Flush partial (end="") writes to the terminal.          Rich only auto-flushes o, Live-render new events while the turn runs (polling drain)., Render a live diff/status for a file the agent just changed., Short git diff for a changed file; falls back to new-file marker., Render an executed command with a collapsed output preview.          Returns Tru (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.14
Nodes (16): Agent, ScriptFn, make_echo_model(), make_scripted_model(), make_tool_call_then_answer(), Any, FunctionModel, Mock provider: scripted models for deterministic tests and offline demos.  Wraps (+8 more)

### Community 33 - "Community 33"
Cohesion: 0.14
Nodes (11): _is_sensitive_key(), Any, Secret redaction: credentials never reach events, logs, or checkpoints., Replaces known secret values and obviously-secret keys with a marker.      Appli, Recursively redact strings in dicts/lists/tuples and by key name., SecretRedactor, EventCollector, Asynchronous event bus: one publish point, many subscribers.  Runtime components (+3 more)

### Community 34 - "Community 34"
Cohesion: 0.25
Nodes (17): Any, FunctionModel, Contract tests for the agent runtime runner (PydanticAI bridge, events, timeouts, A streaming model produces MESSAGE_DELTA events with kind text/thinking., PydanticAI's UsageLimits defaults request_limit to 50 when left     implicit; an, The model's tool call must flow through the guarded executor., _runner(), test_budget_maps_config_to_usage_limits() (+9 more)

### Community 35 - "Community 35"
Cohesion: 0.17
Nodes (9): _enable_vt_output(), Make sure stdout accepts ANSI escape sequences.      POSIX terminals always do., Await a turn with the status bar pinned to the terminal bottom.          ``botto, Reserve the terminal's bottom row for the status bar.          Returns the pin s, Repaint the bar row (outside the scroll region).          Save/restore wraps the, Reset the scroll region and erase the bar row., Repaint the bar each tick; survives a mid-turn terminal resize., Write raw ANSI straight to the terminal, bypassing rich styling. (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.19
Nodes (5): Queue, EventReader, Any, Async iterator over events published after subscription., Collect exactly ``count`` events; raises on timeout.

### Community 37 - "Community 37"
Cohesion: 0.14
Nodes (13): ModelSpec, ProviderInfo, ProviderSpec, BaseModel, Provider abstraction built on PydanticAI's already-unified model interface.  om-, Runtime view of a provider: availability and its known models., A parsed ``provider:model`` string., Static description of a supported provider. (+5 more)

### Community 38 - "Community 38"
Cohesion: 0.23
Nodes (10): _isolated_user_home(), Any, MonkeyPatch, Shared test fixtures: hermetic user-home isolation for every test.  Tests must n, _write_mock_default(), home(), Any, MonkeyPatch (+2 more)

### Community 39 - "Community 39"
Cohesion: 0.25
Nodes (11): apply_model(), _deep_merge(), _dump_toml(), load_user_overrides(), persist_updates(), Any, Raw user-level config table (empty if absent)., Merge updates into the user config.toml (creates it if needed). (+3 more)

### Community 40 - "Community 40"
Cohesion: 0.20
Nodes (5): ArgsT, BaseTool, Any, BaseModel, Base class for all tools.      Subclasses declare a module-level ``Args`` pydant

### Community 42 - "Community 42"
Cohesion: 0.36
Nodes (8): demo(), main(), make_sample_repo(), FunctionModel, Path, End-to-end demo without API keys: a scripted "coder" model performs a real codin, A model script: read the file, fix the bug, run tests, then summarize., scripted_coder_model()

### Community 43 - "Community 43"
Cohesion: 0.33
Nodes (8): _chunk(), _gateway_app(), gateway_url(), Any, FastAPI, End-to-end test: om-harness against a real local OpenAI-compatible gateway (in-p, Start the OpenAI-compatible gateway on an ephemeral localhost port., test_run_against_local_gateway_via_models_json()

### Community 44 - "Community 44"
Cohesion: 0.50
Nodes (8): _manager(), Any, Contract tests for the session manager (lifecycle, messages, checkpoints)., test_add_message_updates_and_persists(), test_create_session_publishes_and_persists(), test_list_and_latest_sessions(), test_run_lifecycle(), test_save_checkpoint_emits_event_and_persists()

### Community 45 - "Community 45"
Cohesion: 0.39
Nodes (7): Any, Contract tests for the persisted repo-index cache in the user cache dir., repo(), test_cache_written_and_reused(), test_expired_cache_rebuilt(), test_invalidate_removes_cache_file(), test_no_cache_dir_keeps_previous_behavior()

### Community 46 - "Community 46"
Cohesion: 0.29
Nodes (5): Contract tests for core Pydantic runtime models., test_event_has_identity_and_defaults(), test_event_roundtrip_preserves_type(), test_task_result_defaults_are_compact(), test_token_usage_add()

### Community 47 - "Community 47"
Cohesion: 0.47
Nodes (4): DoctorItem, DoctorReport, BaseModel, TaskStatus

## Knowledge Gaps
- **1 isolated node(s):** `om-harness`
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Harness` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 17`, `Community 18`, `Community 21`, `Community 26`, `Community 29`, `Community 30`, `Community 31`, `Community 33`, `Community 41`, `Community 42`, `Community 43`, `Community 47`?**
  _High betweenness centrality (0.175) - this node is a cross-community bridge._
- **Why does `ChatRepl` connect `Community 10` to `Community 0`, `Community 35`, `Community 6`, `Community 7`, `Community 8`, `Community 41`, `Community 14`, `Community 18`, `Community 21`, `Community 24`, `Community 28`, `Community 31`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `ToolContext` connect `Community 9` to `Community 1`, `Community 34`, `Community 5`, `Community 6`, `Community 40`, `Community 11`, `Community 16`, `Community 19`, `Community 23`, `Community 27`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `Harness` (e.g. with `ApprovalPolicy` and `HarnessConfig`) actually correct?**
  _`Harness` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ChatRepl` (e.g. with `ApprovalPolicy` and `ThinkingLevel`) actually correct?**
  _`ChatRepl` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `EventBus` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`EventBus` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Task` (e.g. with `DoctorItem` and `DoctorReport`) actually correct?**
  _`Task` has 15 INFERRED edges - model-reasoned connections that need verification._