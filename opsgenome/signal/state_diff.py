"""Resource State Snapshot & Delta Analyzer.

Captures system/resource health snapshots before and after remediation commands,
and correlates command executions with observed state changes (e.g. CrashLoopBackOff -> Running).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from opsgenome.storage.models import StateSnapshot


class StateSnapshotEngine:
    """Collects and compares infrastructure state snapshots."""

    @staticmethod
    def create_snapshot(
        incident_id: str,
        resource_type: str = "k8s_pods",
        raw_state: dict[str, Any] | None = None,
        status_summary: str = "",
        is_healthy: bool = True,
    ) -> StateSnapshot:
        """Create a state snapshot model."""
        return StateSnapshot(
            incident_id=incident_id,
            timestamp=datetime.now(timezone.utc),
            resource_type=resource_type,
            raw_state=raw_state or {},
            status_summary=status_summary,
            is_healthy=is_healthy,
        )


def compute_state_delta(
    before: StateSnapshot | None,
    after: StateSnapshot | None,
) -> tuple[str, bool]:
    """Compute difference between before and after snapshots.

    Returns:
        (delta_summary_string, is_meaningful_improvement)
    """
    if before is None or after is None:
        return "", False

    # Check health transition
    if not before.is_healthy and after.is_healthy:
        summary = f"RECOVERY: State improved from unhealthy [{before.status_summary}] to healthy [{after.status_summary}]"
        return summary, True

    if before.is_healthy and not after.is_healthy:
        summary = f"DEGRADATION: State degraded from healthy [{before.status_summary}] to unhealthy [{after.status_summary}]"
        return summary, False

    # Status summary changes
    if before.status_summary != after.status_summary:
        summary = f"STATE_CHANGE: [{before.status_summary}] -> [{after.status_summary}]"
        return summary, False

    # Raw state diffs
    if before.raw_state != after.raw_state:
        diff_keys = [k for k in set(before.raw_state.keys()).union(after.raw_state.keys())
                     if before.raw_state.get(k) != after.raw_state.get(k)]
        if diff_keys:
            return f"CONFIG_DELTA on keys: {', '.join(diff_keys[:4])}", False

    return "", False
