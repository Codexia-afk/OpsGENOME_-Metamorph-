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
    assert report.grounding_rate == 1.0
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
    assert report.grounding_rate == 0.5
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
    assert report.grounding_rate == 0.0
    assert report.is_fully_grounded is False
    assert "belongs to incident" in report.checks[0].rejection_reason
