"""Seed Stability & Determinism Test Suite.

Verifies that seed_incident_history runs cleanly and identically
across fresh databases with zero errors or discrepancies.
"""

from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.seed import seed_incident_history


def test_seed_stability_across_runs(tmp_path):
    # Run 3 consecutive clean seeding operations
    for run_idx in range(1, 4):
        db_file = tmp_path / f"clean_opsgenome_run_{run_idx}.db"
        db = DatabaseManager(db_path=str(db_file))

        seeded = seed_incident_history(db)
        assert len(seeded) == 11, f"Run {run_idx}: Expected 11 seeded incidents, got {len(seeded)}"

        # Verify runbooks
        runbooks = db.list_runbooks(service="payments-deploy")
        assert len(runbooks) == 3, f"Run {run_idx}: Expected 3 runbooks, got {len(runbooks)}"

        rb_map = {r.root_cause_category: r for r in runbooks}

        # 1. Config Runbook
        cfg = rb_map["Invalid Configuration / Breaking Deployment Revision"]
        assert cfg.success_count == 3
        assert cfg.failure_count == 0
        assert cfg.confidence_display == "100% — 3 of 3 uses"

        # 2. Timeout Runbook
        tm = rb_map["Database Connection Pool Saturation"]
        assert tm.success_count == 3
        assert tm.failure_count == 1
        assert tm.confidence_display == "75% — 3 of 4 uses"

        # 3. Memory Leak Runbook
        mem = rb_map["Container Memory Limit Exhaustion (OOMKilled)"]
        assert mem.success_count == 4
        assert mem.failure_count == 0
        assert mem.confidence_display == "100% — 4 of 4 uses"


def test_seed_idempotency_double_run_same_database(tmp_path):
    """Verifies that running seed_incident_history twice on the same database file
    is 100% idempotent and does not create duplicate incidents or runbooks.
    """
    db_file = tmp_path / "idempotent_opsgenome.db"
    db = DatabaseManager(db_path=str(db_file))

    # Run 1
    seeded_1 = seed_incident_history(db)
    assert len(seeded_1) == 11

    # Run 2 immediately on the same database instance / file
    seeded_2 = seed_incident_history(db)
    assert len(seeded_2) == 11

    # Verify discrete record counts remain unchanged
    incidents = db.list_incidents(service="payments-deploy")
    assert len(incidents) == 11

    runbooks = db.list_runbooks(service="payments-deploy")
    assert len(runbooks) == 3

    rb_map = {r.root_cause_category: r for r in runbooks}
    assert rb_map["Invalid Configuration / Breaking Deployment Revision"].success_count == 3
    assert rb_map["Database Connection Pool Saturation"].success_count == 3
    assert rb_map["Database Connection Pool Saturation"].failure_count == 1
    assert rb_map["Container Memory Limit Exhaustion (OOMKilled)"].success_count == 4

