"""Command Burst Rate Anomaly Detector.

Monitors terminal command execution velocity. If a sudden spike in infrastructure calls
(kubectl, aws, terraform, docker, systemctl) is detected from a session while no incident
is active, it automatically triggers a candidate capture window with an auto-discard timer.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, IncidentStatus, TriggerType


class CommandBurstAnomalyDetector:
    """Sliding-window burst detector on CLI operations."""

    OPS_COMMAND_REGEX = re.compile(
        r"\b(kubectl|aws|terraform|docker|docker-compose|gcloud|az|systemctl|helm|vault|consul|crictl|nerdctl)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        db: DatabaseManager | None = None,
        burst_threshold: int = 4,  # 4 ops commands within window
        window_seconds: int = 30,
        discard_after_minutes: int = 15,
    ):
        self.db = db or DatabaseManager()
        self.burst_threshold = burst_threshold
        self.window_seconds = window_seconds
        self.discard_after_minutes = discard_after_minutes
        self._command_timestamps: deque[datetime] = deque()

    def record_command(self, command: str) -> Incident | None:
        """Record a command execution and check if a burst anomaly threshold is crossed.

        Returns a newly created candidate Incident if anomaly triggered, else None.
        """
        now = datetime.now(timezone.utc)

        # Check if active incident already exists
        active = self.db.get_active_incident()
        if active:
            return None

        # Check if command is an infrastructure operation
        if not self.OPS_COMMAND_REGEX.search(command):
            return None

        # Add to sliding window
        self._command_timestamps.append(now)

        # Evict timestamps older than window
        cutoff = now - timedelta(seconds=self.window_seconds)
        while self._command_timestamps and self._command_timestamps[0] < cutoff:
            self._command_timestamps.popleft()

        # Check burst threshold
        if len(self._command_timestamps) >= self.burst_threshold:
            # Trigger candidate capture session
            match = self.OPS_COMMAND_REGEX.search(command)
            tool_name = match.group(0).lower() if match else "infra"

            discard_at = now + timedelta(minutes=self.discard_after_minutes)
            candidate_incident = Incident(
                title=f"Auto-Triggered Burst Capture ({tool_name.upper()} Spike)",
                service="inferred-system",
                environment="production",
                severity="P2",
                trigger_type=TriggerType.BURST_ANOMALY,
                status=IncidentStatus.ACTIVE,
                started_at=now,
                symptoms=[f"Command burst detected: >= {self.burst_threshold} ops commands in {self.window_seconds}s"],
                candidate_discard_at=discard_at,
                metadata={"burst_rate": len(self._command_timestamps), "trigger_tool": tool_name},
            )

            self.db.create_incident(candidate_incident)
            # Reset window so we don't duplicate
            self._command_timestamps.clear()
            return candidate_incident

        return None

    def clean_expired_candidates(self) -> list[Incident]:
        """Auto-discard candidate incidents that expired without resolution."""
        now = datetime.now(timezone.utc)
        active_incidents = self.db.list_incidents(status=IncidentStatus.ACTIVE)
        discarded: list[Incident] = []

        for inc in active_incidents:
            if inc.trigger_type == TriggerType.BURST_ANOMALY and inc.candidate_discard_at:
                if inc.candidate_discard_at < now:
                    inc.status = IncidentStatus.DISCARDED
                    inc.summary = "Auto-discarded: Candidate burst session expired with no resolution/fix confirmed."
                    self.db.create_incident(inc)
                    discarded.append(inc)

        return discarded
