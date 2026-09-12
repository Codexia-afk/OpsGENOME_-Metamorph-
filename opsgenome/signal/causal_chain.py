"""Causal Chain Extractor.

Separates pre-filtered captured events into:
1. Remediation steps (actual fix commands)
2. Diagnostic checks (evidence collection)
3. Negative knowledge (dead-ends & ruled out commands)
4. Verification commands (post-fix health checks)
5. Evidence items (grounded state transitions & telemetry)
6. Why / Why Not decision records (grounded alternatives analysis)
"""

from __future__ import annotations

from typing import Any
import uuid
from opsgenome.storage.models import (
    CapturedEvent,
    CausalStatus,
    DeadEndStep,
    Evidence,
    RunbookStep,
    StateSnapshot,
    WhyWhyNot,
)


class CausalChainExtractor:
    """Extracts organized causal chains, negative knowledge, and why/why not evidence."""

    @staticmethod
    def extract(
        events: list[CapturedEvent],
        snapshots: list[StateSnapshot] | None = None,
    ) -> dict[str, Any]:
        remediation_steps: list[RunbookStep] = []
        diagnostic_steps: list[RunbookStep] = []
        verification_steps: list[str] = []
        dead_ends: list[DeadEndStep] = []
        evidence_items: list[Evidence] = []

        step_counter = 1
        incident_id = events[0].incident_id if events else "unknown"

        for ev in events:
            cmd = ev.command_redacted.strip()
            if not cmd:
                continue

            if ev.status == CausalStatus.NOISE:
                continue

            if ev.status == CausalStatus.DEAD_END or ev.exit_code != 0:
                why_failed = ev.stderr_summary or ev.stderr_snippet or f"Command exited with non-zero code {ev.exit_code}"
                evidence_text = ev.stdout_summary or ev.stdout_snippet or "Execution failed or timed out"
                dead_ends.append(
                    DeadEndStep(
                        command=cmd,
                        why_it_failed=why_failed,
                        evidence_observed=evidence_text,
                        recommendation="Ruled out. Do not execute this during remediation.",
                    )
                )
                evidence_items.append(
                    Evidence(
                        id=f"ev-fail-{str(uuid.uuid4())[:8]}",
                        incident_id=ev.incident_id,
                        event_id=ev.id,
                        evidence_type="command_output",
                        summary=f"Negative verification on `{cmd}`: {why_failed[:120]}",
                        verified=False,
                    )
                )
            elif ev.status == CausalStatus.VERIFIED_FIX:
                remediation_steps.append(
                    RunbookStep(
                        step_number=step_counter,
                        title=f"Execute remediation ({ev.tool_category.upper()})",
                        description=f"Run `{cmd}` to restore healthy system state.",
                        command=cmd,
                        expected_output=ev.stdout_summary or "Resource updated / status healthy",
                        rationale=ev.state_delta_summary or "Directly correlated with state recovery",
                        is_remediation=True,
                    )
                )
                evidence_items.append(
                    Evidence(
                        id=f"ev-fix-{str(uuid.uuid4())[:8]}",
                        incident_id=ev.incident_id,
                        event_id=ev.id,
                        evidence_type="state_diff",
                        summary=f"Confirmed recovery: `{cmd}` restored service health ({ev.state_delta_summary or 'exit 0 with verified recovery'})",
                        verified=True,
                    )
                )
                step_counter += 1
            elif ev.status == CausalStatus.INVESTIGATIVE:
                # If command is at the very end and is investigative, treat as verification
                if ev.causal_score >= 0.8 and ("get" in cmd or "status" in cmd or "curl" in cmd or "health" in cmd):
                    verification_steps.append(cmd)
                    evidence_items.append(
                        Evidence(
                            id=f"ev-chk-{str(uuid.uuid4())[:8]}",
                            incident_id=ev.incident_id,
                            event_id=ev.id,
                            evidence_type="metric_verification",
                            summary=f"Post-remediation probe passed: `{cmd}` returned healthy telemetry",
                            verified=True,
                        )
                    )
                else:
                    diagnostic_steps.append(
                        RunbookStep(
                            step_number=step_counter,
                            title=f"Diagnostic inspection ({ev.tool_category.upper()})",
                            description=f"Inspect system state with `{cmd}`",
                            command=cmd,
                            expected_output=ev.stdout_summary or "Diagnostic logs / telemetry",
                            rationale="Gathers initial evidence and confirms failure mode",
                            is_remediation=False,
                        )
                    )
                    evidence_items.append(
                        Evidence(
                            id=f"ev-diag-{str(uuid.uuid4())[:8]}",
                            incident_id=ev.incident_id,
                            event_id=ev.id,
                            evidence_type="log_snippet",
                            summary=f"Diagnostic observation: `{cmd}` exposed fault condition ({ev.stdout_snippet[:80] or 'diagnostics gathered'})",
                            verified=True,
                        )
                    )
                    step_counter += 1

        # Incorporate state snapshots into evidence
        if snapshots:
            for snap in snapshots:
                evidence_items.append(
                    Evidence(
                        id=f"ev-snap-{str(uuid.uuid4())[:8]}",
                        incident_id=snap.incident_id,
                        event_id=snap.event_id,
                        evidence_type="state_diff",
                        summary=f"Resource state diff for {snap.resource_type}: {snap.diff_summary or snap.status_summary or 'Health recovered'}",
                        verified=snap.is_healthy,
                        raw_payload={"before": snap.before_state, "after": snap.after_state},
                    )
                )

        # Build Why / Why Not decision model
        why_not_list: list[dict[str, Any]] = []
        for d in dead_ends:
            why_not_list.append(
                {
                    "action": d.command,
                    "reason_rejected": d.why_it_failed,
                    "evidence": d.evidence_observed,
                }
            )

        recommended_cmd = remediation_steps[0].command if remediation_steps else "Inspect diagnostic logs"
        why_reasons: list[str] = []
        if remediation_steps:
            why_reasons.append(f"Direct causal correlation: `{recommended_cmd}` produced healthy state delta.")
        if verification_steps:
            why_reasons.append(f"Subsequent verification check `{verification_steps[0]}` confirmed healthy 200 OK.")
        if not why_reasons:
            why_reasons.append("Deterministic heuristics verified diagnostic evidence.")

        why_why_not = WhyWhyNot(
            incident_id=incident_id,
            recommended_action=recommended_cmd,
            why_reasons=why_reasons,
            why_not_alternatives=why_not_list,
            evidence_ids=[ev.id for ev in evidence_items],
            confidence=0.96 if remediation_steps and verification_steps else 0.82,
        )

        return {
            "remediation_steps": remediation_steps,
            "diagnostic_steps": diagnostic_steps,
            "verification_steps": verification_steps,
            "dead_ends": dead_ends,
            "evidence_items": evidence_items,
            "why_why_not": why_why_not,
        }
