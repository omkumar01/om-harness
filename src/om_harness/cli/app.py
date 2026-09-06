"""om-harness CLI: the developer entry point.

Commands: init, run, chat, agent, providers, doctor, status, resume, config.
All commands accept ``--json`` for automation; runs are compact by default
with ``--verbose``/``--debug`` traces available explicitly.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from om_harness import __version__

app = typer.Typer(
    name="om-harness",
    help="A context-efficient AI coding-agent harness for real repositories.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
config_app = typer.Typer(
    help="Configuration helpers.", no_args_is_help=True, invoke_without_command=False
)
app.add_typer(config_app, name="config")

console = Console()
err_console = Console(stderr=True)

STATE_DIR = ".om-harness"


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"om-harness {__version__}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """om-harness: orchestrate coding agents in your repository.

    Run without a subcommand to start an interactive chat session.
    """
    if ctx.invoked_subcommand is None:
        launch_interactive()


def launch_interactive(
    repo: str | None = None,
    session: str | None = None,
    resume: bool = False,
    model: str | None = None,
    approval_policy: str | None = None,
) -> None:  # pragma: no cover - interactive entry point (tested via monkeypatch)
    """First-class default: `om-harness` drops you into a chat session."""
    from om_harness.config.paths import ensure_user_dirs, user_config_dir
    from om_harness.ui.repl import ChatRepl

    first_run = ensure_user_dirs()
    harness = _build_harness(repo, False, False, False, model, approval_policy)
    renderer = harness.renderer
    if first_run:
        renderer.console.print(
            f"[green]Welcome to om-harness[/] — user config at {user_config_dir()}"
        )
        renderer.console.print(
            "[dim]Set provider API keys in your environment (OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, GOOGLE_API_KEY) or add providers to "
            "~/.om-harness/config/models.json. Type /help for commands.[/]"
        )
    session_obj = harness._resolve_session(session_id=session, resume=resume)
    repl = ChatRepl(harness, session_id=session_obj.session_id, verbosity=harness.config.verbosity)
    repl.run_forever()


def run_app() -> None:
    """Console-script entry point: dispatch the Typer application."""
    app()


if __name__ == "__main__":  # python -m om_harness.cli.app
    app()


def _repo_root(repo: str | None) -> Path:
    return Path(repo).resolve() if repo else Path.cwd().resolve()


def _build_harness(
    repo: str | None,
    json_mode: bool,
    verbose: bool,
    debug: bool,
    model: str | None,
    approval_policy: str | None,
) -> Any:  # Harness instance (typed Any to keep CLI import light)
    from om_harness.config.loader import RoutingConfig, Verbosity, load_config
    from om_harness.harness import Harness
    from om_harness.ui.terminal import TerminalRenderer

    renderer = TerminalRenderer()

    async def _confirm(tool_name: str, reason: str) -> bool:
        return renderer.confirm(tool_name, reason)

    root = _repo_root(repo)
    config = load_config(root)
    if model:
        routing = RoutingConfig(**{**config.routing.model_dump(), "default_model": model})
        config = config.model_copy(update={"routing": routing})
    verbosity = Verbosity.debug if debug else (Verbosity.verbose if verbose else Verbosity.compact)
    config = config.model_copy(update={"verbosity": verbosity})
    if approval_policy:
        from om_harness.config.loader import ApprovalConfig, ApprovalPolicy

        approval = ApprovalConfig(
            policy=ApprovalPolicy(approval_policy), allowlist=config.approval.allowlist
        )
        config = config.model_copy(update={"approval": approval})

    harness = Harness(
        repo_root=root,
        config=config,
        interactive=not json_mode,
        confirmer=_confirm if not json_mode else None,
    )
    harness.renderer = renderer  # type: ignore[attr-defined]
    return harness


def _print_events(harness, offset: int, renderer, verbosity) -> None:  # type: ignore[no-untyped-def]
    from om_harness.ui.components import event_to_display

    for event in harness.bus.history[offset:]:
        display = event_to_display(event, verbosity)
        if display is not None:
            renderer.line(display)


def _json_payload(data) -> str:  # type: ignore[no-untyped-def]
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(mode="json"), indent=2, default=str)
    return json.dumps(data, indent=2, default=str)


@app.command()
def init(
    repo: str = typer.Option(None, "--repo", help="Repository root (default: current directory)."),
) -> None:
    """Initialize om-harness state for this repository."""
    from om_harness.harness import Harness

    root = _repo_root(repo)
    Harness.init_repo(root)
    console.print(f"[green]✔[/] initialized {root / STATE_DIR}")


@app.command()
def run(
    goal: str = typer.Argument(..., help="What the agent should accomplish."),
    repo: str = typer.Option(None, "--repo"),
    strategy: str = typer.Option(
        None, "--strategy", help="single | sequential | parallel | reviewer"
    ),
    model: str = typer.Option(None, "--model", help="Model override, e.g. openai:gpt-4o"),
    session: str = typer.Option(None, "--session", help="Existing session id to continue."),
    resume: bool = typer.Option(False, "--resume", help="Resume the latest session in this repo."),
    retries: int = typer.Option(0, "--retries", help="Retries per task on failure."),
    json_mode: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    debug: bool = typer.Option(False, "--debug"),
    approval_policy: str = typer.Option(None, "--approval-policy"),
) -> None:
    """Run one coding-agent goal end-to-end."""
    from om_harness.ui.components import outcome_to_summary

    harness = _build_harness(repo, json_mode, verbose, debug, model, approval_policy)
    renderer = harness.renderer
    offset = len(harness.bus.history)
    try:
        outcome = asyncio.run(
            harness.run(
                goal,
                strategy=strategy,
                model_override=model,
                session_id=session,
                resume=resume,
                retries=retries,
            )
        )
    except Exception as exc:
        if json_mode:
            typer.echo(_json_payload({"error": str(exc)}))
        else:
            renderer.error(str(exc))
        raise typer.Exit(1) from exc

    if json_mode:
        typer.echo(_json_payload(outcome))
    else:
        _print_events(harness, offset, renderer, harness.config.verbosity)
        renderer.summary(outcome_to_summary(outcome))
    if outcome.status.value != "completed":
        raise typer.Exit(1)


@app.command()
def chat(
    repo: str = typer.Option(None, "--repo"),
    session: str = typer.Option(None, "--session"),
    resume: bool = typer.Option(False, "--resume", help="Continue latest session."),
    model: str = typer.Option(None, "--model"),
    json_mode: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    debug: bool = typer.Option(False, "--debug"),
    approval_policy: str = typer.Option(None, "--approval-policy"),
) -> None:
    """Interactive chat session (same as running bare `om-harness`)."""
    launch_interactive(
        repo=repo, session=session, resume=resume, model=model, approval_policy=approval_policy
    )


@app.command()
def agent(
    instruction: str = typer.Argument(None, help="Single-agent instruction."),
    repo: str = typer.Option(None, "--repo"),
    role: str = typer.Option("explorer", "--role", help="Agent role for the task."),
    model: str = typer.Option(None, "--model"),
    list_tools: bool = typer.Option(False, "--list-tools", help="List available tools and exit."),
    json_mode: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    debug: bool = typer.Option(False, "--debug"),
    approval_policy: str = typer.Option(None, "--approval-policy"),
) -> None:
    """Run a single specialist agent (no planning), or list tools."""
    from om_harness.models.task import Task, TaskType
    from om_harness.ui.components import outcome_to_summary

    harness = _build_harness(repo, json_mode, verbose, debug, model, approval_policy)
    renderer = harness.renderer

    if list_tools:
        payload = {"tools": harness.registry.specs()}
        typer.echo(_json_payload(payload))
        return

    if not instruction:
        err_console.print("Provide an instruction or use --list-tools.")
        raise typer.Exit(2)

    task_type = TaskType.explore if role == "explorer" else TaskType.implement
    tasks = [
        Task(
            id="agent-1",
            title=instruction[:60],
            instruction=instruction,
            task_type=task_type,
            role=role,
        )
    ]
    offset = len(harness.bus.history)
    outcome = asyncio.run(harness.run(instruction, tasks=tasks, model_override=model))
    if json_mode:
        typer.echo(_json_payload(outcome))
    else:
        _print_events(harness, offset, renderer, harness.config.verbosity)
        renderer.summary(outcome_to_summary(outcome))
    if outcome.status.value != "completed":
        raise typer.Exit(1)


@app.command()
def providers(
    repo: str = typer.Option(None, "--repo"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """List providers (built-in and models.json) and their availability."""
    from om_harness.harness import Harness

    harness = Harness(repo_root=_repo_root(repo))
    infos = harness.provider_registry.available_providers()
    customs = harness.provider_registry.custom_provider_summaries()
    if json_mode:
        typer.echo(
            _json_payload(
                {
                    "providers": [i.model_dump(mode="json") for i in infos],
                    "custom_providers": customs,
                }
            )
        )
        return
    for info in infos:
        state = "[green]available[/]" if info.available else "[dim]no API key[/]"
        console.print(f"{info.name:12} {state}  default: {info.default_model}")
    for custom in customs:
        state = "[green]available[/]" if custom["available"] else "[dim]unavailable[/]"
        console.print(f"{custom['name']:12} {state}  ({custom['api']}, {custom['key_source']} key)")
        for model in custom["models"]:
            console.print(
                f"  {custom['name']}:{model['id']}  "
                f"[dim]tools={model['tool_calling']} vision={model['vision']} "
                f"context={model['context_window'] or '?'}[/]"
            )


@app.command()
def doctor(
    repo: str = typer.Option(None, "--repo"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Diagnose repository, configuration, and provider health."""
    from om_harness.harness import Harness

    harness = Harness(repo_root=_repo_root(repo))
    report = harness.doctor()
    if json_mode:
        typer.echo(_json_payload(report))
        return
    for item in report.items:
        mark = "[green]✔[/]" if item.ok else "[red]✖[/]"
        console.print(f"{mark} {item.name}: {item.detail}")
    if not report.all_ok:
        raise typer.Exit(1)


@app.command()
def status(
    repo: str = typer.Option(None, "--repo"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show session/checkpoint/provider state for this repository."""
    from om_harness.harness import Harness

    harness = Harness(repo_root=_repo_root(repo))
    state = harness.status()
    if json_mode:
        typer.echo(_json_payload(state))
        return
    for key, value in state.items():
        console.print(f"[bold]{key}:[/] {value}")


@app.command()
def resume(
    repo: str = typer.Option(None, "--repo"),
    session: str = typer.Option(None, "--session"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show the latest session/checkpoint and how to continue it."""
    from om_harness.harness import Harness

    harness = Harness(repo_root=_repo_root(repo))
    if session:
        target: Any = harness.sessions.load(session)
    else:
        target = harness.sessions.latest(str(_repo_root(repo)))
    if target is None:
        err_console.print("No sessions found. Run `om-harness run` first.")
        raise typer.Exit(1)
    checkpoints = harness.store.list_checkpoints(target.session_id)
    latest_cp = checkpoints[-1] if checkpoints else None
    payload = {
        "session_id": target.session_id,
        "status": target.status.value,
        "runs": len(target.runs),
        "messages": len(target.messages),
        "checkpoints": [cp.checkpoint_id for cp in checkpoints],
        "latest_checkpoint": latest_cp.model_dump(mode="json") if latest_cp else None,
        "continue_with": f"om-harness run <goal> --session {target.session_id}",
    }
    if json_mode:
        typer.echo(_json_payload(payload))
        return
    console.print(f"session [bold]{target.session_id}[/] ({target.status.value})")
    if latest_cp:
        console.print(f"checkpoint: {latest_cp.checkpoint_id}")
        console.print(f"summary: {latest_cp.summary[:300] or '(empty)'}")
    console.print(payload["continue_with"])


@config_app.command("show")
def config_show(
    repo: str = typer.Option(None, "--repo"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show the effective configuration (env + file + defaults)."""
    from om_harness.harness import Harness

    harness = Harness(repo_root=_repo_root(repo))
    if json_mode:
        typer.echo(_json_payload(harness.config))
        return
    for key, value in harness.config.model_dump(mode="json").items():
        console.print(f"[bold]{key}:[/] {json.dumps(value, default=str)}")


@app.command()
def install(
    source: str = typer.Argument(
        ..., help="Plugin source, e.g. git:github.com/obra/superpowers or a local path."
    ),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Install (or update) a plugin from git; its skills become available."""
    from om_harness.plugins import PluginError, install_plugin

    try:
        plugin = install_plugin(source)
    except PluginError as exc:
        if json_mode:
            typer.echo(_json_payload({"error": str(exc)}))
        else:
            err_console.print(f"install failed: {exc}")
        raise typer.Exit(1) from exc
    skill_names = [s.name for s in plugin.skills]
    if json_mode:
        typer.echo(
            _json_payload(
                {
                    "name": plugin.name,
                    "skills": skill_names,
                    "path": str(plugin.path),
                    "source": plugin.source,
                }
            )
        )
        return
    console.print(
        f"[green]✔[/] installed plugin [bold]{plugin.name}[/] ({len(skill_names)} skills)"
    )
    for name in skill_names:
        console.print(f"  {name}")
    console.print("[dim]Restart om-harness (or start a new run) to pick up the new skills.[/]")


@app.command()
def uninstall(
    name: str = typer.Argument(..., help="Installed plugin name (see `om-harness plugins`)."),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Remove an installed plugin."""
    from om_harness.plugins import PluginError, uninstall_plugin

    try:
        uninstall_plugin(name)
    except PluginError as exc:
        if json_mode:
            typer.echo(_json_payload({"error": str(exc)}))
        else:
            err_console.print(str(exc))
        raise typer.Exit(1) from exc
    if json_mode:
        typer.echo(_json_payload({"uninstalled": name}))
    else:
        console.print(f"[green]✔[/] uninstalled plugin [bold]{name}[/]")


@app.command()
def plugins(
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """List installed plugins and the skills they provide."""
    from om_harness.plugins import load_plugins

    installed = load_plugins()
    if json_mode:
        typer.echo(
            _json_payload(
                {
                    "plugins": [
                        {
                            "name": p.name,
                            "description": p.description,
                            "source": p.source,
                            "path": str(p.path),
                            "skills": [s.name for s in p.skills],
                        }
                        for p in installed
                    ]
                }
            )
        )
        return
    if not installed:
        console.print("No plugins installed. Try: om-harness install git:github.com/<owner>/<repo>")
        return
    for plugin in installed:
        console.print(f"[bold]{plugin.name}[/] {len(plugin.skills)} skills")
        for skill in plugin.skills:
            console.print(f"  {skill.name}: [dim]{skill.description}[/]")
