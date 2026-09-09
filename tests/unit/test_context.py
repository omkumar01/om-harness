"""Contract tests for context management: budget ledger, repo index, assembler.

These tests prove the context-minimization promises:
- repo context is built once and reused (not re-derived per call),
- old history is summarized/trimmed rather than resent in full,
- agents receive structured TaskResults, not transcripts,
- every context component is accounted for in a token report.
"""

from __future__ import annotations

from typing import Any

from om_harness.config.loader import HarnessConfig
from om_harness.context.assembler import ContextAssembler
from om_harness.context.budget import ContextLedger, estimate_tokens
from om_harness.context.repo_index import RepoIndex
from om_harness.models.task import TaskResult, TaskStatus

# -- token estimation ---------------------------------------------------------


def test_estimate_tokens_is_stable_heuristic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100  # 4 chars per token heuristic


def test_ledger_accumulates_categories() -> None:
    ledger = ContextLedger()
    ledger.record("system_prompt", "s" * 400)
    ledger.record("system_prompt", "s" * 400)
    ledger.record("repo_context", "r" * 800)
    report = ledger.report()
    assert report.items["system_prompt"] == 200
    assert report.items["repo_context"] == 200
    assert report.total_tokens == 400


# -- repo index ---------------------------------------------------------------


def test_repo_index_builds_and_caches(tmp_path: Any) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "src" / "b.py").write_text("y = 2\n")
    (tmp_path / "README.md").write_text("hello\n")
    index = RepoIndex(tmp_path)
    index.build()
    first_built_at = index.built_at
    first_summary = index.summary()
    assert "src/a.py" in first_summary
    # Rebuild is a no-op while cached (build once per session).
    index.build()
    assert index.built_at == first_built_at


def test_repo_index_summary_respects_cap(tmp_path: Any) -> None:
    for i in range(30):
        (tmp_path / f"f{i:02}.py").write_text("x\n")
    index = RepoIndex(tmp_path, max_files=10)
    index.build()
    summary = index.summary()
    assert summary.count(".py") <= 11  # 10 files + "+N more" line
    assert "more files" in summary


def test_repo_index_invalidator(tmp_path: Any) -> None:
    (tmp_path / "a.py").write_text("x\n")
    index = RepoIndex(tmp_path)
    index.build()
    (tmp_path / "b.py").write_text("y\n")
    index.invalidate()
    index.build()
    assert "b.py" in index.summary()


# -- assembler ----------------------------------------------------------------


def _assembler(tmp_path: Any) -> ContextAssembler:
    (tmp_path / "main.py").write_text("print('hi')\n")
    return ContextAssembler(config=HarnessConfig(), repo_index=RepoIndex(tmp_path))


def test_role_prompts_are_small_and_distinct(tmp_path: Any) -> None:
    assembler = _assembler(tmp_path)
    prompts = {
        role: assembler.system_prompt(role)
        for role in ("planner", "explorer", "implementer", "reviewer", "chat")
    }
    assert len(set(prompts.values())) == 5
    for role, prompt in prompts.items():
        assert 0 < len(prompt) < 1200, f"{role} prompt too large: {len(prompt)} chars"


def test_assemble_includes_repo_context_and_instruction(tmp_path: Any) -> None:
    assembler = _assembler(tmp_path)
    assembled = assembler.assemble(
        role="implementer",
        instruction="Fix the failing test in main.py",
    )
    assert "Fix the failing test" in assembled.user_prompt
    assert "main.py" in assembled.repo_context
    assert "print" not in assembled.system_prompt  # role prompt stays minimal


def test_system_prompt_lists_available_skills(tmp_path: Any) -> None:
    from om_harness.skills import Skill

    skills = {"analyse": Skill(name="analyse", description="pick a method", path=tmp_path / "x")}
    assembler = ContextAssembler(
        config=HarnessConfig(), repo_index=RepoIndex(tmp_path), skills=skills
    )
    prompt = assembler.system_prompt("chat")
    assert "Available skills" in prompt
    assert "analyse" in prompt
    assert "pick a method" in prompt
    assert "`skill` tool" in prompt


def test_system_prompt_unchanged_without_skills(tmp_path: Any) -> None:
    plain = ContextAssembler(config=HarnessConfig(), repo_index=RepoIndex(tmp_path))
    with_empty = ContextAssembler(config=HarnessConfig(), repo_index=RepoIndex(tmp_path), skills={})
    assert plain.system_prompt("chat") == with_empty.system_prompt("chat")


def test_history_beyond_cap_is_trimmed_not_resent(tmp_path: Any) -> None:
    from om_harness.models.session import Message, MessageRole

    assembler = ContextAssembler(config=HarnessConfig(context={"max_history_messages": 6}))
    history = []
    for i in range(20):
        history.append(
            Message(role=MessageRole.user, content=f"old message number {i} " + "pad " * 50)
        )
        history.append(Message(role=MessageRole.assistant, content=f"reply {i} " + "pad " * 50))
    assembled = assembler.assemble(role="chat", instruction="next step", history=history)
    rendered = assembled.render_history()
    assert len(rendered) <= 6
    assert (
        "earlier conversation" in rendered[0].content.lower()
        or "summar" in rendered[0].content.lower()
    )
    # Newest messages survive trimming.
    assert "reply 19" in rendered[-1].content


def test_prior_results_render_compactly(tmp_path: Any) -> None:
    assembler = _assembler(tmp_path)
    results = [
        TaskResult(
            task_id="explore-1",
            status=TaskStatus.completed,
            summary="Found the bug in parser.py line 42",
            findings=["parser.py:42 divides by zero"],
            files_modified=[],
        ),
        TaskResult(
            task_id="impl-1",
            status=TaskStatus.failed,
            summary="patch failed",
            errors=["edit_file: not found"],
        ),
    ]
    assembled = assembler.assemble(
        role="implementer", instruction="continue", prior_results=results
    )
    assert "parser.py line 42" in assembled.user_prompt
    assert "FAILED" in assembled.user_prompt
    assert "patch failed" in assembled.user_prompt


def test_context_report_accounts_for_components(tmp_path: Any) -> None:
    assembler = _assembler(tmp_path)
    assembled = assembler.assemble(role="implementer", instruction="do the thing")
    report = assembled.report
    assert report.items.get("system_prompt", 0) > 0
    assert report.items.get("repo_context", 0) > 0
    assert report.items.get("user_prompt", 0) > 0
    assert report.total_tokens == sum(report.items.values())


# -- plan mode -----------------------------------------------------------------


def test_plan_mode_prompt_injected_only_when_active() -> None:
    assembler = ContextAssembler(config=HarnessConfig())
    assert "Mode: plan" not in assembler.system_prompt("implementer")
    assembler.plan_mode = True
    prompt = assembler.system_prompt("implementer")
    assert "Mode: plan" in prompt
    assert "Do not modify files" in prompt
    # Role prompt is still present alongside the plan-mode addition.
    assert "Role: implementer" in prompt


def test_plan_mode_prompt_defaults_off_for_new_assembler() -> None:
    assembler = ContextAssembler(config=HarnessConfig())
    assert assembler.plan_mode is False
