"""Signal-vs-Noise Heuristic Pre-Filtering Pipeline.

Implements the exact 4-step heuristic:
1. exit_code != 0 within fix-attempt window -> mark as candidate dead_end (preserved as negative knowledge).
2. State snapshot before/after comparison. If no meaningful recovery diff -> weight toward investigation, not fix.
3. Proximity to final successful state check -> commands closer to resolution receive higher signal weight.
4. Threshold gate: only events with signal_weight >= threshold (default 0.6) are passed to LLM chain assembly.
"""

from __future__ import annotations

import math
import re
from opsgenome.signal.state_diff import compute_state_delta
from opsgenome.storage.models import Event, EventClassification, StateSnapshot


class SignalFilter:
    """Calculates signal_weight (0.0 - 1.0) and classification (fix|retry|dead_end|investigation|unknown)."""

    NOISE_PATTERNS = [
        re.compile(r"^\s*(ls(\s+-[a-zA-Z0-9]+|\s+[^\s]+)*|ll|la|dir|pwd|clear|cls|history|whoami|echo\s+.*|cd\s*[\w\.\/~-]*)\s*$", re.IGNORECASE),
        re.compile(r"^\s*$", re.IGNORECASE),
    ]

    MUTATION_PATTERNS = [
        re.compile(r"\b(apply|patch|scale|restart|delete|edit|rollback|undo|cordon|drain|set|exec|run|docker\s+(run|stop|restart|rm)|systemctl\s+(restart|start|stop|reload)|kill|killall|pkill|terraform\s+apply|aws\s+[\w-]+\s+(update|modify|delete|create|put)|helm\s+(upgrade|rollback|install))\b", re.IGNORECASE),
    ]

    INVESTIGATION_PATTERNS = [
        re.compile(r"\b(get|describe|logs|status|top|inspect|diff|cat|grep|tail|head|curl|ping|traceroute|netstat|ss|lsof|dig|nslookup|ps|df|free)\b", re.IGNORECASE),
    ]

    def __init__(self, high_signal_threshold: float = 0.60):
        self.high_signal_threshold = high_signal_threshold

    @classmethod
    def is_noise(cls, command: str) -> bool:
        cmd_strip = command.strip()
        return any(pat.match(cmd_strip) for pat in cls.NOISE_PATTERNS)

    @classmethod
    def is_mutation(cls, command: str) -> bool:
        return any(pat.search(command) for pat in cls.MUTATION_PATTERNS)

    @classmethod
    def is_investigation(cls, command: str) -> bool:
        return any(pat.search(command) for pat in cls.INVESTIGATION_PATTERNS)

    def process_events(
        self,
        events: list[Event],
        snapshots: list[StateSnapshot] | None = None,
    ) -> list[Event]:
        """Calculates signal_weight and classification for each event in the incident."""
        if not events:
            return []

        snap_map: dict[str, StateSnapshot] = {}
        if snapshots:
            for s in snapshots:
                if s.event_id:
                    snap_map[s.event_id] = s

        n = len(events)
        processed: list[Event] = []
        half_life = max(2.0, n / 3.0)

        # Find the last successful mutation command in the session
        last_mutation_idx = -1
        for i, ev in enumerate(events):
            c = (ev.raw_command or ev.command_redacted or "").strip()
            if ev.exit_code == 0 and self.is_mutation(c):
                last_mutation_idx = i

        for idx, ev in enumerate(events):
            cmd = (ev.raw_command or ev.command_redacted or "").strip()
            score = 0.40
            classification = EventClassification.UNKNOWN

            # Check trivial noise
            if self.is_noise(cmd):
                ev.signal_weight = 0.05
                ev.causal_score = 0.05
                ev.classification = EventClassification.UNKNOWN
                ev.status = EventClassification.UNKNOWN
                processed.append(ev)
                continue

            # 1. Exit-Code Weighting: Failed commands are dead-ends
            if ev.exit_code != 0:
                ev.classification = EventClassification.DEAD_END
                ev.status = EventClassification.DEAD_END
                ev.signal_weight = 0.35
                ev.causal_score = 0.35
                processed.append(ev)
                continue

            # 2. State-Delta Correlation
            snap = snap_map.get(ev.id)
            has_recovery = False
            if snap:
                before_snap = StateSnapshot(incident_id=ev.incident_id, raw_state=snap.before_state, is_healthy=False)
                after_snap = StateSnapshot(incident_id=ev.incident_id, raw_state=snap.after_state, is_healthy=snap.is_healthy)
                delta_str, is_rec = compute_state_delta(before_snap, after_snap)
                has_recovery = is_rec or snap.is_healthy
                ev.state_delta_summary = delta_str
            elif ev.before_snapshot and ev.after_snapshot:
                delta_str, is_rec = compute_state_delta(ev.before_snapshot, ev.after_snapshot)
                has_recovery = is_rec
                ev.state_delta_summary = delta_str

            distance_from_end = n - 1 - idx
            recency_weight = math.exp(-distance_from_end / half_life)

            if has_recovery or idx == last_mutation_idx or (self.is_mutation(cmd) and idx >= n - 3):
                classification = EventClassification.FIX
                # Fix score smoothly scales from 0.85 (earlier in fix window) to 0.93 (at final resolution)
                final_weight = round(0.85 + 0.08 * recency_weight, 2)
            elif self.is_investigation(cmd):
                classification = EventClassification.INVESTIGATION
                score = 0.55
                final_weight = round(min(0.80, score * 0.70 + recency_weight * 0.30), 2)
            elif self.is_mutation(cmd):
                classification = EventClassification.RETRY
                score = 0.65
                final_weight = round(min(0.80, score * 0.70 + recency_weight * 0.30), 2)
            else:
                classification = EventClassification.INVESTIGATION
                score = 0.50
                final_weight = round(min(0.75, score * 0.70 + recency_weight * 0.30), 2)

            ev.signal_weight = final_weight
            ev.causal_score = final_weight
            ev.classification = classification
            ev.status = classification
            processed.append(ev)

        return processed

    def get_high_signal_events(self, events: list[Event]) -> list[Event]:
        """Returns only events with signal_weight >= threshold for the LLM pipeline."""
        return [e for e in events if e.signal_weight >= self.high_signal_threshold]
