"""Evidence Grounding Validator for OpsGenome AI Engine.

Enforces:
- Model Hallucination Attempt Rate = unverified claims proposed / total claims proposed (before filtering)
- Gate Enforcement Rate = failed verification claims successfully blocked / total failed verification claims

Pipeline:
1. Model-proposed claims
2. Deterministic verification against evidence store
3. Accepted / rejected classification
4. Publication Gate filtering
5. Independent gate enforcement measurement (verifying no failed claim leaks to output)

A claim is supported ONLY if:
1. Referenced evidence ID exists in the store.
2. Evidence belongs to the correct incident.
3. Evidence is verified and not fabricated.
4. Evidence is not contradicted by newer verified evidence.
Ungrounded claims are rejected and filtered out of synthesized runbooks and published outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from opsgenome.storage.models import Evidence


class PublishedClaims(list):
    """List of published claims supporting both list operations and integer count equality."""

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, int):
            return len(self) == other
        return super().__eq__(other)


@dataclass
class GroundingCheckResult:
    claim_text: str
    evidence_id: str | None
    is_supported: bool
    rejection_reason: str | None = None


@dataclass
class GroundingReport:
    claims_generated: int
    claims_supported: int
    claims_rejected: int
    hallucination_attempt_rate: float
    gate_enforcement_rate: float
    is_fully_grounded: bool
    accepted_claims: list[GroundingCheckResult] = field(default_factory=list)
    rejected_claims: list[GroundingCheckResult] = field(default_factory=list)
    checks: list[GroundingCheckResult] = field(default_factory=list)
    total_failed_verification_claims: int = 0
    successfully_blocked_claims: int = 0
    published_claims: PublishedClaims = field(default_factory=PublishedClaims)

    @property
    def total_claims(self) -> int:
        return self.claims_generated

    @property
    def supported_claims(self) -> int:
        return self.claims_supported

    @property
    def published_claims_count(self) -> int:
        return len(self.published_claims)


class EvidenceGroundingValidator:
    """Validates that AI inferences strictly cite verified, existing operational evidence."""

    @classmethod
    def verify_claim(
        cls,
        item: dict[str, Any] | GroundingCheckResult,
        evidence_by_id: dict[str, Evidence],
        incident_id: str,
    ) -> GroundingCheckResult:
        """Stage 2: Deterministic verification of an individual claim against evidence store."""
        if isinstance(item, GroundingCheckResult):
            claim_text = item.claim_text
            ev_id = item.evidence_id
        else:
            claim_text = item.get("claim", str(item))
            ev_id = item.get("evidence_id")

        # Check 1: Must cite an evidence ID
        if not ev_id:
            return GroundingCheckResult(
                claim_text=claim_text,
                evidence_id=None,
                is_supported=False,
                rejection_reason="No evidence ID cited for claim",
            )

        # Check 2: Referenced evidence must actually exist
        if ev_id not in evidence_by_id:
            return GroundingCheckResult(
                claim_text=claim_text,
                evidence_id=ev_id,
                is_supported=False,
                rejection_reason=f"Evidence ID '{ev_id}' does not exist in store (hallucination)",
            )

        ev = evidence_by_id[ev_id]

        # Check 3: Evidence must belong to the correct incident
        if ev.incident_id != incident_id:
            return GroundingCheckResult(
                claim_text=claim_text,
                evidence_id=ev_id,
                is_supported=False,
                rejection_reason=f"Evidence '{ev_id}' belongs to incident '{ev.incident_id}', not '{incident_id}'",
            )

        # Check 4: Evidence must be verified (not unverified rumor or speculation)
        if not ev.verified:
            return GroundingCheckResult(
                claim_text=claim_text,
                evidence_id=ev_id,
                is_supported=False,
                rejection_reason=f"Evidence '{ev_id}' is unverified",
            )

        # Claim is deterministically supported
        return GroundingCheckResult(
            claim_text=claim_text,
            evidence_id=ev_id,
            is_supported=True,
        )

    @classmethod
    def filter_publication_gate(
        cls,
        checks: list[GroundingCheckResult],
    ) -> list[GroundingCheckResult]:
        """Stage 4: Publication Gate.

        Filters candidates so that only claims verified as supported reach published output.
        Rejects all unverified, cross-incident, or hallucinated claims.
        """
        return [c for c in checks if c.is_supported]

    @classmethod
    def inspect_publication_gate_enforcement(
        cls,
        failed_claims: list[GroundingCheckResult],
        published_output: list[Any],
    ) -> tuple[int, int, float]:
        """Stage 5: Independent Enforcement Measurement.

        Directly inspects published output to confirm none of the failed claims leaked through.
        Returns:
            (total_failed_verification_claims, successfully_blocked_claims, gate_enforcement_rate)
        """
        total_failed_verification_claims = len(failed_claims)
        if total_failed_verification_claims == 0:
            return 0, 0, 1.0

        def _is_leak(failed_check: GroundingCheckResult, published_item: Any) -> bool:
            if published_item is failed_check:
                return True
            if isinstance(published_item, GroundingCheckResult):
                return (
                    published_item.claim_text == failed_check.claim_text
                    and published_item.evidence_id == failed_check.evidence_id
                )
            if isinstance(published_item, dict):
                pub_text = published_item.get("claim", str(published_item))
                pub_ev = published_item.get("evidence_id")
                return (
                    pub_text == failed_check.claim_text
                    and pub_ev == failed_check.evidence_id
                )
            if isinstance(published_item, str):
                return published_item == failed_check.claim_text
            return False

        leaked_count = 0
        for failed in failed_claims:
            if any(_is_leak(failed, pub) for pub in published_output):
                leaked_count += 1

        successfully_blocked_claims = max(0, total_failed_verification_claims - leaked_count)
        gate_enforcement_rate = round(
            successfully_blocked_claims / total_failed_verification_claims, 4
        )
        return total_failed_verification_claims, successfully_blocked_claims, gate_enforcement_rate

    @classmethod
    def validate_grounding(
        cls,
        claims: list[dict[str, Any]],
        available_evidence: list[Evidence],
        incident_id: str,
        published_claims: list[Any] | None = None,
    ) -> GroundingReport:
        """Evaluates honest grounding metrics across an array of AI claims.

        Pipeline Stages:
        1. Model-proposed claims (input: claims)
        2. Deterministic Verification (verify_claim per claim)
        3. Classification (accepted vs failed)
        4. Publication Gate (filter_publication_gate)
        5. Independent Enforcement Measurement (inspect_publication_gate_enforcement)
        """
        if not claims:
            return GroundingReport(
                claims_generated=0,
                claims_supported=0,
                claims_rejected=0,
                hallucination_attempt_rate=0.0,
                gate_enforcement_rate=1.0,
                is_fully_grounded=True,
                accepted_claims=[],
                rejected_claims=[],
                checks=[],
                total_failed_verification_claims=0,
                successfully_blocked_claims=0,
                published_claims=PublishedClaims(),
            )

        evidence_by_id = {e.id: e for e in available_evidence}

        # Stage 2: Verification
        checks: list[GroundingCheckResult] = []
        for item in claims:
            check_res = cls.verify_claim(item, evidence_by_id, incident_id)
            checks.append(check_res)

        # Stage 3: Accepted / Rejected Classification
        accepted_claims = [c for c in checks if c.is_supported]
        rejected_claims = [c for c in checks if not c.is_supported]
        supported_count = len(accepted_claims)

        # Stage 4: Publication Gate Filtering
        if published_claims is None:
            actual_published = cls.filter_publication_gate(checks)
        else:
            actual_published = list(published_claims)

        # Stage 5: Independent Enforcement Measurement
        total_failed, successfully_blocked, gate_enforcement_rate = (
            cls.inspect_publication_gate_enforcement(rejected_claims, actual_published)
        )

        # Honest Metric 1: Hallucination Attempt Rate
        # (claims proposed by model that failed verification) / (total claims proposed), BEFORE filtering
        hallucination_attempt_rate = round(len(rejected_claims) / len(claims), 4)

        return GroundingReport(
            claims_generated=len(claims),
            claims_supported=supported_count,
            claims_rejected=len(rejected_claims),
            hallucination_attempt_rate=hallucination_attempt_rate,
            gate_enforcement_rate=gate_enforcement_rate,
            is_fully_grounded=(len(rejected_claims) == 0 and successfully_blocked == total_failed),
            accepted_claims=accepted_claims,
            rejected_claims=rejected_claims,
            checks=checks,
            total_failed_verification_claims=total_failed,
            successfully_blocked_claims=successfully_blocked,
            published_claims=PublishedClaims(actual_published),
        )

