"""Test Suite for FastAPI Webhooks, Anomaly Detection & Static UI."""

import pytest
from fastapi.testclient import TestClient
from opsgenome.daemon.anomaly_detector import CommandBurstAnomalyDetector
from opsgenome.daemon.server import create_app
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import IncidentStatus, TriggerType


def test_command_burst_anomaly_trigger(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    detector = CommandBurstAnomalyDetector(db=db, burst_threshold=3, window_seconds=30)

    # Command 1: kubectl get pods
    res1 = detector.record_command("kubectl get pods -n prod")
    assert res1 is None

    # Command 2: kubectl describe deployment payments
    res2 = detector.record_command("kubectl describe deployment payments")
    assert res2 is None

    # Command 3: kubectl logs -f payments-123
    res3 = detector.record_command("kubectl logs -f payments-123")
    assert res3 is not None
    assert res3.trigger_type == TriggerType.BURST_ANOMALY
    assert res3.status == IncidentStatus.ACTIVE
    assert res3.candidate_discard_at is not None


def test_pagerduty_webhook_endpoint(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    app = create_app(db=db)
    client = TestClient(app)

    payload = {
        "event": "incident.trigger",
        "incident": {
            "title": "CRITICAL: High Error Rate on Ingress Gateway",
            "service": {"summary": "ingress-controller"},
            "urgency": "high",
        },
    }

    response = client.post("/api/v1/webhooks/pagerduty", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["created"]) == 1

    active = db.get_active_incident()
    assert active is not None
    assert active.service == "ingress-controller"
    assert active.trigger_type == TriggerType.WEBHOOK_PAGERDUTY


def test_static_dashboard_endpoint(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    app = create_app(db=db)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "OpsGenome" in response.text
