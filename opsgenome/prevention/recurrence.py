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

    def check_recurrence(
        self,
        new_incident: Incident,
        current_project: str | None = None,
    ) -> dict[str, Any] | None:
        """Scan past runbooks across all projects in the global store for matching patterns.

        Maintains strict trust asymmetry:
        - same_project: True  -> standard recurrence alert with earned confidence.
        - same_project: False -> cross-project advisory explicitly noting foreign project origin.
        """
        active_project = current_project or getattr(new_incident, "project", "default")
        query_text = f"{new_incident.service} {new_incident.title} {' '.join(new_incident.symptoms)}"

        # Inspect if incident or its captured events contain structured parsed_error
        parsed_error = getattr(new_incident, "parsed_error", None)
        if not parsed_error and new_incident.id:
            try:
                inc_events = self.db.get_events_for_incident(new_incident.id)
                parsed_error = next((e.parsed_error for e in inc_events if getattr(e, "parsed_error", None)), None)
            except Exception:
                parsed_error = None

        if parsed_error:
            pe_type = (parsed_error.get("exception_type") or "").strip()
            pe_msg = (parsed_error.get("message") or "").strip()
            pe_lang = (parsed_error.get("language") or "").strip()
            query_text += f" {pe_type} {pe_msg} {pe_lang}"

        query_tokens = self._tokenize(query_text)

        # Query all runbooks across the entire global store
        runbooks = self.db.list_runbooks()
        best_match: Runbook | None = None
        best_similarity = 0.0

        for r in runbooks:
            # Same service match boost
            service_boost = 0.25 if r.service.lower() == new_incident.service.lower() else 0.0
            # Same stack match boost (e.g. shared kubernetes or terraform across projects)
            r_stack = getattr(r, "stack", "general")
            inc_stack = getattr(new_incident, "stack", "general")
            stack_boost = 0.10 if (r_stack != "general" and r_stack.lower() == inc_stack.lower()) else 0.0

            target_text = f"{r.service} {r.title} {r.root_cause_category} {r.symptom_signature}"
            target_tokens = self._tokenize(target_text)

            # Structured parsed_error boost: strong alignment on matching exception type
            pe_boost = 0.0
            if parsed_error and parsed_error.get("exception_type"):
                exc_token = parsed_error["exception_type"].lower()
                if exc_token in target_text.lower():
                    pe_boost = 0.35

            sim = self.calculate_similarity(query_tokens, target_tokens) + service_boost + stack_boost + pe_boost
            if sim > best_similarity:
                best_similarity = sim
                best_match = r

        if best_match and best_similarity >= self.similarity_threshold:
            source_project = getattr(best_match, "project", "default")
            source_stack = getattr(best_match, "stack", "general")
            same_project = (source_project.lower() == active_project.lower())
            rounded_sim = round(min(1.0, best_similarity), 2)

            if same_project:
                trust_tier = "same_project_verified"
                alert_msg = (
                    f"[SAME-PROJECT RECURRENCE MATCH] (Project: {source_project}): OpsGenome detected that incident '{new_incident.title}' "
                    f"matches past root cause '{best_match.root_cause_category}' ({int(best_similarity * 100)}% match). "
                    f"Runbook '{best_match.title}' is available with {int(best_match.earned_confidence_score * 100)}% earned confidence."
                )
                confidence_pres = {
                    "tier": "same_project_verified",
                    "confidence_score": best_match.earned_confidence_score,
                    "is_validated_in_context": True,
                    "label": f"{int(best_match.earned_confidence_score * 100)}% earned confidence",
                }
            else:
                trust_tier = "cross_project_unvalidated"
                alert_msg = (
                    f"[CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT] (Source Project: '{source_project}'): "
                    f"Similar incident pattern found in a different project on this machine (similarity {rounded_sim}). "
                    f"DO NOT apply without independent validation — this fix has not been validated in this project's context "
                    f"('{active_project}'). Dual-confirmation typing 'CONFIRM FROM {source_project}' is strictly required before execution."
                )
                confidence_pres = {
                    "tier": "cross_project_unvalidated",
                    "confidence_score": best_match.earned_confidence_score,
                    "is_validated_in_context": False,
                    "label": f"UNVALIDATED (Cross-project from '{source_project}') — requires manual verification",
                }

            return {
                "matched": True,
                "similarity_score": rounded_sim,
                "project": source_project,
                "source_project": source_project,
                "target_project": active_project,
                "current_project": active_project,
                "stack": source_stack,
                "source_stack": source_stack,
                "same_project": same_project,
                "trust_tier": trust_tier,
                "confidence_presentation": confidence_pres,
                "matched_runbook_id": best_match.id,
                "matched_runbook_title": best_match.title,
                "service": best_match.service,
                "root_cause_category": best_match.root_cause_category,
                "confidence_score": best_match.earned_confidence_score,
                "confidence_level": best_match.confidence_level.value if hasattr(best_match.confidence_level, 'value') else str(best_match.confidence_level),
                "provenance_trail": best_match.provenance.provenance_trail_text if hasattr(best_match, 'provenance') else "",
                "top_commands": [s.command for s in best_match.steps[:3]],
                "negative_knowledge_warnings": [d.command for d in best_match.negative_knowledge_dead_ends],
                "alert_message": alert_msg,
            }

        return None
