# Design document & tradeoffs

This document records the important design decisions in om-harness and,
more importantly, the tradeoffs accepted — so future contributors can
revisit them with full context.

## Goals (in priority order)

1. A working coding-agent CLI usable on real repositories today.
2. Minimal context footprint (tokens, latency, cost) without sacrificing
   capability.
3. Reliability: durable state, resume, timeouts, retries, bounded
   concurrency.
4. Safety: tool permissions, approval gates, fail-safe defaults, no secret
   leakage.
5. Readability: a codebase a single contributor can hold in their head.
6. Extensibility: clean seams for future work, but no speculative
   infrastructure.

## Tradeoff 1: PydanticAI as the agent substrate vs. a homegrown loop

**Decision.** Agents are PydanticAI `Agent` instances; message/history types,
usage accounting, retries (`ModelRetry`), usage limits, and structured
outputs come from the library.

**Why.** A hand-rolled loop would duplicate message-protocol code for three
providers and drift as APIs change. PydanticAI is stable, typed, and its
`FunctionModel` gives us a perfect offline testing substrate.

**Cost.** We inherit PydanticAI's abstractions and occasionally use a
private helper (`pydantic_ai._function_schema`) in exactly one file
(`runtime/agent.py`) to bridge our tool registry. That is the single
fragile seam, deliberately isolated and documented.

## Tradeoff 2: How aggressively to minimize context

**Decision.** Conservative, mechanical minimization: capped repo *index*
(paths, not contents), role-scoped prompts, history window + extractive
summary, `TaskResult` handoffs, token ledger. No LLM-driven summarization.

**Why.** Mechanical minimization is deterministic, testable, and free. The
biggest wins in agent workloads come from *not resending* repository
listings and transcripts — those do not require an LLM summarizer.

**Cost.** Model-generated summaries would compress better than our
extractive one. The assembler is the single place to add them later; the
`ContextLedger` already reports what was sent.

**Non-goals.** Vector embeddings, semantic retrieval, RAG. For repos that
fit an index summary plus targeted `read_file` calls, they add moving parts
without changing what the model sees.

## Tradeoff 3: Orchestration — plans as data vs. agent-driven planning

**Decision.** The planner is a small heuristic that produces a `Plan`
(validated DAG); the coordinator executes plans identically regardless of
origin (heuristic, user-declared tasks via CLI, or — later — model-produced
JSON plans).

**Why.** Model-driven planning is nondeterministic, costly, and hard to
test. Most real tasks need one agent; "explore then implement" covers most
of the rest. Making plans *data* means a future model-driven planner drops
in without touching the coordinator.

**Cost.** v1 cannot decide on its own to spawn six parallel specialists.
Users can force it today (`agent`/`run --strategy`, declared tasks); a
model-generated plan module is the documented extension point.

## Tradeoff 4: Wave scheduling vs. fully dynamic scheduling

**Decision.** The coordinator executes topological *waves* (all ready tasks
concurrently, bounded by a semaphore), rather than launching each task the
instant its dependencies finish.

**Why.** Waves make fan-in aggregation trivially deterministic, keep the
code small (one loop, `asyncio.gather`), and preserve real parallelism
(proven by a deadlock-if-serialized sentinel test).

**Cost.** A long wave can delay a newly-ready task until the wave drains.
For agent tasks (seconds to minutes), the scheduling overhead is negligible
compared to the model calls themselves.

## Tradeoff 5: Durability — files vs. a database

**Decision.** JSON/JSONL files under `.om-harness/` with atomic writes.

**Why.** Zero setup, human-inspectable, diffable, trivially portable. The
spec's failure model (a crashed process, not concurrent multi-host access)
is fully handled: temp-file + rename leaves no torn state, and reads
tolerate a torn final event line.

**Cost.** No concurrent writers, no queries. `LocalStore` and `EventBus`
are the seams for a hosted/remote implementation later.

## Tradeoff 6: Safety defaults

**Decision.** Fail-safe everywhere:

- non-interactive contexts *deny* tools that need confirmation (never
  auto-approve);
- shell runs argv-only, no shell interpolation, with a metacharacter and
  catastrophic-command blocklist;
- destructive tools (currently `git restore`) are never auto-approved, even
  under `auto` policy;
- all file operations are confined to the repository root;
- subprocess environments are scrubbed of credential-looking variables;
- the redactor scrubs values *and* sensitive key names at the event bus, so
  every consumer is covered once.

**Cost.** No `/bin/sh` is ever involved: `run_shell` implements the safe
subset of shell syntax natively — pipelines (`a | b`), `2>&1` merging, and
`>` / `>>` redirection into repository files are parsed and executed as
chained argv processes. Constructs that genuinely require a shell
(`;`, `&&`, `<`, `$()`, backticks, background jobs) remain rejected, as do
known catastrophic commands. This trades a slice of raw power for an
auditable, injection-resistant surface.

## Tradeoff 7: One event bus for everything

**Decision.** A single async pub/sub bus; UI, persistence, and tracing are
all subscribers; redaction happens at publish.

**Why.** One mechanism to test; guarantees the terminal, web, and logs see
identical histories; keeps `emit` cheap (sync publish into queues, bounded
history, seq-cursor draining after a run to avoid async races).

**Cost.** The bus history is in-memory per process. Long-running hosted
deployments will want the JSONL log (or a remote bus) as the source of
truth — the interface is the extension point.

## Tradeoff 8: Terminal UI scope

**Decision.** Compact-by-default replay of filtered events plus a summary
panel; live token streaming is not implemented in v1. *(Update: live
streaming later shipped through a bus-draining pump in the REPL — see
Tradeoff 12 for why it drains by seq cursor.)*

**Why.** Agent turns are seconds-long; replay reads as "live". Spending
complexity on terminal streaming before the web SSE client (which *is*
streaming, by construction) would invert priorities. PydanticAI's
`event_stream_handler` is the documented hook for adding it.

## Tradeoff 9: Structured agent outputs

**Decision.** Agents return plain text which the runner wraps into
`TaskResult`; inter-agent contracts are enforced by Pydantic models at the
orchestration boundary, not inside each model call.

**Why.** Forcing structured output on every provider adds failure modes
(schema disagreements, tool-only providers) that v1 does not need. The
`TaskResult` boundary gives coordinators typed data where it matters.

**Cost.** Findings/files-modified are model-authored text within a
structured envelope, not extracted facts. Native `output_type=TaskResult`
per agent is a natural follow-up, isolated to `AgentFactory`.

## Tradeoff 10: Mock provider in the routing chain

**Decision.** `mock:` is a real provider — last in the auto-routing order,
always available.

**Why.** Demos, onboarding, and CI run with zero configuration, through the
same code path as real providers (not a bypass).

**Cost.** A misconfigured environment (missing keys) silently degrades to
mock output unless `doctor`/`status` is checked. `run` prints the effective
model in verbose mode; doctor flags "no providers available".

## Tradeoff 11: Skills — progressive disclosure vs. always-injected context

**Decision.** Skills (`SKILL.md` instruction packs) are discovered at
startup but only their name + one-line description enter the system
prompt; the full body is fetched on demand through a read-only `skill`
tool whose argument is a skill *name*, never a path. Plugins are plain git
repositories shallow-cloned into `~/.om-harness/plugins` by the CLI (no
registry, no server, no manifest requirement); plugin skills register
under `<plugin>:<skill>` with the plain name filled only when free.

**Why.** Injecting every skill's full body would reintroduce the
mega-prompt the assembler exists to prevent (a dozen skills is easily
20k+ characters on every turn, used or not). One-line descriptions cost
almost nothing and let the model decide when to pull instructions. The
name-not-path tool argument means skills can live outside the repository
(`~/.agents/skills`) without opening a path-traversal hole through the
repo-confinement rule. Git-clone-as-install inherits transport security,
mirrors how users already share agent packs (e.g. obra/superpowers), and
gives update/uninstall for free — a plugin *format* (tools, commands,
entry points) would be speculative infrastructure until a second
capability is actually needed.

**Cost.** Every skill invocation costs one extra tool round-trip, and a
model that ignores the `skill` tool works from the description alone.
Discovery reads `~/.agents/skills`, which the harness does not own —
foreign files there are tolerated (malformed skills are skipped) but never
validated beyond frontmatter. Plugin skills are picked up only at the
next harness start, not mid-session. Frontmatter parsing is a minimal
`key: value` reader rather than a YAML dependency; richer frontmatter
(lists, nesting) will need a real parser.

## Tradeoff 12: Seq-cursor event draining vs. positional offsets

**Decision.** Every published event carries a monotonic `seq` stamped by
the bus; consumers drain with `bus.cursor` / `bus.since(cursor)` instead of
positional slices of the bounded history (`history[offset:]`). All live
streaming, end-of-turn sweeps, persistence, CLI output, and web replay use
this cursor.

**Why.** Positional offsets are silently wrong once the bounded deque
starts evicting: the REPL live pump froze after ~1000 streamed deltas
(≈ 4.8k characters of thinking text) while the agent kept running, every
later turn rendered nothing live, and persistence quietly stopped saving
events. A seq cursor is eviction-proof, costs one integer per event, and
is what makes live token streaming compatible with a bounded history at
all.

**Cost.** Events evicted before a consumer drains are gone — that is the
point of bounded memory; a consumer must keep up within the 10,000-event
window. Each publish does one extra `model_copy` to stamp the seq.

## Tradeoff 13: Timeouts are nullable settings ("off"), not magic numbers

**Decision.** `agent_timeout_seconds` / `tool_timeout_seconds` are
`float | None`; `off`/`none`/`0` parse to `None`, which disables the
timeout. `/timeout` and `/config set agent_timeout|tool_timeout <seconds|off>`
mutate the live config and persist; TOML (no null) stores the string
`"off"`, which the loader's validator parses back to `None`. Tool timeouts
propagate immediately through the shared live `ToolContext`.

**Why.** `asyncio.timeout(None)` and `wait_for(..., timeout=None)` already
mean "no timeout", so `None` requires no changes at enforcement sites and
no sentinel arithmetic. A magic large number (99999) lies in status output
and still fires eventually; `0` is kept as an `off` alias because a
zero-second timeout is meaningless.

**Cost.** A string can appear in a nominally numeric field (accepted by
the loader validator and re-serialized as `"off"`), and enforcement sites
must tolerate `None` — asyncio does natively, and tests cover the
round-trip. Long agent turns without a timeout can hang until the user
interrupts; that is exactly what `off` asks for.

## Compatibility notes

- Python ≥ 3.11 (StrEnum, asyncio.timeout, tomllib).
- PydanticAI 2.x: `Agent(instructions=…)`, `event_stream_handler`,
  `RunUsage`, `UsageLimits`, `FallbackModel`, `FunctionModel`. Verified
  against 2.40; the private `function_schema` helper is isolated in
  `runtime/agent.py`.
- Windows is a first-class platform (CI matrix); path handling is
  `pathlib`-based with posix-style repo-relative names in context/events.

## Future extension points

Remote execution (networked `LocalStore`/`EventBus`), shared agent pools,
hosted web app (same facade), more providers, MCP toolsets (PydanticAI
capability), richer memory (checkpoint side-channels), evaluation harness
(run the same scripted models against suites), team governance (approval
policies are already a policy object), plugin capabilities beyond skills
(slash commands, tools, Python entry points — `plugins/` already owns the
install/discovery lifecycle and the manifest is the versioned seam).
