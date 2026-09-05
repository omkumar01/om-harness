# Configuration

om-harness is configured from three sources, in increasing precedence:

1. built-in defaults,
2. a configuration file,
3. environment variables.

## Configuration file

Two locations are checked (per repository):

- `om-harness.toml` in the repository root, or
- `[tool.om-harness]` table in the repository root `pyproject.toml`.

A full example:

```toml
[routing]
default_model = "openai:gpt-4o-mini"   # used when routing can't pick better
auto_route = true                       # honor task_models automatically
fallbacks = ["anthropic:claude-sonnet-4-5"]

[routing.task_models]                   # task-type -> model
explore = "openai:gpt-4o-mini"
implement = "openai:gpt-4o"
review = "anthropic:claude-sonnet-4-5"
test = "openai:gpt-4o-mini"

[approval]
policy = "ask"                          # ask | auto | allowlist | deny
allowlist = ["write_file", "edit_file"] # used when policy = "allowlist"

[budget]
max_requests = 40
max_input_tokens = 200000
max_output_tokens = 32000
max_cost_usd = 2.0

[context]
max_history_messages = 40
summarize_after = 24
max_repo_index_files = 500
max_file_read_chars = 40000

max_concurrency = 4                     # parallel agent tasks
agent_timeout_seconds = 600.0
tool_timeout_seconds = 60.0
verbosity = "compact"                   # compact | verbose | debug
```

## Environment variables

| Variable | Meaning | Example |
|---|---|---|
| `OPENAI_API_KEY` | enables the OpenAI provider | `sk-…` |
| `ANTHROPIC_API_KEY` | enables the Anthropic provider | `sk-ant-…` |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | enables the Google (AI Studio) provider | |
| `OM_HARNESS_DEFAULT_MODEL` | overrides `routing.default_model` | `anthropic:claude-sonnet-4-5` |
| `OM_HARNESS_TASK_MODELS` | overrides `routing.task_models` (comma-separated) | `explore=openai:gpt-4o-mini,review=anthropic:claude-sonnet-4-5` |
| `OM_HARNESS_APPROVAL_POLICY` | overrides `approval.policy` | `auto` |
| `OM_HARNESS_MAX_CONCURRENCY` | parallel agent tasks | `2` |
| `OM_HARNESS_VERBOSITY` | `compact` / `verbose` / `debug` | `verbose` |
| `OM_HARNESS_MAX_REQUESTS` | per-run request ceiling | `20` |
| `OM_HARNESS_AGENT_TIMEOUT_SECONDS` | per-task agent timeout | `300` |
| `OM_HARNESS_TOOL_TIMEOUT_SECONDS` | per-tool-call timeout | `30` |

### API key handling rules

- Keys are read **only** from the environment. They never appear in
  `om-harness.toml`, sessions, checkpoints, or the event log.
- Every event passes through a secret redactor before any consumer
  (terminal, web, event log) sees it.
- Subprocesses spawned by tools receive an environment with
  credential-looking variables removed.
- Copy `.env.example` to `.env` and use your own mechanism to load it if
  you want file-based keys for local development.

## Model strings

`provider:model` strings select providers and models:

- `openai:gpt-4o-mini`, `openai:gpt-4o`
- `anthropic:claude-3-5-haiku-latest`, `anthropic:claude-sonnet-4-5`
- `google-gla:gemini-2.0-flash` (AI Studio; `google-vertex:` also available)
- `mock:echo` (offline; always available)

Unknown prefixes fail fast with a `ProviderError` naming the valid
prefixes.

## Checking configuration

```bash
om-harness config show          # effective merged configuration
om-harness providers            # which providers have keys
om-harness doctor               # full environment diagnostic
```

Invalid configuration fails loudly at startup (`ConfigError`) — never
mid-run.
