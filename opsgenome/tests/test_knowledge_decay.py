"""Test Suite for Knowledge Status Decay (VERIFIED, AGING, STALE, CONTRADICTED)."""

from datetime import datetime, timedelta, timezone
import pytest
from opsgenome.ai.confidence import ConfidenceEngine
from opsgenome.storage.models import KnowledgeStatus


def test_knowledge_decay_fresh_verified():
    now = datetime.now(timezone.utc)
    status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=5,
        successful_resolutions=5,
        escalations=0,
        last_matched_at=now - timedelta(days=5),
    )
    assert status == KnowledgeStatus.VERIFIED


def test_knowledge_decay_aging():
    now = datetime.now(timezone.utc)
    status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=5,
        successful_resolutions=5,
        escalations=0,
        last_matched_at=now - timedelta(days=45),
    )
    assert status == KnowledgeStatus.AGING


def test_knowledge_decay_stale():
    now = datetime.now(timezone.utc)
    status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=5,
        successful_resolutions=5,
        escalations=0,
        last_matched_at=now - timedelta(days=100),
    )
    assert status == KnowledgeStatus.STALE


def test_knowledge_decay_contradicted():
    now = datetime.now(timezone.utc)
    status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=3,
        successful_resolutions=0,
        escalations=2,
        last_matched_at=now - timedelta(days=2),
    )
    assert status == KnowledgeStatus.CONTRADICTED


def test_contradicted_historical_knowledge_when_command_succeeds_but_health_fails():
    """Test 3: Historical rollback was successful (VERIFIED). In a new incident,
    'kubectl rollout undo deployment/payments-api' executed with exit 0,
    but health verification failed (service degraded, is_healthy=False).
    Status immediately transitions to CONTRADICTED and is archived as a dead end.
    """
    now = datetime.now(timezone.utc)
    # Step 1: Historical baseline was VERIFIED (5 resolutions, 0 escalations)
    baseline_status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=5,
        successful_resolutions=5,
        escalations=0,
        last_matched_at=now - timedelta(days=2),
    )
    assert baseline_status == KnowledgeStatus.VERIFIED

    # Step 2: In new incident, command runs with exit_code=0, but health verification fails (is_healthy=False)
    command_executed = "kubectl rollout undo deployment/payments-api"
    exit_code = 0
    is_healthy = False  # Health check failed after command execution

    contradicted_status = ConfidenceEngine.calculate_knowledge_status(
        total_incidents=6,
        successful_resolutions=5,
        escalations=1,
        last_matched_at=now,
        last_execution_healthy=is_healthy,
    )

    # Must immediately transition to CONTRADICTED
    assert contradicted_status == KnowledgeStatus.CONTRADICTED
