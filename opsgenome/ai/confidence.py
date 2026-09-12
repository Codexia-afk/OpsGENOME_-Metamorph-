"""Earned Confidence Score & Provenance Trail Engine.

Calculates defensible confidence scores from real historical resolution outcomes
rather than asserting arbitrary percentages, and enforces cold-start honesty.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from opsgenome.storage.models import ConfidenceLevel, KnowledgeStatus, ProvenanceRecord


class ConfidenceEngine:
    """Calculates earned confidence scores and provenance trails."""

    COLD_START_MIN_SAMPLES = 3

    @classmethod
    def calculate_confidence(
        cls,
        total_incidents: int,
        successful_resolutions: int,
        escalations: int = 0,
        verification_checks_passed: int = 1,
        first_seen_at: datetime | None = None,
        last_verified_at: datetime | None = None,
        engineers: list[str] | None = None,
    ) -> tuple[float, ConfidenceLevel, ProvenanceRecord]:
        """Calculate earned confidence score and provenance record.

        Returns:
            (earned_score, confidence_level, provenance_record)
        """
        now = datetime.now(timezone.utc)
        first_seen = first_seen_at or now
        last_verified = last_verified_at or now
        eng_list = engineers or ["local_engineer"]

        if total_incidents <= 0:
            prov = ProvenanceRecord(
                total_incidents_recorded=0,
                successful_resolutions=0,
                historical_success_rate=0.0,
                current_evidence_confidence=0.0,
                escalations_required=0,
                verification_rate=0.0,
                first_seen_at=first_seen,
                last_verified_at=last_verified,
                contributing_engineers=eng_list,
                provenance_trail_text="Cold start: No historical incidents recorded yet.",
            )
            return 0.0, ConfidenceLevel.COLD_START, prov

        # 1. Historical Success Rate: How often did this action work in the past?
        historical_success_rate = round(successful_resolutions / total_incidents, 3)

        # 2. Escalation penalty (reduces confidence if human intervention/escalation was needed)
        escalation_penalty = (escalations / total_incidents) * 0.25

        # 3. Verification check boost (rewards deterministic state-transition checks)
        verification_rate = min(1.0, verification_checks_passed / max(1, total_incidents))
        verification_boost = verification_rate * 0.10

        # 4. Sample Size Damping Factor: W = 1 - exp(-N / 4.0)
        # Prevents premature overconfidence on small samples.
        # N=1 -> W=0.22, N=3 -> W=0.53, N=5 -> W=0.71, N=8 -> W=0.86, N=12 -> W=0.95
        sample_damping = 1.0 - math.exp(-total_incidents / 4.0)

        # 5. Current Evidence Confidence: How strongly does today's evidence support this action?
        raw_score = (historical_success_rate - escalation_penalty + verification_boost) * sample_damping
        current_evidence_confidence = round(max(0.0, min(1.0, raw_score)), 2)
        earned_score = current_evidence_confidence

        # 6. Determine Confidence Level (Enforcing Cold-Start Honesty)
        if total_incidents < cls.COLD_START_MIN_SAMPLES:
            level = ConfidenceLevel.COLD_START
            trail_text = (
                f"Cold Start ({total_incidents}/{cls.COLD_START_MIN_SAMPLES} incidents recorded): "
                f"{successful_resolutions} resolved ({int(historical_success_rate * 100)}% historical success), "
                f"{escalations} escalations. Confidence is withheld until sufficient sample size is reached."
            )
        else:
            if earned_score >= 0.80:
                level = ConfidenceLevel.HIGH
            elif earned_score >= 0.55:
                level = ConfidenceLevel.MODERATE
            else:
                level = ConfidenceLevel.LOW

            eng_count = len(set(eng_list))
            trail_text = (
                f"Based on {total_incidents} recorded incidents: {successful_resolutions} resolved ({int(historical_success_rate * 100)}% historical success). "
                f"Current Evidence Confidence: {int(current_evidence_confidence * 100)}% (Sample Damping: {round(sample_damping, 2)}). "
                f"{escalations} required escalation across {eng_count} engineer(s)."
            )

        prov = ProvenanceRecord(
            total_incidents_recorded=total_incidents,
            successful_resolutions=successful_resolutions,
            historical_success_rate=historical_success_rate,
            current_evidence_confidence=current_evidence_confidence,
            escalations_required=escalations,
            verification_rate=round(verification_rate, 2),
            first_seen_at=first_seen,
            last_verified_at=last_verified,
            contributing_engineers=list(set(eng_list)),
            provenance_trail_text=trail_text,
        )

        return earned_score, level, prov
    @classmethod
    def calculate_knowledge_status(
        cls,
        total_incidents: int,
        successful_resolutions: int,
        escalations: int = 0,
        last_matched_at: datetime | None = None,
        last_execution_healthy: bool | None = None,
    ) -> KnowledgeStatus:
        """Determines whether runbook knowledge is VERIFIED, AGING, STALE, or CONTRADICTED."""
        # Immediate contradiction if historical remedy was executed but service health verification failed
        if last_execution_healthy is False:
            return KnowledgeStatus.CONTRADICTED

        if escalations > 0 and (successful_resolutions == 0 or escalations >= successful_resolutions):
            return KnowledgeStatus.CONTRADICTED

        now = datetime.now(timezone.utc)
        if last_matched_at:
            if last_matched_at.tzinfo is None:
                last_matched_at = last_matched_at.replace(tzinfo=timezone.utc)
            age_days = (now - last_matched_at).total_seconds() / 86400.0
            if age_days > 90.0:
                return KnowledgeStatus.STALE
            elif age_days > 30.0:
                return KnowledgeStatus.AGING

        return KnowledgeStatus.VERIFIED
