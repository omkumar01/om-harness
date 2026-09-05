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

**Cost.** `run_shell` cannot run pipelines or redirections (`|`, `>`,
`;`). Users needing them run explicit script files. This trades raw power
for an auditable, injection-resistant surface — a deliberate v1 posture
that can be revisited with command allowlists or an interactive shell mode.

## Tradeoff 7: One event bus for everything

**Decision.** A single async pub/sub bus; UI, persistence, and tracing are
all subscribers; redaction happens at publish.

**Why.** One mechanism to test; guarantees the terminal, web, and logs see
identical histories; keeps `emit` cheap (sync publish into queues, bounded
history, offset-based persistence after a run to avoid async races).

**Cost.** The bus history is in-memory per process. Long-running hosted
deployments will want the JSONL log (or a remote bus) as the source of
truth — the interface is the extension point.

## Tradeoff 8: Terminal UI scope

**Decision.** Compact-by-default replay of filtered events plus a summary
panel; live token streaming is not implemented in v1.

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
policies are already a policy object).
