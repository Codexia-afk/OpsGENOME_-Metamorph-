"""SRE Replay Flight Simulator.

Allows new on-call engineers to step through past production incidents command-by-command,
observing the engineer's hypothesis, evidence, state changes, and negative dead-ends.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import CapturedEvent, CausalStatus, Incident


class SimulationStep(BaseModel):
    step_index: int
    total_steps: int
    timestamp_offset_sec: int
    phase: str  # INTAKE, DIAGNOSIS, ATTEMPTED_FIX, RECOVERY, VERIFICATION
    command: str
    exit_code: int
    tool_category: str
    stdout: str
    stderr: str
    state_delta: str
    is_healthy_now: bool
    expert_annotation: str
    causal_status: str
    quiz_question: str | None = None
    quiz_options: list[str] = Field(default_factory=list)
    quiz_correct_index: int | None = None


class FlightSimulatorEngine:
    """Manages SRE interactive replay simulations for on-call onboarding."""

    def __init__(self, db: DatabaseManager | None = None):
        self.db = db or DatabaseManager()

    def build_simulation(self, incident_id: str) -> dict[str, Any] | None:
        """Construct full step-by-step flight simulator scenario from an incident."""
        incident = self.db.get_incident(incident_id)
        if not incident:
            return None

        events = self.db.get_events_for_incident(incident_id)
        if not events:
            return None

        steps: list[SimulationStep] = []
        total_steps = len(events)
        start_time = events[0].timestamp

        for idx, ev in enumerate(events):
            offset = int((ev.timestamp - start_time).total_seconds())

            # Determine phase
            if idx == 0:
                phase = "INTAKE"
            elif ev.status == CausalStatus.DEAD_END or ev.exit_code != 0:
                phase = "ATTEMPTED_FIX (DEAD END)"
            elif ev.status == CausalStatus.VERIFIED_FIX:
                phase = "REMEDIAL FIX"
            elif idx >= total_steps - 2:
                phase = "VERIFICATION"
            else:
                phase = "DIAGNOSIS"

            # Expert annotation
            annotation = self._generate_annotation(ev, incident, idx, total_steps)

            # Quiz checkpoint on critical steps
            quiz_q, quiz_opts, quiz_ans = self._generate_quiz(ev, idx, total_steps)

            steps.append(
                SimulationStep(
                    step_index=idx + 1,
                    total_steps=total_steps,
                    timestamp_offset_sec=offset,
                    phase=phase,
                    command=ev.command_redacted,
                    exit_code=ev.exit_code,
                    tool_category=ev.tool_category,
                    stdout=ev.stdout_summary or "(no stdout)",
                    stderr=ev.stderr_summary or "",
                    state_delta=ev.state_delta_summary or "No state change observed",
                    is_healthy_now=bool(ev.after_snapshot and ev.after_snapshot.is_healthy),
                    expert_annotation=annotation,
                    causal_status=ev.status.value,
                    quiz_question=quiz_q,
                    quiz_options=quiz_opts,
                    quiz_correct_index=quiz_ans,
                )
            )

        return {
            "incident_id": incident.id,
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "root_cause_category": incident.root_cause_category,
            "resolved_by": incident.resolved_by,
            "total_steps": total_steps,
            "steps": [s.model_dump() for s in steps],
        }

    def _generate_annotation(
        self, ev: CapturedEvent, incident: Incident, idx: int, total: int
    ) -> str:
        cmd = ev.command_redacted
        if ev.status == CausalStatus.DEAD_END or ev.exit_code != 0:
            return (
                f"DEAD-END BRANCH: The on-call engineer attempted `{cmd}`, but it failed with exit code {ev.exit_code}. "
                "Notice how this ruled out this vector and directed investigation to the true root cause."
            )
        elif ev.status == CausalStatus.VERIFIED_FIX:
            return (
                f"THE FIX: Executing `{cmd}` directly resolved the failure state. "
                f"Delta observed: {ev.state_delta_summary or 'Service restored to healthy state.'}"
            )
        elif "logs" in cmd or "describe" in cmd:
            return f"EVIDENCE GATHERING: Inspecting logs/manifests with `{cmd}` to isolate error signatures."
        elif idx == total - 1:
            return f"VERIFICATION: Final health check `{cmd}` confirmed 200 OK across all pods."
        else:
            return f"INVESTIGATION: Checking resource status with `{cmd}`."

    def _generate_quiz(
        self, ev: CapturedEvent, idx: int, total: int
    ) -> tuple[str | None, list[str], int | None]:
        if ev.status == CausalStatus.VERIFIED_FIX:
            return (
                "Checkpoint: What is the most critical next step after applying this fix?",
                [
                    "Immediately close the incident channel without checking pod status",
                    "Run verification queries against health endpoints and monitor error rate for 5 minutes",
                    "Restart all database nodes just in case",
                    "Reboot the entire Kubernetes control plane",
                ],
                1,
            )
        elif idx == 0:
            return (
                "Initial Response: What should you check first when this alert fires?",
                [
                    "Delete the deployment immediately",
                    "Inspect recent pod status, logs, and upstream latency metrics",
                    "Page the CTO directly",
                    "Assume it's a false positive and snooze alert for 2 hours",
                ],
                1,
            )
        return None, [], None
