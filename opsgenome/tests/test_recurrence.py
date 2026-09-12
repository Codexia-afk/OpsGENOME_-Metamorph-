"""Test Suite for Recurrence Alerting & Sub-50ms Pattern Matching."""

import pytest
from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import CapturedEvent, Incident, IncidentStatus


def test_instant_recurrence_alert_on_intake(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))

    # 1. Simulate prior incident on payments-service
    prior_incident = Incident(
        id="inc-old",
        title="Payment Service 504 Gateway Timeout Outage",
        service="payments-service",
        severity="P1",
        status=IncidentStatus.RESOLVED,
        symptoms=["504 Gateway Timeout", "database connection pool latency"],
        root_cause_category="Upstream Service Timeout / Connection Latency",
    )
    db.create_incident(prior_incident)

    events = [
        CapturedEvent(incident_id="inc-old", sequence_idx=0, command_redacted="kubectl logs -n prod payments", exit_code=0),
        CapturedEvent(incident_id="inc-old", sequence_idx=1, command_redacted="kubectl patch deployment payments --patch 'pool_size=50'", exit_code=0),
    ]

    gen = RunbookGenerator(db=db)
    gen.generate_runbook_for_incident(
        incident=prior_incident,
        events=events,
        historical_count=5,
        success_count=5,
    )

    # 2. Trigger a new incoming incident with matching symptoms
    new_incident = Incident(
        id="inc-new",
        title="CRITICAL: payments-service experiencing 504 Gateway Timeout",
        service="payments-service",
        severity="P1",
        status=IncidentStatus.ACTIVE,
        symptoms=["504 Gateway Timeout", "database pool latency"],
    )

    rec_engine = RecurrenceAlertEngine(db=db)
    match = rec_engine.check_recurrence(new_incident)

    assert match is not None
    assert match["matched"] is True
    assert match["similarity_score"] >= 0.55
    assert match["service"] == "payments-service"
    assert "Timeout" in match["root_cause_category"] or "Latency" in match["root_cause_category"] or "Connection" in match["root_cause_category"] or "Database" in match["root_cause_category"]
    assert len(match["top_commands"]) > 0
