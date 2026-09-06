"""Harness: the composition root binding config, providers, tools, runtime,
orchestration, and persistence behind one small facade.

Both the CLI and the web reference client consume this class (and the event
stream it publishes) — neither duplicates runtime logic.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from om_harness.config.loader import ApprovalPolicy, HarnessConfig, load_config
from om_harness.config.paths import user_cache_dir, user_skills_dir
from om_harness.config.secrets import SecretRedactor
from om_harness.context.assembler import ContextAssembler
from om_harness.context.repo_index import RepoIndex
from om_harness.models.events import EventType, make_event
from om_harness.models.session import Checkpoint
from om_harness.models.task import (
    Plan,
    RunStatus,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
    TokenUsage,
)
from om_harness.orchestration.coordinator import Coordinator
from om_harness.orchestration.planner import Planner
from om_harness.plugins import load_plugins, merge_plugin_skills
from om_harness.providers.models_json import load_models_json
from om_harness.providers.registry import ProviderRegistry
from om_harness.providers.router import ModelRouter
from om_harness.runtime.bus import EventBus
from om_harness.runtime.runner import AgentRunner
from om_harness.runtime.session import SessionManager
from om_harness.runtime.store import LocalStore
from om_harness.skills import Skill, discover_skills
from om_harness.tools import build_default_registry
from om_harness.tools.approval import ApprovalEngine
from om_harness.tools.base import ToolContext
from om_harness.tools.registry import GuardedToolExecutor
from om_harness.tools.skill import SkillTool

STATE_DIR_NAME = ".om-harness"
GITIGNORE_MARKER = ".om-harness/"

Confirmer = Callable[[str, str], Awaitable[bool]]


class DoctorItem(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class DoctorReport(BaseModel):
    items: list[DoctorItem] = Field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(item.ok for item in self.items)


class RunOutcome(BaseModel):
    session_id: str
    run_id: str
    plan: Plan
    results: list[TaskResult]
    status: RunStatus = RunStatus.completed
    usage: TokenUsage = Field(default_factory=TokenUsage)
    checkpoint_id: str | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None

    @property
    def summary(self) -> str:
        lines = [f"{r.task_id}: {r.status.value} - {r.summary}" for r in self.results]
        return "\n".join(lines)


class Harness:
    def __init__(
        self,
        repo_root: Path,
        config: HarnessConfig | None = None,
        *,
        env: Mapping[str, str] | None = None,
        bus: EventBus | None = None,
        interactive: bool = False,
        confirmer: Confirmer | None = None,
        approval_policy: str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.env = env if env is not None else os.environ
        if config is None:
            self.config = load_config(self.repo_root, env=self.env)
        else:
            self.config = config
        if approval_policy:
            self.config = self.config.model_copy(
                update={
                    "approval": self.config.approval.model_copy(
                        update={"policy": ApprovalPolicy(approval_policy)}
                    )
                }
            )

        # Custom providers from models.json (local gateways, private
        # endpoints). Loaded before the bus so inline keys can be registered
        # with the secret redactor.
        self.models_json = load_models_json(self.repo_root, self.env)

        redactor = SecretRedactor.from_env(
            self.env,
            extra=self.models_json.inline_api_keys() if self.models_json else None,
        )
        self.bus = bus or EventBus(redactor=redactor)
        self.store = LocalStore(self.repo_root / STATE_DIR_NAME)
        self.sessions = SessionManager(self.store, self.bus)
        self.interactive = interactive

        self.provider_registry = ProviderRegistry(self.env, custom=self.models_json)
        self.router = ModelRouter(self.config.routing, self.provider_registry)
        self.repo_index = RepoIndex(
            self.repo_root,
            self.config.context.max_repo_index_files,
            cache_dir=user_cache_dir(),
            cache_ttl_hours=self.config.context.index_cache_ttl_hours,
        )
        self.skills = self._resolve_skills()
        self.assembler = ContextAssembler(self.config, self.repo_index, skills=self.skills)

        tool_ctx = ToolContext(
            repo_root=self.repo_root,
            tool_timeout_seconds=self.config.tool_timeout_seconds,
            max_file_read_chars=self.config.context.max_file_read_chars,
        )
        self.registry = build_default_registry(tool_ctx)
        if self.skills:
            self.registry.register(SkillTool(tool_ctx, skills=self.skills))
        self.approval = ApprovalEngine(
            self.config.approval, interactive=interactive, confirmer=confirmer
        )
        self.executor = GuardedToolExecutor(self.registry, self.approval, self.bus)

        self.planner = Planner(self.config)
        self.runner = AgentRunner(
            executor=self.executor,
            assembler=self.assembler,
            router=self.router,
            provider_registry=self.provider_registry,
            config=self.config,
            bus=self.bus,
        )
        self.coordinator = Coordinator(runner=self.runner, config=self.config, bus=self.bus)

    # -- repo setup ----------------------------------------------------------

    def _resolve_skills(self) -> dict[str, Skill]:
        """Discover skills: user dir, config extra dirs, then repo (repo wins).

        Installed plugins are then folded in under namespaced names
        (``plugin:skill``); their plain names fill only free slots, so
        user/repo skills keep precedence on collisions.
        """
        if not self.config.skills.enabled:
            return {}
        sources: list[tuple[Path, str]] = [
            (user_skills_dir(), "user"),
        ]
        for extra in self.config.skills.extra_dirs:
            path = Path(extra)
            if not path.is_absolute():
                path = self.repo_root / path
            sources.append((path, "extra"))
        sources.append((self.repo_root / ".agents" / "skills", "repo"))
        skills = discover_skills(sources)
        return merge_plugin_skills(skills, load_plugins())

    @staticmethod
    def init_repo(repo_root: Path) -> None:
        """Prepare a repository: state dir + gitignore entry (idempotent)."""
        repo_root = Path(repo_root)
        (repo_root / STATE_DIR_NAME).mkdir(parents=True, exist_ok=True)
        gitignore = repo_root / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if GITIGNORE_MARKER not in existing:
            with gitignore.open("a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(f"# om-harness runtime state\n{GITIGNORE_MARKER}\n")

    # -- runs ----------------------------------------------------------------

    async def run(
        self,
        goal: str,
        *,
        strategy: str | None = None,
        tasks: list[Task] | None = None,
        model_override: str | None = None,
        retries: int = 0,
        session_id: str | None = None,
        resume: bool = False,
    ) -> RunOutcome:
        """Execute one goal end-to-end: plan, coordinate, persist, checkpoint."""
        session = self._resolve_session(session_id=session_id, resume=resume)
        # Events are persisted after the run from the bus history (bounded,
        # deterministic) — no pump race with cancellation.
        event_offset = len(self.bus.history)
        run = self.sessions.start_run(
            session,
            goal=goal,
            strategy=self.planner.decide(goal, strategy_override=strategy, explicit_tasks=tasks),
        )

        self.runner.session_id = session.session_id
        self.runner.run_id = run.run_id
        self.coordinator.session_id = session.session_id
        self.coordinator.run_id = run.run_id
        self.executor.session_id = session.session_id
        self.executor.run_id = run.run_id

        plan = self.planner.build_plan(goal, strategy=strategy, tasks=tasks)
        self.bus.publish_sync(
            make_event(
                EventType.PLAN_CREATED,
                session_id=session.session_id,
                run_id=run.run_id,
                strategy=plan.strategy.value,
                task_count=len(plan.tasks),
                rationale=plan.rationale,
            )
        )

        started = time.monotonic()
        status = RunStatus.completed
        error: str | None = None
        try:
            results = await self.coordinator.execute_plan(
                plan, retries=retries, model_override=model_override
            )
        except asyncio.CancelledError:
            status = RunStatus.cancelled
            results = []
            error = "run cancelled"
            raise
        except Exception as exc:
            status = RunStatus.failed
            results = []
            error = str(exc)
        finally:
            elapsed = time.monotonic() - started

        usage = TokenUsage()
        for result in results:
            usage = usage.add(result.usage)

        # Task failures must not hide behind a "completed" run: surface them.
        if status == RunStatus.completed and any(r.status == TaskStatus.failed for r in results):
            status = RunStatus.failed
            failed = [r.task_id for r in results if r.status == TaskStatus.failed]
            error = "task(s) failed: " + ", ".join(failed)

        self.sessions.finish_run(
            session, run, status=status, error=error, usage=usage, task_results=results
        )

        checkpoint: Checkpoint | None = None
        if status == RunStatus.completed:
            checkpoint = self.sessions.save_checkpoint(
                session,
                run,
                label=f"after-{run.run_id}",
                summary=RunOutcome(
                    session_id=session.session_id,
                    run_id=run.run_id,
                    plan=plan,
                    results=results,
                ).summary[:2000],
                plan=plan,
                task_results=results,
                completed_task_ids=[r.task_id for r in results if r.status == TaskStatus.completed],
            )

        for event in self.bus.history[event_offset:]:
            if event.session_id == session.session_id:
                self.store.append_event(event)

        return RunOutcome(
            session_id=session.session_id,
            run_id=run.run_id,
            plan=plan,
            results=results,
            status=status,
            usage=usage,
            checkpoint_id=checkpoint.checkpoint_id if checkpoint else None,
            elapsed_seconds=round(elapsed, 3),
            error=error,
        )

    async def chat_turn(
        self, session_id: str, user_text: str, *, model_override: str | None = None
    ) -> str:
        """One interactive chat turn. Errors surface in the reply text."""
        session = self.sessions.load(session_id)
        self.sessions.add_message(session, role="user", content=user_text)
        outcome = await self.run(user_text, model_override=model_override, session_id=session_id)

        if outcome.results:
            result = outcome.results[-1]
            if result.status.value == "completed":
                assistant_text = result.summary
            else:
                detail = "; ".join(result.errors) if result.errors else "no details"
                assistant_text = f"error ({result.status.value}): {detail}"
        elif outcome.error:
            assistant_text = f"error: {outcome.error}"
        else:
            assistant_text = "(no response)"

        session = self.sessions.load(session_id)
        self.sessions.add_message(session, role="assistant", content=assistant_text)
        return assistant_text

    def _resolve_session(self, session_id: str | None, resume: bool) -> Any:
        if session_id:
            return self.sessions.load(session_id)
        if resume:
            latest = self.sessions.latest(self.repo_root)
            if latest is not None:
                self.bus.publish_sync(
                    make_event(EventType.SESSION_RESUMED, session_id=latest.session_id)
                )
                return latest
        return self.sessions.create(repo_root=str(self.repo_root))

    # -- introspection -------------------------------------------------------

    def status(self) -> dict[str, Any]:
        sessions = self.sessions.list_sessions()
        repo_sessions = [s for s in sessions if s.repo_root == str(self.repo_root)]
        checkpoints = sum(len(self.store.list_checkpoints(s.session_id)) for s in repo_sessions)
        latest = repo_sessions[0] if repo_sessions else None
        return {
            "repo_root": str(self.repo_root),
            "skills": sorted(self.skills),
            # The model a general task would actually use (accounts for which
            # providers have keys configured).
            "default_model": self.router.select(TaskType.general),
            "configured_default_model": self.config.routing.default_model,
            "available_providers": [
                info.name for info in self.provider_registry.available_providers() if info.available
            ],
            "custom_providers": self.provider_registry.custom_provider_names,
            "sessions": len(repo_sessions),
            "checkpoints": checkpoints,
            "latest_session": (
                {
                    "session_id": latest.session_id,
                    "status": latest.status.value,
                    "messages": len(latest.messages),
                    "runs": len(latest.runs),
                }
                if latest
                else None
            ),
            "approval_policy": self.config.approval.policy.value,
            "tools": self.registry.names(),
        }

    def doctor(self) -> DoctorReport:
        items: list[DoctorItem] = []

        in_git = (self.repo_root / ".git").exists()
        items.append(
            DoctorItem(
                name="git_repository",
                ok=in_git,
                detail="repository root"
                if in_git
                else "not a git repository (git-aware tools limited)",
            )
        )

        items.append(
            DoctorItem(
                name="config",
                ok=True,
                detail=f"default model {self.config.routing.default_model}, "
                f"approval {self.config.approval.policy.value}",
            )
        )

        try:
            probe_dir = self.repo_root / STATE_DIR_NAME
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe = probe_dir / f".probe-{uuid.uuid4().hex[:8]}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            items.append(DoctorItem(name="state_store", ok=True, detail=str(probe_dir)))
        except OSError as exc:
            items.append(DoctorItem(name="state_store", ok=False, detail=str(exc)))

        providers = self.provider_registry.available_providers()
        available = [p.name for p in providers if p.available]
        detail = ", ".join(available) if available else "none available"
        items.append(
            DoctorItem(
                name="providers",
                ok=len(available) > 0,
                detail=f"{detail} (keys read from environment only)",
            )
        )

        if self.models_json is not None:
            names = self.provider_registry.custom_provider_names
            detail = f"{len(names)} custom provider(s) from models.json: {', '.join(names)}"
        else:
            detail = "no models.json found (built-in providers only)"
        items.append(DoctorItem(name="models_json", ok=True, detail=detail))

        git_version = self._git_version()
        items.append(
            DoctorItem(
                name="git_cli",
                ok=git_version is not None,
                detail=git_version or "git executable not found",
            )
        )
        return DoctorReport(items=items)

    @staticmethod
    def _git_version() -> str | None:
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return None
