"""Systemic Drift Detection Engine.

Flags chronic, repeating root-cause categories as systemic engineering defects
rather than isolated firefights, automatically generating architectural backlog items.
"""

from __future__ import annotations

from collections import defaultdict
import uuid
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, SystemicDriftReport


class DriftDetectionEngine:
    """Analyzes cross-incident historical memory to detect recurring systemic failure modes."""

    def __init__(self, db: DatabaseManager | None = None, recurrence_threshold: int = 2):
        self.db = db or DatabaseManager()
        self.recurrence_threshold = recurrence_threshold

    def analyze_drift(self, incidents: list[Incident] | None = None) -> list[SystemicDriftReport]:
        """Scan historical incidents for repeating root causes on the same service."""
        if incidents is None:
            incidents = self.db.list_incidents(limit=200)

        # Group by (service, root_cause_category)
        groups: dict[tuple[str, str], list[Incident]] = defaultdict(list)
        for inc in incidents:
            if inc.root_cause_category and inc.root_cause_category != "Unknown":
                groups[(inc.service, inc.root_cause_category)].append(inc)

        reports: list[SystemicDriftReport] = []

        for (service, root_cause), inc_list in groups.items():
            count = len(inc_list)
            if count >= self.recurrence_threshold:
                timeline = [inc.started_at.strftime("%Y-%m-%d %H:%M") for inc in sorted(inc_list, key=lambda x: x.started_at)]

                # Generate architectural backlog item recommendation
                summary = (
                    f"Systemic recurrence detected on '{service}': '{root_cause}' "
                    f"has occurred {count} times across the fleet."
                )
                recommendation = (
                    f"ARCHITECTURAL DEFECT TICKET: Stop firefighting '{root_cause}' manually on service '{service}'. "
                    f"Action items: 1) Refactor baseline resource requests & limits; "
                    f"2) Implement automated circuit breaker / connection backoff; "
                    f"3) Add end-to-end integration test reproducing peak load conditions."
                )

                severity = "P1" if count >= 3 else "P2"
                report = SystemicDriftReport(
                    id=str(uuid.uuid4())[:8],
                    service=service,
                    root_cause_category=root_cause,
                    incident_count=count,
                    timeline_dates=timeline,
                    drift_summary=summary,
                    backlog_recommendation=recommendation,
                    severity=severity,
                )
                self.db.save_drift_report(report)
                reports.append(report)

        return reports
