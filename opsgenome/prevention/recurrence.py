"""Recurrence Alerting Engine.

Surfaces matching past runbooks at incident intake in < 50ms before the engineer starts digging.
"""

from __future__ import annotations

import re
from typing import Any
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, Runbook


class RecurrenceAlertEngine:
    """Matches active incident symptoms against historical memory to prevent redundant firefighting."""

    def __init__(self, db: DatabaseManager | None = None, similarity_threshold: float = 0.35):
        self.db = db or DatabaseManager()
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        # Split into alphanumeric chunks and words
        words = re.findall(r"[a-zA-Z0-9]+", text.lower())
        # Filter generic stop words
        stops = {"the", "and", "for", "with", "this", "that", "from", "service", "error", "failed", "incident", "across", "near"}
        tokens = {w for w in words if len(w) >= 3 and w not in stops}
        return tokens

    @classmethod
    def calculate_similarity(cls, tokens1: set[str], tokens2: set[str]) -> float:
        """Compute Jaccard similarity between two token sets."""
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        return intersection / union if union > 0 else 0.0

    def check_recurrence(self, new_incident: Incident) -> dict[str, Any] | None:
        """Scan past runbooks and signatures for matching recurrence patterns.

        Returns match details if similarity >= threshold, else None.
        """
        query_text = f"{new_incident.service} {new_incident.title} {' '.join(new_incident.symptoms)}"
        query_tokens = self._tokenize(query_text)

        runbooks = self.db.list_runbooks()
        best_match: Runbook | None = None
        best_similarity = 0.0

        for r in runbooks:
            # Same service match boost
            service_boost = 0.25 if r.service.lower() == new_incident.service.lower() else 0.0
            target_text = f"{r.service} {r.title} {r.root_cause_category} {r.symptom_signature}"
            target_tokens = self._tokenize(target_text)

            sim = self.calculate_similarity(query_tokens, target_tokens) + service_boost
            if sim > best_similarity:
                best_similarity = sim
                best_match = r

        if best_match and best_similarity >= self.similarity_threshold:
            return {
                "matched": True,
                "similarity_score": round(min(1.0, best_similarity), 2),
                "matched_runbook_id": best_match.id,
                "matched_runbook_title": best_match.title,
                "service": best_match.service,
                "root_cause_category": best_match.root_cause_category,
                "confidence_score": best_match.earned_confidence_score,
                "confidence_level": best_match.confidence_level.value,
                "provenance_trail": best_match.provenance.provenance_trail_text,
                "top_commands": [s.command for s in best_match.steps[:3]],
                "negative_knowledge_warnings": [d.command for d in best_match.negative_knowledge_dead_ends],
                "alert_message": (
                    f"RECURRENCE ALERT: OpsGenome detected that incident '{new_incident.title}' "
                    f"matches past root cause '{best_match.root_cause_category}' ({int(best_similarity * 100)}% match). "
                    f"Runbook '{best_match.title}' is available with {int(best_match.earned_confidence_score * 100)}% earned confidence."
                ),
            }

        return None
