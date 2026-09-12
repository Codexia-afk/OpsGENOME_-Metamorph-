"""Permission Gate and Trust Asymmetry Enforcement Engine for Suggested Fixes.

CORE DESIGN INVARIANT:
1. Same-project matches follow standard single-confirmation or auto-approve flows.
2. Cross-project matches are strictly lower trust:
   - NEVER allowed to auto-apply under ANY configuration flag (including auto_approve or yolo).
   - Require an additional explicit dual-confirmation step naming the source project.
   - Refuse execution if acknowledgment is missing or does not name the foreign source project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class PermissionGateError(Exception):
    """Base exception for permission gate violations."""
    pass


class CrossProjectAutoApproveForbiddenError(PermissionGateError):
    """Raised when an auto-approve flag attempts to bypass cross-project confirmation."""
    pass


class CrossProjectAcknowledgmentRequiredError(PermissionGateError):
    """Raised when a cross-project fix lacks the explicit secondary acknowledgment."""
    pass


@dataclass
class FixExecutionRequest:
    runbook_id: str
    target_incident_id: str
    target_project: str
    source_project: str
    command: str
    same_project: bool
    confirmed: bool = False
    cross_project_ack: str | None = None
    auto_approve: bool = False


@dataclass
class FixExecutionResult:
    status: str  # "executed" | "refused" | "blocked"
    command: str
    same_project: bool
    source_project: str
    target_project: str
    executed: bool
    message: str


class FixApplicationGate:
    """Enforces strict trust asymmetry between same-project and cross-project fixes."""

    @classmethod
    def authorize_and_apply(
        cls,
        request: FixExecutionRequest,
        runner_fn: Callable[[str], Any] | None = None,
    ) -> FixExecutionResult:
        """Evaluate fix request against trust invariants and execute only if authorized."""
        # Tier 1: Same-Project Match
        if request.same_project:
            if request.auto_approve or request.confirmed:
                output = runner_fn(request.command) if runner_fn else None
                return FixExecutionResult(
                    status="executed",
                    command=request.command,
                    same_project=True,
                    source_project=request.source_project,
                    target_project=request.target_project,
                    executed=True,
                    message=f"Same-project fix executed successfully for project '{request.target_project}'.",
                )
            return FixExecutionResult(
                status="refused",
                command=request.command,
                same_project=True,
                source_project=request.source_project,
                target_project=request.target_project,
                executed=False,
                message="Same-project fix application cancelled by user.",
            )

        # Tier 2: Cross-Project Match (Strict Lower-Trust Asymmetry)

        # Invariant 1: Under NO flag may cross-project fixes be auto-applied
        if request.auto_approve:
            raise CrossProjectAutoApproveForbiddenError(
                f"Cross-project fix from foreign project '{request.source_project}' cannot be auto-applied "
                f"under any configuration flag. Explicit interactive confirmation is mandatory."
            )

        # Invariant 2: Primary confirmation is required
        if not request.confirmed:
            return FixExecutionResult(
                status="refused",
                command=request.command,
                same_project=False,
                source_project=request.source_project,
                target_project=request.target_project,
                executed=False,
                message="Cross-project fix application declined at primary confirmation.",
            )

        # Invariant 3: Dual-confirmation explicitly naming the source project is mandatory
        expected_ack = f"CONFIRM FROM {request.source_project}".strip().upper()
        actual_ack = (request.cross_project_ack or "").strip().upper()

        if actual_ack != expected_ack:
            raise CrossProjectAcknowledgmentRequiredError(
                f"Cross-project fix execution REFUSED: Requires explicit acknowledgment typing "
                f"'{expected_ack}'. Received: '{request.cross_project_ack}'. "
                f"Fix has not been validated in this project's context."
            )

        # Authorized cross-project execution
        output = runner_fn(request.command) if runner_fn else None
        return FixExecutionResult(
            status="executed",
            command=request.command,
            same_project=False,
            source_project=request.source_project,
            target_project=request.target_project,
            executed=True,
            message=(
                f"Cross-project fix from '{request.source_project}' authorized with explicit "
                f"dual-confirmation and executed in '{request.target_project}'."
            ),
        )
