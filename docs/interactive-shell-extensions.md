# Interactive Shell Extensions: Tools, Skills, and Plugins

This guide explains how to use **tools**, **skills**, and **plugins** inside the
om-harness interactive shell. All three are first-class, explicitly reachable
from slash commands while you chat with the agent — no need to exit the shell or
drop to a separate tool.

For the broader shell UX (live streaming, status bar, plan mode, setup wizard)
see [the shell section in the README](../README.md#the-interactive-shell). For
the architectural reasoning behind the extension model, see
[design.md](design.md) (Tradeoff 11) and [architecture.md](architecture.md).

---

## What these are

| Concept | What it is | How the shell touches it |
|---|---|---|
| **Tools** | 16 schema'd actions the agent can take (read/write files, run shell, git, tests, repo info, load a skill). Each has a permission level: `read_only`, `mutating`, or `destructive`. | `/tools` lists them; the approval mode controls which mutable ones the agent may run without asking. |
| **Skills** | Small markdown instruction packs (`SKILL.md`). Names + one-line descriptions go in the system prompt; full instructions are fetched on demand. | `/skills` lists them; `/skill <name> [args]` runs a turn that loads and follows one. |
| **Plugins** | Git repositories cloned into `~/.om-harness/plugins/` by the CLI. They ship skills (and, someday, tools and slash commands). | Installed from the CLI; `/plugins` lists them inside the shell; their skills appear in `/skills`. |

There is **no MCP** integration — om-harness uses its own extension system
(PydanticAI provider interface + a typed tool registry + `SKILL.md` discovery +
git-installable plugins). See [design.md](design.md) Tradeoff 11.

---

## Launch the interactive shell

From any repository that has been initialized with `om-harness init`:

```console
$ cd your-repo
$ om-harness          # or: om-harness chat
```

The shell opens one input box with an always-visible status bar showing the
active approval mode, provider, model, thinking level, and a live context gauge.
Type `/` to trigger the autocomplete popup for slash commands.

---

## Tools

### Listing tools

```console
> /tools
· repo_info (read_only): Summarize the repository: branch, HEAD, languages, and file counts.
· git_status (read_only): Show the current branch and modified/staged files.
· git_diff (read_only): Show the unified diff of uncommitted changes (optionally staged only).
· git_log (read_only): Show recent commit history (oneline, newest first).
· git_show (read_only): Show a file's content at HEAD (last committed version).
· read_file (read_only): Read a text file from the repository (truncated to the context cap).
· search_files (read_only): Search file contents with a regular expression; returns file:line matches.
· list_files (read_only): List files in the repository (relative paths).
· skill (read_only): Load the full instructions of a named skill … (shown only when skills are installed)
· git_add (mutating): Stage files for commit.
· git_commit (mutating): Commit staged changes with a message.
· edit_file (mutating): Replace an exact substring in a file …
· run_shell (mutating): Execute a command in the repository root …
· write_file (mutating): Create or overwrite a file with the given content …
· run_tests (mutating): Detect and run the repository's test suite (pytest or npm test).
· git_restore (destructive): DISCARD uncommitted changes to a file …
```

The `permission` label tells you how the approval engine treats each tool.

### Permission levels and what they mean

Every tool declares one of three permission levels (defined in
`src/om_harness/tools/base.py`, enforced in
`src/om_harness/tools/approval.py`):

| Level | Tools | In the shell |
|---|---|---|
| `read_only` | `list_files`, `read_file`, `search_files`, `git_status`, `git_diff`, `git_log`, `git_show`, `repo_info`, `skill` | **Always allowed** — no approval prompt, regardless of mode. |
| `mutating` | `write_file`, `edit_file`, `run_shell`, `git_add`, `git_commit`, `run_tests` | Allowed without prompt under `auto`; asked under `ask`; only allowed-listed tools run under `allowlist`; blocked under `deny`. |
| `destructive` | `git_restore` | **Never auto-approved**, even under `auto`. Always requires explicit confirmation. |

Every tool call — started, completed, denied, or failed — is published as an
event on the `EventBus` and rendered live in the shell. Failures are always
shown regardless of verbosity.

### Controlling which tools need approval

The approval policy governs which mutating and destructive tools the agent can
run without asking you:

- **`/mode`** (or `Shift+Tab`) cycles through: `ask` → `auto` → `deny` → back to `ask`.
  The current mode is shown in the status bar as `⏵ ask`, `⏵⏵ auto`, or
  `⛔ deny`.

- **`/config set approval <policy>`** sets a specific policy and persists it to
  `~/.om-harness/config/config.toml`. Valid values: `auto`, `ask`, `allowlist`,
  `deny`.

- **`/config set allowlist`** is not directly supported via `/config set` (the
  `allowlist` key is not in the validated set of config-update keys). To use an
  allowlist, edit your config file directly. Example in `om-harness.toml` or
  `[tool.om-harness]` in `pyproject.toml`:

  ```toml
  [approval]
  policy = "allowlist"
  allowlist = ["write_file", "edit_file"]
  ```

  Under `allowlist`, only the listed tools run without confirmation; all other
  mutating/destructive tools prompt (or are denied in non-interactive runs).

> **Fail-safe rule:** in any non-interactive context (e.g. `om-harness run --json`),
> a tool that needs confirmation resolves to **denied**, never silently approved.

### Shell safety

The `run_shell` tool is the safe shell executor (in `src/om_harness/tools/shell.py`):

- Commands run as **argv lists** with `shell=False` — no `/bin/sh` involved.
- Simple pipelines (`a | b | c`), `2>&1` merging, and `> / >>` redirection are
  supported natively (parsed and chained as separate processes).
- Shell metacharacters that require a shell (`;`, `&`, `<`, `$`, backticks,
  `()`) are **rejected outright**.
- Catastrophic patterns (`rm -rf /`, `format c:`, `mkfs`, fork bombs,
  `git push --force --all`) are blocked before execution.
- Subprocesses receive a **scrubbed environment** (no `API_KEY`, `SECRET`,
  `TOKEN` variables).
- All tools resolve file paths **strictly inside the repository root**; the sole
  exemption is the `skill` tool, which takes a name (not a path) resolved
  against the discovery registry.

---

## Skills

### Discovering skills

```console
> /skills
· brainstorm [user]: Use when creating or developing, before writing code …
· systematic-debugging [user]: Use when encountering any bug, test failure, or unexpected behavior …
· writing-plans [user]: Use when you have a spec or requirements for a multi-step task …
· verification-before-completion [user]: Use when about to claim work is complete …
· brainstorming [plugin:superpowers]: You MUST use this before any creative work …
· dispatching-parallel-agents [plugin:superpowers]: …
· subagent-driven-development [plugin:superpowers]: …
· …
```

Each line shows: **`name` [`source`]**`: description`. When an argument hint exists, it appears in brackets: `[args: <hint>]`.

### Where skills come from (discovery order)

Skills are discovered from four sources, checked in override order (later sources
win on name collision; plugin plain names fill free slots only):

| Source | Location | Shell label |
|---|---|---|
| User | `~/.agents/skills` *(or `$OM_HARNESS_SKILLS_DIR`)* | `user` |
| Config | `[skills].extra_dirs` entries (relative to repo) | `extra` |
| Repo | `<repo>/.agents/skills` | `repo` |
| Plugins | `skills/*/SKILL.md` or `.agents/skills/*/SKILL.md` inside each installed plugin | `plugin:<name>` |

Discovery happens at harness startup in `Harness._resolve_skills()`
(`src/om_harness/harness.py`). Plugin skills only appear after a restart —
installing a plugin mid-session does not hot-reload its skills.

### Namespacing

Plugin skills are registered under **two** names:
1. **Namespaced**: `<plugin>:<skill>` — always unambiguous.
2. **Plain name** (e.g. `brainstorming`) — only filled when no user/repo/config
   skill already claims that name. User and repo skills always win collisions.

So in the shell, you can run `/skill brainstorming` (if unique) or
`/skill superpowers:brainstorming` (always works).

### Running a skill

```console
> /skill systematic-debugging
```

This runs a dedicated chat turn whose prompt instructs the agent: *"Load the
skill 'systematic-debugging' with the skill tool and follow its instructions to
handle this request."* The agent then invokes the `skill` tool, which loads the
full `SKILL.md` body (the part after the frontmatter) and follows it.

You can pass extra arguments or context:

```console
> /skill test-driven-development implementing a caching layer for the parser
```

Any text after the skill name is appended as `Arguments/context:` to the
agent's instructions for that turn.

### How progressive disclosure works

Only skill **names + one-line descriptions** enter the system prompt (injected by
`ContextAssembler._skills_section()` in `src/om_harness/context/assembler.py`).
The full `SKILL.md` body is fetched on demand through the read-only `skill` tool
(`src/om_harness/tools/skill.py`). This keeps context small: a dozen skills are
easily 20k+ characters that are not sent unless actually needed.

To disable skill discovery entirely, set in your config:

```toml
[skills]
enabled = false
```

### Creating a local skill

Any directory under a discovery source containing a `SKILL.md` file is picked up.
The `SKILL.md` format is minimal frontmatter followed by markdown:

```markdown
---
name: code-review
description: Review a file or diff for correctness, style, and edge cases.
argument-hint: <repo-relative file path or PR number>
---

When invoked, do the following:

1. Read the specified file or git diff.
2. Check for off-by-one errors, unhandled edge cases, and missing error handling.
3. Look for style violations (snake_case, type hints, docstrings).
4. Report findings as a bulleted list, prioritizing correctness issues.
```

Place it in `<repo>/.agents/skills/code-review/SKILL.md` for repo-local skills,
or in `~/.agents/skills/code-review/SKILL.md` for user-wide skills. Restart
om-harness for new skills to be discovered.

---

## Plugins

### Listing installed plugins

```console
> /plugins
· superpowers (13 skills): A collection of meta-skills for agentic coding.
  · brainstorming: You MUST use this before any creative work …
  · writing-plans: Use when you have a spec or requirements …
  · systematic-debugging: Use when encountering any bug …
  · …
```

This calls `plugins.load_plugins()` and reads each plugin's `plugin.json`
manifest (if present) and its `SKILL.md` files.

### Installing a plugin (CLI-side)

Plugins are installed from your **shell or terminal** — not from within the
interactive shell:

```bash
om-harness install git:github.com/obra/superpowers
om-harness install git:owner/repo          # shorthand for GitHub
om-harness install https://github.com/owner/repo.git
om-harness install /path/to/local/clone
```

Installation shallow-clones the plugin into `~/.om-harness/plugins/<name>`
(override: `$OM_HARNESS_PLUGINS_DIR`) and writes a `.om-harness-plugin.json`
provenance record (source spec + commit SHA).

> **Restart required:** plugin skills are discovered at harness startup. After
> installing, restart the interactive shell (exit and re-enter) for new plugin
> skills to appear in `/skills` and `/skill`.

### Managing plugins

```bash
om-harness plugins                              # list installed plugins (CLI)
om-harness plugins --json                       # machine-readable
om-harness uninstall superpowers                # remove a plugin
om-harness uninstall superpowers --json
```

Reinstalling an already-installed plugin updates it via `git pull --ff-only`
(fast-forward only — no merge commits). Uninstall removes the plugin directory
after fixing permissions on read-only git objects.

### Plugin manifests

A plugin may include an optional `plugin.json` at its root:

```json
{
  "name": "superpowers",
  "description": "A collection of meta-skills for agentic coding."
}
```

If absent, the directory name is used. The manifest is purely informational —
the plugin's value to om-harness comes entirely from its `SKILL.md` files.

### What plugins can (and can't) do yet

Currently, a plugin contributes only **skills**. The architecture is set up to
support plugin-supplied tools and slash commands as a future extension (see
design.md, "Future extension points"), but that is not yet implemented — the
manifest is the versioned seam for it.

---

## Keyboard shortcuts

| Keys | Action |
|---|---|
| `Enter` | Send the current message |
| `\` + `Enter` or `Alt+Enter` | Insert a newline (multi-line input) |
| `Shift+Tab` | Cycle approval mode: ask → auto → deny → ask |
| `Ctrl+T` | Cycle thinking level: off → low → medium → high |
| `Ctrl+O` | Cycle verbosity: compact → verbose → debug |
| `Alt+M` | Open the arrow-key model selector (all configured providers) |
| `Alt+O` | Re-open the output of the most recent executed command (cycles backward) |
| `Ctrl+G` | Show help (commands + keybindings) |
| `Ctrl+L` | Clear screen |
| `Ctrl+C` | Clear input; press again within 2s to quit; interrupts a running turn |
| `Ctrl+D` | Quit |
| `Up` / `Down` | Browse input history |

The status bar at the bottom of the terminal shows the current state and
updates in real time during a turn (it is pinned via a VT scroll region so
streaming output scrolls above it rather than erasing it).

---

## Slash command reference

All slash commands are defined in `src/om_harness/ui/slash.py`. Type `/` and
browse the autocomplete popup, or press `Ctrl+G` for the full list.

| Command | Arguments | What it does |
|---|---|---|
| `/model` | `[provider:model]` | Show or set the active model. No args opens the arrow-key selector. |
| `/thinking` | `[off\|low\|medium\|high]` | Show or set the thinking level. No args toggles live display. |
| `/mode` | — | Cycle approval mode: ask → auto → deny |
| `/plan` | `[on\|off]` | Toggle plan mode (read-only research, then approve to implement) |
| `/config` | — | Show current configuration |
| `/config set` | `<key> <value>` | Change and persist a config key (model, thinking, approval, verbosity, max_concurrency, max_requests, agent_timeout, tool_timeout, task_model.<type>) |
| `/timeout` | `[agent\|tool] <seconds\|off>` | Show or set the agent (whole-turn) and tool (per-call) timeouts |
| `/providers` | — | List providers and their availability |
| `/tools` | — | List available tools with permission levels and descriptions |
| `/skills` | — | List available skills with source labels and argument hints |
| `/skill` | `<name> [args]` | Run a turn that loads and follows a specific skill |
| `/plugins` | — | List installed plugins and their skills |
| `/status` | — | Show session, checkpoint, and provider status |
| `/sessions` | — | List recent sessions |
| `/checkpoint` | `[label]` | Save a checkpoint now |
| `/setup` | — | Interactive setup wizard (providers, model, mode, verbosity, thinking) |
| `/verbose` | — | Cycle verbosity: compact → verbose → debug |
| `/output` | `[n]` | Re-page a previously executed command's output (`Alt+O` does this inline) |
| `/help` | — | Show all commands and keybindings |
| `/exit` | — | Leave the session (aliases: `quit`, `:q`, `q`) |

---

## Live display during turns

While a turn runs, the shell renders events as they happen through a pump that
polls the `EventBus` every 50ms:

- **Model replies** stream token-by-token (green text). Thinking deltas stream
  in dim italic if `/thinking` is on or `Ctrl+T` has raised the level.
- **Tool calls** appear as `⚙ tool name(args)` when they start and `⚙ done` /
  `✖ failed` when they finish.
- **File changes** render a real-time git diff — `✎ path` with `+`/`−` lines
  for tracked files, or `(new file — not yet tracked)` for untracked ones.
- **Shell commands** show a collapsed output preview (last 3 lines) with a
  hint to press `Alt+O` or `/output` to expand.
- **Denials** and **approvals** appear with `⛔` / `?` icons.
- **Per-turn summary** at the bottom of each turn shows files read, files
  modified, commands run, and token usage.

All of this works in every flow — chat, `om-harness run`, and `om-harness agent`
— because they all publish through the same `EventBus`.

---

## Workflow examples

### 1. Research a codebase with read-only tools only

```console
> /plan on
plan mode on — read-only research; the agent proposes a plan, then reply 'approve' to implement

> find the sign bug in calc.py
[agent explores the repo: list_files, read_file, git_log, ...]
⏸ plan
The bug is in calc.py line 42: the subtraction should be addition.
Plan:
1. Fix the sign on line 42.
2. Run tests.

> approve
plan mode off — approval mode: ⏵⏵ auto
[agent implements the fix, runs tests, reports success]
```

### 2. Run a skill-driven task

```console
> /skills
· brainstorming [user]: Use when creating or developing, before writing code …
· test-driven-development [plugin:superpowers]: …
· systematic-debugging [user]: …

> /skill systematic-debugging failing test in test_parser.py
[agent loads the systematic-debugging skill and follows its steps]
```

### 3. Lock down the approval mode for a careful pass

```console
> /config set approval deny
approval policy set to deny · saved to ~/.om-harness/config/config.toml

> /tools               # still lists everything
> write a note to scratch.txt   # agent calls write_file → ⛔ denied
tool call denied: denied by approval policy
```

### 4. Use a plugin skill by namespaced name

```console
> /skill superpowers:brainstorming feature ideas for a CLI todo app
[agent loads brainstorming skill and follows it]
```

---

## Best practices

- **Start with `/tools`** to understand what the agent can do, and `/mode` to
  set your comfort level (use `ask` if you want to review every file write and
  shell command).
- **Use `/skills`** to discover what instruction packs are available. Skills are
  the primary extension mechanism — install the `superpowers` plugin for a
  set of battle-tested meta-skills:
  ```bash
  om-harness install git:github.com/obra/superpowers
  ```
- **Use `/plan on`** before complex or risky tasks. The agent will explore
  read-only and propose a plan; reply `approve` (or `go ahead`, `implement`,
  `proceed`, `lgtm`, `looks good`, `ship it`) when the plan looks right.
- **Use `/skill <name>`** when you want the agent to follow a specific
  methodology (debugging, TDD, brainstorming, etc.) for a turn.
- **Check `/providers`** if model calls fail — it tells you which providers have
  keys configured and which don't.
- **Use `/setup`** on first run to walk through provider configuration, model
  selection, and default modes — everything persists to `~/.om-harness/`.
