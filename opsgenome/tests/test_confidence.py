"""Test Suite for Earned Confidence Score, Cold-Start Honesty & Provenance."""

import pytest
from opsgenome.ai.confidence import ConfidenceEngine
from opsgenome.storage.models import ConfidenceLevel


def test_cold_start_honesty_low_sample_size():
    # Only 1 incident recorded
    score, level, prov = ConfidenceEngine.calculate_confidence(
        total_incidents=1,
        successful_resolutions=1,
        escalations=0,
    )
    assert level == ConfidenceLevel.COLD_START
    assert "Cold Start" in prov.provenance_trail_text
    assert prov.total_incidents_recorded == 1


def test_earned_confidence_mature_sample():
    # 8 incidents: 7 resolved, 1 escalation
    score, level, prov = ConfidenceEngine.calculate_confidence(
        total_incidents=8,
        successful_resolutions=7,
        escalations=1,
        verification_checks_passed=8,
        engineers=["alice", "bob", "carol"],
    )
    assert level == ConfidenceLevel.HIGH or level == ConfidenceLevel.MODERATE
    assert score >= 0.65
    assert "Based on 8 recorded incidents" in prov.provenance_trail_text
    assert len(prov.contributing_engineers) == 3


def test_earned_confidence_with_frequent_escalations():
    # 5 incidents, 3 escalations (low confidence)
    score, level, prov = ConfidenceEngine.calculate_confidence(
        total_incidents=5,
        successful_resolutions=2,
        escalations=3,
        verification_checks_passed=1,
    )
    assert level == ConfidenceLevel.LOW
    assert score < 0.50
