"""Approval policy engine: decides whether a tool may run.

Policies (see ``config.loader.ApprovalPolicy``):
- ``auto``: mutating tools run freely, destructive tools need confirmation
- ``ask``: mutating and destructive tools need confirmation
- ``allowlist``: only explicitly listed tools run without confirmation
- ``deny``: nothing mutating/destructive ever runs

Read-only tools are always allowed under every policy. In non-interactive
contexts (CI, ``run --json``), requests for confirmation resolve to *denied* —
fail safe, never auto-approve.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum

from om_harness.config.loader import ApprovalConfig
from om_harness.config.loader import ApprovalPolicy as Policy
from om_harness.tools.base import Permission

Confirmer = Callable[[str, str], Awaitable[bool]]


class ApprovalDecision(StrEnum):
    approved = "approved"
    denied = "denied"
    needs_approval = "needs_approval"


class ApprovalEngine:
    def __init__(
        self,
        config: ApprovalConfig,
        *,
        interactive: bool = False,
        confirmer: Confirmer | None = None,
    ) -> None:
        self.config = config
        self.interactive = interactive
        self.confirmer = confirmer

    def evaluate(self, tool_name: str, permission: Permission) -> ApprovalDecision:
        if permission == Permission.read_only:
            return ApprovalDecision.approved
        policy = self.config.policy
        if policy == Policy.deny:
            return ApprovalDecision.denied
        if policy == Policy.allowlist:
            if tool_name in self.config.allowlist:
                return ApprovalDecision.approved
            # Policy-pure: interactivity is resolved in request().
            return ApprovalDecision.needs_approval
        if policy == Policy.auto:
            if permission == Permission.mutating:
                return ApprovalDecision.approved
            return ApprovalDecision.needs_approval
        # Policy.ask
        return ApprovalDecision.needs_approval

    async def request(self, tool_name: str, permission: Permission) -> bool:
        """Final verdict: may the tool execute?"""
        decision = self.evaluate(tool_name, permission)
        if decision == ApprovalDecision.approved:
            return True
        if decision == ApprovalDecision.denied:
            return False
        # needs_approval
        if self.interactive and self.confirmer is not None:
            reason = (
                f"Tool {tool_name!r} requires approval "
                f"(permission level: {permission.value}, policy: {self.config.policy.value})."
            )
            return await self.confirmer(tool_name, reason)
        return False
