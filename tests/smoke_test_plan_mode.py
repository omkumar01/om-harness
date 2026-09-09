"""End-to-end smoke test for /plan mode (uses the mock:echo model, no network).

Drives the real ChatRepl.run_forever with a fake prompt session:
  /plan -> read-only turn -> approve -> implement turn -> exit.
Asserts the live approval engine, assembler prompt, policy restore,
and that the plan context is passed to the implementation turn.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="om-smoke-"))
home = tmp / "home"
(home / "config").mkdir(parents=True)
(home / "config" / "config.toml").write_text('[routing]\ndefault_model = "mock:echo"\n')
os.environ["OM_HARNESS_HOME"] = str(home)
os.environ["OM_HARNESS_SKILLS_DIR"] = str(home / "skills")
os.environ["OM_HARNESS_PLUGINS_DIR"] = str(home / "plugins")

repo = tmp / "repo"
repo.mkdir()
subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
(repo / "x.py").write_text("x = 1\n")

from om_harness.config.loader import ApprovalPolicy  # noqa: E402
from om_harness.harness import Harness  # noqa: E402
from om_harness.tools.base import Permission  # noqa: E402
from om_harness.ui.repl import ChatRepl  # noqa: E402

harness = Harness(repo_root=repo, env={})
session = harness.sessions.create(repo_root=str(repo))
repl = ChatRepl(harness, session_id=session.session_id)

# Feed the interactive loop; run_turn is the REAL one (mock model echoes).
# (No "/exit" line: the empty queue raises EOFError from prompt() instead.)
sent_lines = ["/plan", "read x.py and propose a change", "approve"]


class _FakeSession:
    def prompt(self, *a, **k):
        if not sent_lines:
            raise EOFError
        return sent_lines.pop(0)


repl._make_prompt_session = lambda: _FakeSession()  # type: ignore[method-assign]

original_policy = harness.config.approval.policy
assert original_policy != ApprovalPolicy.deny

failures: list[str] = []
turns_seen: list[str] = []


class _TurnWatcher(ChatRepl):
    pass


real_run_turn = repl.run_turn


def watched_run_turn(text: str) -> None:
    turns_seen.append(text)
    # Inside a plan-mode turn: engine must deny mutating, allow read-only.
    if repl.plan_mode:
        denied = harness.approval.evaluate("write_file", Permission.mutating)
        allowed = harness.approval.evaluate("read_file", Permission.read_only)
        if denied.value != "denied" or allowed.value != "approved":
            failures.append(f"gating wrong during turn: {denied=} {allowed=}")
    real_run_turn(text)


repl.run_turn = watched_run_turn  # type: ignore[method-assign]

# Snapshot of what a plan-mode system prompt contains, before the loop runs.

repl._slash_command("/plan")
prompt = harness.assembler.system_prompt("implementer")
assert "Mode: plan" in prompt and "Do not modify files" in prompt, prompt
assert "⏸ plan" in repl._status_bar(), repl._status_bar()
assert repl._slash_command("/mode") and harness.config.approval.policy == ApprovalPolicy.deny
repl._slash_command("/plan off")  # reset: the loop itself will re-enter plan mode

repl.run_forever()

print("--- smoke results ---")
print("turns sent to agent:", turns_seen)
print("plan_mode after loop:", repl.plan_mode)
print("policy after loop:", harness.config.approval.policy, "| original:", original_policy)
print("prompt glyph during plan mode: OK")
print("approval engine gating inside plan turn:", failures or "OK")

messages = harness.store.load_session(session.session_id).messages
print("recorded message roles:", [m.role.value for m in messages])

# The implementation turn (second user message) should contain the plan context
# Note: mock:echo model echoes the user's message, so the "plan" in session is
# the user's original question - that's fine, the prepend logic still works.
impl_turn = None
for m in messages:
    if m.role.value == "user" and "Plan from previous turn" in m.content:
        impl_turn = m
        break

ok = (
    turns_seen[0] == "read x.py and propose a change"
    and turns_seen[1].startswith("Plan from previous turn:")
    and "User approval: approve" in turns_seen[1]
    and repl.plan_mode is False
    and harness.config.approval.policy == original_policy
    and not failures
    and len(messages) >= 4
    and impl_turn is not None
)
print("SMOKE:", "PASS" if ok else "FAIL")
if not ok:
    print("Missing plan context in implementation turn!")
sys.exit(0 if ok else 1)
