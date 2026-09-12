"""Shadow Mode Incident Co-Pilot.

Watches live incident command execution in real-time, matching against historical
intelligence graphs to suggest optimal next actions and warn against known dead-ends.
"""

from __future__ import annotations

from typing import Any
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import CapturedEvent, Incident, Runbook


class ShadowCopilot:
    """Provides real-time predictive guidance and dead-end warnings during active firefighting."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        recurrence_engine: RecurrenceAlertEngine | None = None,
    ):
        self.db = db or DatabaseManager()
        self.recurrence_engine = recurrence_engine or RecurrenceAlertEngine(self.db)

    def evaluate_live_state(
        self, active_incident: Incident, recent_events: list[CapturedEvent]
    ) -> dict[str, Any]:
        """Evaluate the active incident and return real-time suggestions and warnings."""
        match_info = self.recurrence_engine.check_recurrence(active_incident)

        suggestions: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        if match_info and match_info.get("matched"):
            runbook_id = match_info["matched_runbook_id"]
            runbook = self.db.get_runbook(runbook_id)

            if runbook:
                # Check executed commands against runbook steps
                executed_cmds = {ev.command_redacted.strip() for ev in recent_events}

                # Next recommended step
                for step in runbook.steps:
                    if step.command.strip() not in executed_cmds:
                        suggestions.append({
                            "title": step.title,
                            "command": step.command,
                            "expected_output": step.expected_output,
                            "reasoning": (
                                f"Historical Runbook Match ({int(match_info['similarity_score'] * 100)}% similarity). "
                                f"In {runbook.provenance.total_incidents_recorded} past incidents, this step resolved {runbook.root_cause_category}."
                            ),
                            "confidence": match_info["confidence_score"],
                        })
                        break

                # Check if engineer attempted or is investigating a known dead end
                for dead_end in runbook.negative_knowledge_dead_ends:
                    warnings.append({
                        "avoid_command": dead_end.command,
                        "why_avoid": dead_end.why_it_failed,
                        "recommendation": dead_end.recommendation,
                    })

        return {
            "incident_id": active_incident.id,
            "has_historical_match": bool(match_info and match_info.get("matched")),
            "similarity_score": match_info["similarity_score"] if match_info else 0.0,
            "root_cause_prediction": match_info["root_cause_category"] if match_info else "Diagnosing...",
            "suggested_next_steps": suggestions,
            "dead_end_warnings": warnings,
        }
