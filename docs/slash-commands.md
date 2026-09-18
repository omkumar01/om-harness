# Slash Commands Reference

This document provides a complete reference for all slash commands available in the interactive shell.

## Overview

Slash commands are typed directly into the REPL prompt (prefixed with `/`) and provide quick access to common configuration and session management tasks. They support tab completion for command names and arguments.

---

## Command List

| Command | Description | Arguments | Examples |
|---------|-------------|-----------|----------|
| `/model` | Pick or set the active model | `[provider:model]` | `/model anthropic:claude-3-opus` |
| `/thinking` | Cycle thinking display (inline / minimized / off) or set model level | `[inline\|minimized\|off\|low\|medium\|high]` | `/thinking inline` |
| `/mode` | Cycle approval mode (ask / auto / deny) | *(none)* | `/mode` |
| `/plan` | Toggle plan mode (read-only research, then approve to implement) | `[on\|off]` | `/plan on` |
| `/config` | Show or change configuration | `[set <key> <value>]` | `/config set model anthropic:claude-3-opus` |
| `/timeout` | Show or set timeouts (agent turn / tool call) | `[agent\|tool] <seconds\|off>` | `/timeout agent 300` |
| `/providers` | List providers and availability | *(none)* | `/providers` |
| `/tools` | List available tools and permissions | *(none)* | `/tools` |
| `/skills` | List available skills | *(none)* | `/skills` |
| `/skill` | Run a turn that follows a skill | `<name> [args]` | `/skill analyse-problem "issue description"` |
| `/plugins` | List installed plugins and their skills | *(none)* | `/plugins` |
| `/status` | Session, checkpoint, and provider status | *(none)* | `/status` |
| `/sessions` | List recent sessions | *(none)* | `/sessions` |
| `/checkpoint` | Save a checkpoint now | `[label]` | `/checkpoint "before refactor"` |
| `/resume` | Show session, checkpoints, and the resume command | *(none)* | `/resume` |
| `/memory` | Manage project memory (list/recall/clear) | `[list [tag] \| recall <query> \| clear]` | `/memory list` |
| `/setup` | Interactive setup wizard (providers, model, modes) | *(none)* | `/setup` |
| `/verbose` | Cycle verbosity (compact / verbose / debug) | *(none)* | `/verbose` |
| `/help` | Show commands and keybindings | *(none)* | `/help` |
| `/exit` | Leave the session | *(none)* | `/exit` |

---

## Detailed Command Reference

### `/model` — Set Active Model

**Usage:** `/model [provider:model]`

Sets the active model for the current session. Without arguments, shows the current model.

- **Arguments:** Provider and model name in `provider:model` format (e.g., `anthropic:claude-3-opus`, `openai:gpt-4o`)
- **Tab Completion:** Shows available models from configured providers
- **Example:**
  ```
  /model anthropic:claude-3-5-sonnet
  ```

---

### `/thinking` — Set Thinking Level

**Usage:** `/thinking [off|low|medium|high]`

Controls the reasoning/thinking effort level for the model. Without arguments, shows the current level.

- **Options:**
  - `off` — No explicit thinking (◌)
  - `low` — Minimal thinking (◐)
  - `medium` — Balanced thinking (◑)
  - `high` — Maximum thinking (●)
- **Tab Completion:** Cycles through available levels
- **Example:**
  ```
  /thinking high
  ```

---

### `/mode` — Cycle Approval Mode

**Usage:** `/mode`

Cycles through the three approval modes without arguments:

1. **ask** (⏵) — Prompt before each tool call
2. **auto** (⏵⏵) — Automatically approve safe tool calls
3. **deny** (⛔) — Block all tool calls by default

---

### `/plan` — Toggle Plan Mode

**Usage:** `/plan [on|off]`

Enables or disables plan mode. In plan mode, the agent performs read-only research and presents a plan for approval before implementing.

- **Arguments:** `on` to enter, `off` to leave (omitting toggles)
- **Indicator:** Shows ⏸ in status bar when active
- **Example:**
  ```
  /plan on
  ```

---

### `/config` — Configuration Management

**Usage:** `/config [set <key> <value>]`

View or modify configuration settings. Without arguments, displays current configuration.

#### Configurable Keys

| Key | Description | Values |
|-----|-------------|--------|
| `model` | Default model | `provider:model` |
| `thinking` | Default thinking level | `off`, `low`, `medium`, `high` |
| `approval` | Default approval mode | `ask`, `auto`, `allowlist`, `deny` |
| `verbosity` | Default output verbosity | `compact`, `verbose`, `debug` |
| `max_concurrency` | Max parallel agent tasks | Integer |
| `max_requests` | Per-run request budget | Integer |
| `agent_timeout` | Agent turn timeout (seconds or off) | Integer or `off` |
| `tool_timeout` | Per-tool-call timeout (seconds or off) | Integer or `off` |
| `tool_max_retries` | Tool retry limit (0 to disable) | Integer |
| `task_model.explore` | Model for explore tasks | `provider:model` |
| `task_model.implement` | Model for implement tasks | `provider:model` |
| `task_model.review` | Model for review tasks | `provider:model` |

**Examples:**
```
/config
/config set model anthropic:claude-3-opus
/config set max_concurrency 4
/config set agent_timeout 300
```

---

### `/timeout` — Timeout Configuration

**Usage:** `/timeout [agent|tool] <seconds|off>`

Configure timeouts for agent turns and individual tool calls.

- **Types:**
  - `agent` — Whole-turn timeout
  - `tool` — Per-tool-call timeout
- **Values:** Seconds (integer) or `off` to disable
- **Example:**
  ```
  /timeout agent 300
  /timeout tool off
  ```

---

### `/providers` — List Providers

**Usage:** `/providers`

Displays all configured providers and their availability status (API keys, connectivity).

---

### `/tools` — List Tools

**Usage:** `/tools`

Shows all available tools with their current permission status (allowed/denied/ask).

---

### `/skills` — List Skills

**Usage:** `/skills`

Lists all available skills with brief descriptions.

---

### `/skill` — Run a Skill

**Usage:** `/skill <name> [args]`

Executes a skill directly in the current turn. Useful for one-off skill invocations without full workflow integration.

- **Arguments:** Skill name followed by any skill-specific arguments
- **Example:**
  ```
  /skill analyse-problem "Users report slow startup"
  /skill create-agent --name my-agent
  ```

---

### `/plugins` — List Plugins

**Usage:** `/plugins`

Shows installed plugins and the skills/commands each provides.

---

### `/status` — Session Status

**Usage:** `/status`

Displays current session info including:
- Active model and thinking level
- Approval mode
- Checkpoint status
- Provider connectivity

---

### `/sessions` — Recent Sessions

**Usage:** `/sessions`

Lists recent sessions with timestamps and status for quick resumption.

---

### `/checkpoint` — Save Checkpoint

**Usage:** `/checkpoint [label]`

Creates a named checkpoint of the current session state. Without arguments, uses an auto-generated label.

- **Example:**
  ```
  /checkpoint "before major refactor"
  ```

---

### `/resume` — Resume the Session

**Usage:** `/resume`

Shows the current session (id, status, message and run counts), the latest
checkpoints, and the exact command to continue this session later:

```
session a1b2c3d4e5f6 (active) · 4 messages · 2 run(s)
⌘ after-a1b2c3d4: main: completed - ...
to resume: om-harness --resume --session a1b2c3d4e5f6  ·  cp: cp-a1b2c3d4
```

The same resume hint is printed when a run finishes and when you exit the
shell, so interrupted or completed work can always be continued.

---

### `/memory` — Project Memory Management

**Usage:** `/memory list [tag]` | `/memory recall <query>` | `/memory clear`

Manages the project-level memory system — a persistent fact store that
survives across sessions within the same repository. Facts are stored as
structured entries (content + tags + confidence + TTL) in
`<repo>/.om-harness/memory/memory.jsonl` and retrieved via a keyword inverted
index (no vector DB, no model calls).

- **`list [tag]`** — List all stored memory entries. Optionally filter to
  entries tagged with the given tag. Expired entries (past `fact_ttl_days`)
  are shown dimmed.
- **`recall <query>`** — Search stored facts by keyword, ranked by
  relevance (TF-IDF + recency + access-frequency + confidence). Results are
  also injected into the model's context automatically during runs when the
  instruction matches stored facts.
- **`clear`** — Remove all stored memory entries.

**Examples:**
```
/memory list                # show all facts
/memory list bug            # show only facts tagged "bug"
/memory recall parser       # search for facts mentioning "parser"
/memory clear               # wipe all stored facts
```

The agent can also interact with memory during a run via the `remember` tool
(store a fact, mutating — requires approval) and the `recall` tool
(search stored facts, read-only). Memory is enabled by default; disable it
with `memory.enabled = false` in `om-harness.toml`.

---

### `/setup` — Setup Wizard

**Usage:** `/setup`

Launches an interactive wizard to configure:
- API providers and keys
- Default model
- Approval mode
- Verbosity level

---

### `/verbose` — Cycle Verbosity

**Usage:** `/verbose`

Cycles through verbosity levels:
1. **compact** — Minimal output
2. **verbose** — Detailed output
3. **debug** — Full debug logging

---

### `/help` — Show Help

**Usage:** `/help`

Displays a summary of all slash commands and keybindings.

---

### `/exit` — Exit Session

**Usage:** `/exit`

Cleanly exits the interactive shell, offering to save a checkpoint.

---

## Keybindings

| Key | Action |
|-----|--------|
| `Tab` | Complete command / argument |
| `Shift+Tab` | Previous completion |
| `↑/↓` | History navigation |
| `Ctrl+C` | Interrupt current operation |
| `Ctrl+D` | Exit (same as `/exit`) |

---

## Tips

1. **Tab Completion** works for all commands and their arguments. Type `/` then `Tab` to see all commands.

2. **Inline Hints** appear as you type arguments for commands that support them (e.g., `/config set ` shows valid keys).

3. **Cycling Commands** (`/mode`, `/thinking`, `/verbose`) don't require arguments — just run them repeatedly to cycle.

4. **Configuration Persistence**: Changes made via `/config set` persist across sessions in your user settings file.

5. **Checkpoint Before Big Changes**: Use `/checkpoint` before experimental work so you can roll back if needed.

---

*Generated from `src/om_harness/ui/slash.py`*