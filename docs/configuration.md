# Configuration

om-harness is configured from four sources, in increasing precedence:

1. built-in defaults,
2. user-level configuration: `~/.om-harness/config/config.toml`,
3. repository-level configuration: `om-harness.toml` (or
   `[tool.om-harness]` in `pyproject.toml`),
4. environment variables.

Nested tables merge across levels — a repo-level `[routing.task_models]`
entry adds to (or overrides) the user-level one; scalars at the more
specific level win.

## User-level layout (`~/.om-harness/`)

The delivered install keeps all configuration and caches here
(`OM_HARNESS_HOME` overrides the root, e.g. for tests):

```
~/.om-harness/
├── config/
│   ├── config.toml     # user-level harness settings (created on demand)
│   └── models.json     # user-level custom providers
└── cache/
    └── repo-index/     # persisted repository index caches (24h TTL)
```

Sessions and checkpoints stay repository-local (`<repo>/.om-harness/`,
gitignored). Inside the interactive chat, `/config set <key> <value>`
validates the change, applies it to the live session, and persists it to
`config.toml` — keys: `model`, `thinking`, `approval`, `verbosity`,
`max_concurrency`, `max_requests`, `task_model.<type>`.

### Thinking level

`thinking = "off" | "low" | "medium" | "high"` controls how much reasoning
budget the model gets. The runner maps it to each provider's native setting:

| Provider | Setting applied |
|---|---|
| Anthropic | `thinking = {type: "enabled", budget_tokens: 2048/10000/16384}` |
| Google | `google_thinking_config = {include_thoughts: true, thinking_budget: …}` |
| OpenAI | `openai_reasoning_effort = "low"/"medium"/"high"` (reasoning models only) |
| others | no settings sent (graceful degradation) |

Set it with `/config set thinking medium`, `/thinking medium`, or `Ctrl+T`.

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
- anything from your `models.json` custom providers
- `mock:echo` (offline echo stub for demos/tests; explicit selection only —
  never auto-selected, never listed as a provider)

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

## Custom providers via `models.json`

Beyond the built-in providers, om-harness can use **any OpenAI-compatible
endpoint** declared in a `models.json` file: local gateways (LM Studio,
Ollama, llama.cpp server) or remote inference providers (NVIDIA NIM,
Poolside, OpenRouter, private deployments).

Location — all sources are merged, more specific ones winning per provider:

1. `~/.om-harness/config/models.json` (user-level; the usual place),
2. `<repo>/models.json` (repo-specific providers/overrides),
3. path in the `OM_HARNESS_MODELS_JSON` environment variable (explicit override).

Example (a full annotated copy lives at
[examples/models.json](examples/models.json)):

```json
{
  "providers": {
    "lm-studio": {
      "baseUrl": "http://127.0.0.1:8080/v1",
      "api": "openai-completions",
      "allowLocal": true,
      "models": [
        { "id": "qwen3-32b", "contextWindow": 256000, "maxTokens": 256000 }
      ]
    },
    "nvidia": {
      "baseUrl": "https://integrate.api.nvidia.com/v1",
      "api": "openai-completions",
      "apiKeyEnv": "NVIDIA_API_KEY",
      "models": [
        {
          "id": "nvidia/nemotron-3-ultra-550b-a55b",
          "toolCalling": true,
          "contextWindow": 1000000,
          "maxInputTokens": 1000000,
          "maxOutputTokens": 256000
        }
      ]
    }
  }
}
```

Fields (camelCase and snake_case are both accepted):

| Field | Meaning |
|---|---|
| `baseUrl` | OpenAI-compatible base URL (`/v1` included) |
| `api` | `openai-completions` (chat completions) or `openai-responses` |
| `apiKeyEnv` | **Recommended:** name of the env variable holding the key |
| `apiKey` | inline key — only sensible for local gateways; automatically registered with the secret redactor |
| `allowLocal` | explicit opt-in required for `127.0.0.1`/`localhost`/private-range endpoints (see below) |
| `models[].id` | model id used in model strings |
| `models[].toolCalling` / `vision` / `reasoning` | capability flags (informational; shown by `om-harness providers`) |
| `models[].contextWindow` / `maxTokens` / `maxInputTokens` / `maxOutputTokens` | limits (informational) |
| `models[].url` | optional per-model base-URL override |
| `models[].cost` | per-token costs (informational; zeros for local models) |

Custom models become first-class model strings usable everywhere a model is
accepted — CLI override, config routing, `task_models`, fallbacks:

```bash
export NVIDIA_API_KEY=...                      # or OM_HARNESS_MODELS_JSON keys
om-harness run "fix the parser bug" --model lm-studio:qwen3-32b
om-harness providers                           # lists custom providers + models
```

And in `om-harness.toml`:

```toml
[routing.task_models]
explore = "lm-studio:qwen3-32b"
implement = "nvidia:nvidia/nemotron-3-ultra-550b-a55b"
```

### URL safety policy

Endpoints are validated when `models.json` is loaded and again before any
client is constructed:

- only `http://` and `https://` are allowed;
- loopback (`127.0.0.1`, `::1`, `localhost`), private ranges (`10/8`,
  `172.16/12`, `192.168/16`), link-local, and reserved hosts are **rejected
  by default** — this is SSRF protection;
- local inference servers are a legitimate case, so a provider may set
  `"allowLocal": true` to opt in explicitly. The opt-in applies to that
  provider's own endpoints only.

### Key handling

Prefer `apiKeyEnv` and keep keys in your environment. Inline `apiKey`
values are accepted (many local gateways require a placeholder) but are
treated as secrets: they are registered with the secret redactor, so they
never appear in events, logs, sessions, or checkpoints. Invalid or unsafe
`models.json` content fails loudly at startup (`ModelsJsonError`).
