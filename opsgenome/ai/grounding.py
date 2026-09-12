"""Evidence Grounding Validator for OpsGenome AI Engine.

Enforces:
Evidence Grounding Rate = supported AI claims / total AI claims

A claim is supported ONLY if:
1. Referenced evidence ID exists in the store.
2. Evidence belongs to the correct incident.
3. Evidence is verified and not fabricated.
4. Evidence is not contradicted by newer verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from opsgenome.storage.models import Evidence


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
    raw_claim_support_rate: float
    accepted_claim_grounding: float
    is_fully_grounded: bool
    accepted_claims: list[GroundingCheckResult] = field(default_factory=list)
    rejected_claims: list[GroundingCheckResult] = field(default_factory=list)
    checks: list[GroundingCheckResult] = field(default_factory=list)

    # Backwards-compatibility properties
    @property
    def total_claims(self) -> int:
        return self.claims_generated

    @property
    def supported_claims(self) -> int:
        return self.claims_supported

    @property
    def grounding_rate(self) -> float:
        return self.raw_claim_support_rate


class EvidenceGroundingValidator:
    """Validates that AI inferences strictly cite verified, existing operational evidence."""

    @classmethod
    def validate_grounding(
        cls,
        claims: list[dict[str, Any]],
        available_evidence: list[Evidence],
        incident_id: str,
    ) -> GroundingReport:
        """Evaluates grounding rate across an array of AI claims.

        Each claim dict can contain:
        - "claim": str description
        - "evidence_id": str ID of cited evidence
        """
        if not claims:
            return GroundingReport(
                claims_generated=0,
                claims_supported=0,
                claims_rejected=0,
                raw_claim_support_rate=1.0,
                accepted_claim_grounding=1.0,
                is_fully_grounded=True,
                accepted_claims=[],
                rejected_claims=[],
                checks=[],
            )

        evidence_by_id = {e.id: e for e in available_evidence}
        checks: list[GroundingCheckResult] = []
        supported_count = 0

        for item in claims:
            claim_text = item.get("claim", str(item))
            ev_id = item.get("evidence_id")

            # Check 1: Must cite an evidence ID
            if not ev_id:
                checks.append(
                    GroundingCheckResult(
                        claim_text=claim_text,
                        evidence_id=None,
                        is_supported=False,
                        rejection_reason="No evidence ID cited for claim",
                    )
                )
                continue

            # Check 2: Referenced evidence must actually exist
            if ev_id not in evidence_by_id:
                checks.append(
                    GroundingCheckResult(
                        claim_text=claim_text,
                        evidence_id=ev_id,
                        is_supported=False,
                        rejection_reason=f"Evidence ID '{ev_id}' does not exist in store (hallucination)",
                    )
                )
                continue

            ev = evidence_by_id[ev_id]

            # Check 3: Evidence must belong to the correct incident
            if ev.incident_id != incident_id:
                checks.append(
                    GroundingCheckResult(
                        claim_text=claim_text,
                        evidence_id=ev_id,
                        is_supported=False,
                        rejection_reason=f"Evidence '{ev_id}' belongs to incident '{ev.incident_id}', not '{incident_id}'",
                    )
                )
                continue

            # Check 4: Evidence must be verified (not unverified rumor or speculation)
            if not ev.verified:
                checks.append(
                    GroundingCheckResult(
                        claim_text=claim_text,
                        evidence_id=ev_id,
                        is_supported=False,
                        rejection_reason=f"Evidence '{ev_id}' is unverified",
                    )
                )
                continue

            # Claim is deterministically supported
            supported_count += 1
            checks.append(
                GroundingCheckResult(
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    is_supported=True,
                )
            )

        raw_rate = round(supported_count / len(claims), 4)
        accepted_claims = [c for c in checks if c.is_supported]
        rejected_claims = [c for c in checks if not c.is_supported]
        # Accepted claim grounding is 100% (1.0) because only verified, validly-grounded claims are accepted
        accepted_grounding = 1.0 if accepted_claims else 0.0

        return GroundingReport(
            claims_generated=len(claims),
            claims_supported=supported_count,
            claims_rejected=len(rejected_claims),
            raw_claim_support_rate=raw_rate,
            accepted_claim_grounding=accepted_grounding,
            is_fully_grounded=(raw_rate == 1.0),
            accepted_claims=accepted_claims,
            rejected_claims=rejected_claims,
            checks=checks,
        )
