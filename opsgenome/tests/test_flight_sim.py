"""Test Suite for SRE Flight Simulator & Interactive Replay."""

import pytest
from opsgenome.simulator.flight_sim import FlightSimulatorEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import CapturedEvent, CausalStatus, Incident, IncidentStatus


def test_flight_simulator_scenario_generation(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))

    inc = Incident(
        id="inc-sim-1",
        title="Postgres Connection Exhaustion Flight Sim",
        service="db-proxy",
        severity="P1",
        status=IncidentStatus.RESOLVED,
        root_cause_category="Database Connection Pool Saturation",
        resolved_by="lead_sre",
    )
    db.create_incident(inc)

    events = [
        CapturedEvent(incident_id="inc-sim-1", sequence_idx=0, command_redacted="kubectl get pods -n prod", exit_code=0),
        CapturedEvent(incident_id="inc-sim-1", sequence_idx=1, command_redacted="systemctl restart db-proxy", exit_code=1, stderr_summary="failed to bind port 5432"),
        CapturedEvent(incident_id="inc-sim-1", sequence_idx=2, command_redacted="kubectl patch configmap db-config --patch 'max_connections=200'", exit_code=0, status=CausalStatus.VERIFIED_FIX),
        CapturedEvent(incident_id="inc-sim-1", sequence_idx=3, command_redacted="curl -I http://localhost:8080/health", exit_code=0),
    ]
    for ev in events:
        db.save_event(ev)

    sim_engine = FlightSimulatorEngine(db=db)
    scenario = sim_engine.build_simulation("inc-sim-1")

    assert scenario is not None
    assert scenario["total_steps"] == 4
    steps = scenario["steps"]

    # Step 1: Intake
    assert steps[0]["phase"] == "INTAKE"

    # Step 2: Attempted Fix Dead End
    assert "DEAD END" in steps[1]["phase"]
    assert "DEAD-END BRANCH" in steps[1]["expert_annotation"]

    # Step 3: Verified Fix with Quiz
    assert steps[2]["phase"] == "REMEDIAL FIX"
    assert "THE FIX" in steps[2]["expert_annotation"]
    assert steps[2]["quiz_question"] is not None
