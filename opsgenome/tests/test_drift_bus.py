"""Test Suite for Systemic Drift Detection and Bus Factor Analytics."""

from datetime import datetime, timezone
import pytest
from opsgenome.prevention.bus_factor import BusFactorAnalyzer
from opsgenome.prevention.drift import DriftDetectionEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, IncidentStatus, RiskLevel


def test_systemic_drift_detection(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))

    # Simulate 3 recurring incidents with the same root cause
    for i in range(3):
        inc = Incident(
            id=f"inc-drift-{i}",
            title=f"Payments Timeout Surge #{i+1}",
            service="payments-service",
            severity="P1",
            status=IncidentStatus.RESOLVED,
            started_at=datetime.now(timezone.utc),
            root_cause_category="Upstream Service Timeout / Connection Latency",
        )
        db.create_incident(inc)

    drift_engine = DriftDetectionEngine(db=db, recurrence_threshold=2)
    reports = drift_engine.analyze_drift()

    assert len(reports) == 1
    rep = reports[0]
    assert rep.service == "payments-service"
    assert rep.incident_count == 3
    assert "ARCHITECTURAL DEFECT TICKET" in rep.backlog_recommendation


def test_bus_factor_single_engineer_critical_risk(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))

    # 4 incidents on auth-service, all resolved by Alice
    for i in range(4):
        inc = Incident(
            id=f"inc-auth-{i}",
            title=f"Auth Service Outage #{i}",
            service="auth-service",
            status=IncidentStatus.RESOLVED,
            resolved_by="alice_senior_sre",
        )
        db.create_incident(inc)

    analyzer = BusFactorAnalyzer(db=db)
    metrics = analyzer.analyze_services()

    assert len(metrics) == 1
    m = metrics[0]
    assert m.service == "auth-service"
    assert m.bus_factor_score == 1
    assert m.top_expert == "alice_senior_sre"
    assert m.top_expert_share == 1.0
    assert m.risk_level == RiskLevel.CRITICAL
