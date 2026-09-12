"""Regression tests for the local capture security and evidence boundary."""

from fastapi.testclient import TestClient

from opsgenome.daemon.server import create_app
from opsgenome.storage.db import DatabaseManager


def test_capture_never_persists_raw_alias_or_structured_secret(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    client = TestClient(create_app(db=db))
    incident = client.post("/api/v1/incidents", json={"title": "payments failing"}).json()["incident"]
    secret = "d9F8q2Lx9zK1mP5vR8tY3wQ"
    response = client.post("/api/v1/events/capture", json={
        "incident_id": incident["id"],
        "command": f"kubectl get pods --token={secret}",
        "stdout": "CrashLoopBackOff",
        "before_state": {"summary": "CrashLoopBackOff", "healthy": False, "token": secret},
        "after_state": {"summary": "Running", "healthy": True, "token": secret},
    })
    assert response.status_code == 200
    event = db.get_events_for_incident(incident["id"])[0]
    assert secret not in event.raw_command
    assert event.command_raw == ""
    snapshot = db.get_snapshots_for_incident(incident["id"])[0]
    assert secret not in str(snapshot.before_state)
    assert "RECOVERY" in snapshot.diff_summary


def test_search_labels_fact_inference_and_recommendation(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    client = TestClient(create_app(db=db))
    client.post("/api/v1/incidents", json={"title": "payments deployment timeout", "service": "payments"})
    response = client.get("/api/v1/search", params={"q": "payments timeout"})
    assert response.status_code == 200
    assert set(response.json()) >= {"fact", "inference", "recommendation"}
