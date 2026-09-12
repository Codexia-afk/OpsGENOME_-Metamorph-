"""Tests for Evidence Grounding Validator."""

from datetime import datetime, timezone
import pytest
from opsgenome.ai.grounding import EvidenceGroundingValidator
from opsgenome.storage.models import Evidence


def test_evidence_grounding_valid_citations():
    ev1 = Evidence(
        id="E101",
        incident_id="inc-pay-1",
        evidence_type="state_delta",
        summary="HTTP 504 error rate dropped from 42% to 0% after pool scale",
        verified=True,
    )
    ev2 = Evidence(
        id="E102",
        incident_id="inc-pay-1",
        evidence_type="log_output",
        summary="Database pool saturated with 100 active connections",
        verified=True,
    )

    claims = [
        {"claim": "Database pool was saturated under load", "evidence_id": "E102"},
        {"claim": "Scaling pool recovered HTTP error rate to 0%", "evidence_id": "E101"},
    ]

    report = EvidenceGroundingValidator.validate_grounding(claims, [ev1, ev2], "inc-pay-1")
    assert report.total_claims == 2
    assert report.supported_claims == 2
    assert report.hallucination_attempt_rate == 0.0
    assert report.gate_enforcement_rate == 1.0
    assert report.is_fully_grounded is True


def test_evidence_grounding_rejects_hallucinated_evidence():
    ev1 = Evidence(
        id="E101",
        incident_id="inc-pay-1",
        evidence_type="state_delta",
        summary="Verified fix",
        verified=True,
    )

    claims = [
        {"claim": "CPU reached 98%", "evidence_id": "E999_NON_EXISTENT"},
        {"claim": "Valid fix verified", "evidence_id": "E101"},
    ]

    report = EvidenceGroundingValidator.validate_grounding(claims, [ev1], "inc-pay-1")
    assert report.total_claims == 2
    assert report.supported_claims == 1
    assert report.hallucination_attempt_rate == 0.5
    assert report.gate_enforcement_rate == 1.0
    assert report.is_fully_grounded is False
    assert "hallucination" in report.checks[0].rejection_reason


def test_evidence_grounding_rejects_cross_incident_leakage():
    ev_other = Evidence(
        id="E201",
        incident_id="inc-other-99",
        evidence_type="state_delta",
        summary="From different incident",
        verified=True,
    )

    claims = [
        {"claim": "Borrowed claim from wrong incident", "evidence_id": "E201"},
    ]

    report = EvidenceGroundingValidator.validate_grounding(claims, [ev_other], "inc-pay-1")
    assert report.hallucination_attempt_rate == 1.0
    assert report.gate_enforcement_rate == 1.0
    assert report.is_fully_grounded is False
    assert "belongs to incident" in report.checks[0].rejection_reason


def test_honest_grounding_metrics_adversarial_fixture():
    """Test 1: Standard gate operation.
    
    Adversarial benchmark: 10 proposed claims, exactly 3 ungrounded/hallucinated.
    Gate correctly catches and blocks all 3.
    Asserts:
    - claims_generated == 10
    - claims_rejected == 3
    - hallucination_attempt_rate == 0.30 (30%)
    - successfully_blocked_claims == 3
    - gate_enforcement_rate == 1.0 (100%)
    - published_claims == 7
    """
    valid_evs = [
        Evidence(id=f"E{i}", incident_id="inc-pay-1", evidence_type="state_delta", summary=f"Evidence {i}", verified=True)
        for i in range(1, 8)
    ]
    cross_incident_ev = Evidence(
        id="E_CROSS", incident_id="inc-other-99", evidence_type="log_output", summary="Cross incident log", verified=True
    )
    unverified_ev = Evidence(
        id="E_UNVERIFIED", incident_id="inc-pay-1", evidence_type="log_output", summary="Unverified rumor", verified=False
    )

    available_evidence = valid_evs + [cross_incident_ev, unverified_ev]

    claims = [
        {"claim": f"Valid verified claim {i}", "evidence_id": f"E{i}"} for i in range(1, 8)
    ] + [
        {"claim": "Hallucinated claim with non-existent ID", "evidence_id": "E999_NON_EXISTENT"},
        {"claim": "Cross-incident claim borrowed from inc-other-99", "evidence_id": "E_CROSS"},
        {"claim": "Unverified claim from speculative log", "evidence_id": "E_UNVERIFIED"},
    ]

    report = EvidenceGroundingValidator.validate_grounding(claims, available_evidence, "inc-pay-1")

    # Honest metric 1: 3 out of 10 claims were hallucination attempts (30%)
    assert report.claims_generated == 10
    assert report.claims_supported == 7
    assert report.claims_rejected == 3
    assert report.total_failed_verification_claims == 3
    assert report.hallucination_attempt_rate == 0.30

    # Honest metric 2: 100% of the 3 hallucinated claims were successfully blocked
    assert report.successfully_blocked_claims == 3
    assert report.gate_enforcement_rate == 1.0
    assert report.published_claims == 7
    assert len(report.published_claims) == 7
    assert len(report.accepted_claims) == 7
    assert len(report.rejected_claims) == 3
    assert report.is_fully_grounded is False

    # Verify every accepted claim has is_supported == True and no rejected claims leaked into accepted
    for accepted in report.accepted_claims:
        assert accepted.is_supported is True
        assert accepted.evidence_id not in {"E999_NON_EXISTENT", "E_CROSS", "E_UNVERIFIED"}


def test_leaky_gate_proves_metric_not_tautological():
    """Test 2: Leaky gate (PROVES METRIC IS NOT TAUTOLOGICAL).

    Constructs a scenario where 3 claims fail verification, but a controlled
    publication gate fails to block 1 of them (allowing 1 unverified claim to leak into published output).

    Asserts:
    - total_failed_verification_claims == 3
    - successfully_blocked_claims == 2
    - gate_enforcement_rate == 0.6667 (2 / 3)

    This test proves the metric actually drops below 1.0 when a leak occurs,
    and would FAIL if gate_enforcement_rate were len(rejected_claims) / len(rejected_claims).
    """
    valid_evs = [
        Evidence(id=f"E{i}", incident_id="inc-pay-1", evidence_type="state_delta", summary=f"Evidence {i}", verified=True)
        for i in range(1, 8)
    ]
    cross_incident_ev = Evidence(
        id="E_CROSS", incident_id="inc-other-99", evidence_type="log_output", summary="Cross incident log", verified=True
    )
    unverified_ev = Evidence(
        id="E_UNVERIFIED", incident_id="inc-pay-1", evidence_type="log_output", summary="Unverified rumor", verified=False
    )
    available_evidence = valid_evs + [cross_incident_ev, unverified_ev]

    claims = [
        {"claim": f"Valid verified claim {i}", "evidence_id": f"E{i}"} for i in range(1, 8)
    ] + [
        {"claim": "Hallucinated claim with non-existent ID", "evidence_id": "E999_NON_EXISTENT"},
        {"claim": "Cross-incident claim borrowed from inc-other-99", "evidence_id": "E_CROSS"},
        {"claim": "Unverified claim from speculative log", "evidence_id": "E_UNVERIFIED"},
    ]

    # Baseline report: 3 fail verification
    clean_report = EvidenceGroundingValidator.validate_grounding(claims, available_evidence, "inc-pay-1")
    assert clean_report.claims_rejected == 3
    assert clean_report.total_failed_verification_claims == 3

    # Controlled leaky gate: 2 are blocked, 1 unverified claim leaks to publication
    leaked_claim = clean_report.rejected_claims[0]  # E999_NON_EXISTENT
    leaky_published = list(clean_report.accepted_claims) + [leaked_claim]

    leaky_report = EvidenceGroundingValidator.validate_grounding(
        claims, available_evidence, "inc-pay-1", published_claims=leaky_published
    )

    # 3 claims failed verification
    assert leaky_report.total_failed_verification_claims == 3
    # Exactly 2 were successfully blocked; 1 leaked through
    assert leaky_report.successfully_blocked_claims == 2
    # The gate enforcement rate MUST be 2 / 3 = 0.6667 (66.67%)
    assert leaky_report.gate_enforcement_rate == 0.6667
    assert leaky_report.gate_enforcement_rate < 1.0
    # Proves this is NOT len(rejected)/len(rejected), which would be 1.0
    assert leaky_report.gate_enforcement_rate != 1.0


