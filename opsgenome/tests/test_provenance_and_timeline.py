"""Tests for Enriched Timeline Replay and Flagship Provenance API."""

from datetime import datetime, timezone
import pytest
from opsgenome.daemon.server import create_app
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    Event,
    EventClassification,
    Evidence,
    Incident,
    IncidentStatus,
    Runbook,
    RunbookStep,
    StateSnapshot,
    TriggerSource,
)
from starlette.testclient import TestClient


def test_timeline_and_provenance_endpoints():
    db = DatabaseManager(db_path=":memory:")
    app = create_app(db=db)
    client = TestClient(app)

    # 1. Create incident
    inc = Incident(
        id="inc-prov-101",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        trigger_source=TriggerSource.MANUAL,
        title="payments-deploy 504 Timeout Surge",
        service="payments-deploy",
        environment="production",
        severity="P1",
        status=IncidentStatus.RESOLVED,
        resolved_by="sarah_sre",
        symptoms=["504 Gateway Timeout", "Queue saturation"],
        summary="Resolved by rollback",
    )
    db.create_incident(inc)

    # 2. Add events (diagnostic, dead-end, fix)
    ev_diag = Event(
        id="ev-d1",
        incident_id=inc.id,
        timestamp=datetime.now(timezone.utc),
        raw_command="kubectl logs deployment/payments-deploy -n production",
        exit_code=0,
        stdout_snippet="ERROR 504: Database pool saturated",
        classification=EventClassification.UNKNOWN,
        signal_weight=0.7,
        tool_category="kubectl",
    )
    db.save_event(ev_diag)

    ev_dead = Event(
        id="ev-dead1",
        incident_id=inc.id,
        timestamp=datetime.now(timezone.utc),
        raw_command="kubectl rollout restart deployment/payments-deploy",
        exit_code=1,
        stderr_snippet="CrashLoopBackOff: pool exhaustion persisted",
        classification=EventClassification.DEAD_END,
        signal_weight=0.8,
        tool_category="kubectl",
    )
    db.save_event(ev_dead)

    ev_fix = Event(
        id="ev-f1",
        incident_id=inc.id,
        timestamp=datetime.now(timezone.utc),
        raw_command="kubectl rollout undo deployment/payments-deploy",
        exit_code=0,
        stdout_snippet="deployment.apps/payments-deploy rolled back",
        classification=EventClassification.FIX,
        signal_weight=0.95,
        tool_category="kubectl",
    )
    db.save_event(ev_fix)

    # 3. Add snapshot
    snap = StateSnapshot(
        id="snap-f1",
        incident_id=inc.id,
        event_id=ev_fix.id,
        resource_type="k8s_deployment",
        is_healthy=True,
        diff_summary="Latency dropped 2400ms -> 42ms, 0 errors",
        status_summary="Running healthy",
    )
    db.save_state_snapshot(snap)

    # 4. Add Evidence record
    ev_rec = Evidence(
        id="E101",
        incident_id=inc.id,
        event_id=ev_fix.id,
        evidence_type="state_delta",
        summary="Latency dropped from 2400ms to 42ms, 0 errors",
        verified=True,
    )
    db.save_evidence(ev_rec)

    # 5. Add Runbook
    rb = Runbook(
        id="rb-pay-01",
        title="Rollback Breaking Deployment Revision",
        root_cause_category="Configuration Error",
        service="payments-deploy",
        steps=[
            RunbookStep(
                step_number=1,
                title="Rollback payments deployment",
                command="kubectl rollout undo deployment/payments-deploy -n production",
                is_remediation=True,
            )
        ],
        earned_confidence_score=0.92,
    )
    db.save_runbook(rb)

    # Test GET /api/v1/incidents/{id}/timeline
    t_res = client.get(f"/api/v1/incidents/{inc.id}/timeline")
    assert t_res.status_code == 200
    t_data = t_res.json()
    assert len(t_data["steps"]) == 3
    # Check Section 11 required fields
    step1 = t_data["steps"][0]
    for req_field in ["timestamp", "source", "evidence_id", "state_transition", "command", "exit_code", "result", "decision", "verification_status"]:
        assert req_field in step1, f"Missing required field {req_field} in timeline step"

    assert t_data["steps"][1]["verification_status"] == "DEAD_END_FAILURE"
    assert t_data["steps"][2]["verification_status"] == "VERIFIED_RECOVERY"

    # Test GET /api/v1/incidents/{id}/provenance
    p_res = client.get(f"/api/v1/incidents/{inc.id}/provenance")
    assert p_res.status_code == 200
    p_data = p_res.json()
    assert "provenance_chain" in p_data
    stages = [node["stage"] for node in p_data["provenance_chain"]]
    assert p_data["grounding_summary"]["gate_enforcement_rate"] == 1.0
    assert p_data["grounding_summary"]["hallucination_attempt_rate"] == 0.0
    assert "total_failed_verification_claims" in p_data["grounding_summary"]
    assert "successfully_blocked_claims" in p_data["grounding_summary"]
    assert "explanation" in p_data["grounding_summary"]
    # Verification node in chain also includes real enforcement metrics
    verif_node = next(n for n in p_data["provenance_chain"] if n["stage"] == "VERIFICATION")
    assert verif_node["record"]["gate_enforcement_rate"] == 1.0
    assert verif_node["record"]["successfully_blocked_claims"] == 0
    print("✔ Enriched Timeline and Flagship Provenance verified with 100% contract adherence.")
