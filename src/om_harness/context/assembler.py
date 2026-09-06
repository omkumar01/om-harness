"""Scoped context assembly: small role prompts, selective history, reports.

Design rules enforced here (and tested):
- system prompts are tiny and role-scoped; there is no universal mega-prompt,
- repository context comes from the cached RepoIndex summary, never re-walked,
- history beyond the configured window is replaced by a one-line summary,
- inter-agent data flows through compact TaskResult renderings,
- every component's token estimate is recorded in a ContextReport.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from om_harness.config.loader import HarnessConfig
from om_harness.context.budget import ContextLedger, ContextReport
from om_harness.context.repo_index import RepoIndex
from om_harness.models.session import Message, MessageRole
from om_harness.models.task import TaskResult
from om_harness.skills import Skill, render_skill_list

# Role-scoped system prompts. Each is deliberately tiny: the model's own
# knowledge does the heavy lifting; the prompt only sets role and boundaries.
BASE_PROMPT = (
    "You are om-harness, a coding agent working inside a git repository. "
    "Be concise. Use the provided tools to inspect and change files; never "
    "invent file contents. Report facts, not intentions."
)

ROLE_PROMPTS: dict[str, str] = {
    "planner": (
        "Role: planner. Break the goal into the smallest set of tasks that can "
        "complete it. Prefer one task unless work is clearly independent."
    ),
    "explorer": (
        "Role: explorer. Investigate the repository and answer the question. "
        "Read-only; do not modify files. Return key facts and file paths."
    ),
    "implementer": (
        "Role: implementer. Make the requested code changes with the tools. "
        "Keep edits minimal and run tests when available."
    ),
    "reviewer": (
        "Role: reviewer. Inspect the described changes for correctness and "
        "risks. Read-only. List concrete problems, or say it looks correct."
    ),
    "chat": ("Role: assistant. Help the developer with their repository interactively."),
}


def render_task_results(results: list[TaskResult]) -> str:
    """Compact, structured rendering of prior agent outputs (no transcripts)."""
    if not results:
        return ""
    lines = ["Results from previous tasks:"]
    for result in results:
        status = result.status.value.upper()
        lines.append(f"- [{result.task_id}] {status}: {result.summary}")
        for finding in result.findings:
            lines.append(f"    finding: {finding}")
        if result.files_modified:
            lines.append(f"    files: {', '.join(result.files_modified)}")
        for error in result.errors:
            lines.append(f"    error: {error}")
    return "\n".join(lines)


def summarize_history(history: list[Message], keep_last: int) -> str:
    """Extractive, model-free summary of older conversation turns."""
    if not history:
        return ""
    user_goals = [m.content.splitlines()[0][:120] for m in history if m.role == MessageRole.user]
    goals = "; ".join(user_goals[-3:])
    return f"[Earlier conversation summarized: {goals}]"


class AssembledContext(BaseModel):
    """Everything one agent invocation will receive, plus its token report."""

    system_prompt: str
    user_prompt: str
    repo_context: str = ""
    history: list[Message] = Field(default_factory=list)
    report: ContextReport = Field(default_factory=ContextReport)

    def render_history(self) -> list[Message]:
        return list(self.history)


class ContextAssembler:
    def __init__(
        self,
        config: HarnessConfig,
        repo_index: RepoIndex | None = None,
        skills: dict[str, Skill] | None = None,
    ) -> None:
        self.config = config
        self.repo_index = repo_index
        self.skills: dict[str, Skill] = dict(skills or {})
        self._repo_context_cache: str | None = None

    def system_prompt(self, role: str) -> str:
        base = BASE_PROMPT
        role_prompt = ROLE_PROMPTS.get(role)
        if role_prompt is None:
            role_prompt = ROLE_PROMPTS["chat"]
        prompt = f"{base}\n{role_prompt}"
        skills_section = self._skills_section()
        if skills_section:
            prompt = f"{prompt}\n{skills_section}"
        return prompt

    def _skills_section(self) -> str:
        """Tiny listing of available skills; empty when none are installed."""
        if not self.skills:
            return ""
        listing = render_skill_list(self.skills)
        return (
            "Available skills (one per line, name: description):\n"
            f"{listing}\n"
            "When a task matches a skill, load its full instructions with the "
            "`skill` tool before proceeding."
        )

    def repo_context(self, max_files: int | None = None) -> str:
        if self._repo_context_cache is None and self.repo_index is not None:
            self._repo_context_cache = self.repo_index.summary(max_files)
        return self._repo_context_cache or ""

    def assemble(
        self,
        role: str,
        instruction: str,
        *,
        history: list[Message] | None = None,
        prior_results: list[TaskResult] | None = None,
        include_repo: bool = True,
    ) -> AssembledContext:
        ctx_config = self.config.context
        ledger = ContextLedger()

        system_prompt = self.system_prompt(role)
        ledger.record("system_prompt", system_prompt)

        repo_context = self.repo_context() if include_repo else ""
        if repo_context:
            ledger.record("repo_context", repo_context)

        # History: trim to the configured window; summarize the dropped tail
        # instead of resending it. The summary travels as the first history
        # entry so downstream consumers see one coherent list.
        trimmed: list[Message] = []
        history_note = ""
        if history:
            keep = ctx_config.max_history_messages
            if len(history) > keep:
                dropped = history[:-keep]
                history_note = summarize_history(dropped, keep_last=keep)
                # The summary counts toward the window: keep one fewer raw
                # message so the total stays within max_history_messages.
                trimmed = [Message(role=MessageRole.system, content=history_note)]
                trimmed += history[-(keep - 1) :]
            else:
                trimmed = list(history)
            if history_note:
                ledger.record("history_summary", history_note)
            for message in trimmed:
                ledger.record("history", message.content)

        parts: list[str] = []
        if repo_context:
            parts.append(repo_context)
        if history_note:
            parts.append(history_note)
        results_text = render_task_results(prior_results or [])
        if results_text:
            parts.append(results_text)
            ledger.record("prior_results", results_text)
        parts.append(f"Task: {instruction}")
        user_prompt = "\n\n".join(parts)
        ledger.record("user_prompt", user_prompt)

        return AssembledContext(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            repo_context=repo_context,
            history=trimmed,
            report=ledger.report(),
        )


__all__ = [
    "ROLE_PROMPTS",
    "AssembledContext",
    "ContextAssembler",
    "render_task_results",
    "summarize_history",
]
