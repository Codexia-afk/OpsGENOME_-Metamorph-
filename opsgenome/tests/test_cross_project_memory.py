"""Test Suite for Cross-Project Incident Memory, Trust Asymmetry, and Permission Gate.

Verifies:
1. Cross-project recurrence matching attaches source_project, target_project, and same_project=False.
2. Presentation displays explicit lower-trust tier [CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT].
3. Permission Gate strictly forbids auto-apply under any flag (--auto-approve, --yolo).
4. Permission Gate requires explicit dual-confirmation typing 'CONFIRM FROM <source_project>'.
5. Same-project regression remains intact (allows auto_approve and single confirmation).
6. Global database preserves fail-closed secret redaction and migrates legacy databases.
"""

from __future__ import annotations

import sqlite3
import pytest
from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.prevention.permission_gate import (
    CrossProjectAcknowledgmentRequiredError,
    CrossProjectAutoApproveForbiddenError,
    FixApplicationGate,
    FixExecutionRequest,
)
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.security.redactor import SecurityBoundaryViolation
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Event, Incident, IncidentStatus, Runbook, RunbookStep
from opsgenome.storage.project_context import detect_project, detect_stack


def test_cross_project_recurrence_matching(tmp_path):
    """Verify that recurrence engine searches globally and flags cross-project matches with lower-trust tier."""
    db_file = str(tmp_path / "global.db")
    db = DatabaseManager(db_path=db_file)

    # 1. Seed historical incident in project-alpha
    alpha_incident = Incident(
        id="inc-alpha-001",
        title="Payment Pod CrashLoopBackOff OOMKilled",
        service="payments-service",
        severity="P1",
        status=IncidentStatus.RESOLVED,
        symptoms=["CrashLoopBackOff", "OOMKilled", "memory limit exceeded"],
        root_cause_category="Container OOMKilled / Insufficient Memory Limit",
        project="project-alpha",
        stack="kubernetes",
    )
    db.create_incident(alpha_incident)

    alpha_events = [
        Event(
            incident_id="inc-alpha-001",
            sequence_idx=0,
            command_redacted="kubectl describe pod payments-77d9c8b",
            exit_code=0,
            project="project-alpha",
            stack="kubernetes",
        ),
        Event(
            incident_id="inc-alpha-001",
            sequence_idx=1,
            command_redacted="kubectl set resources deployment payments --limits=memory=512Mi",
            exit_code=0,
            project="project-alpha",
            stack="kubernetes",
        ),
    ]

    gen = RunbookGenerator(db=db)
    gen.generate_runbook_for_incident(
        incident=alpha_incident,
        events=alpha_events,
        historical_count=3,
        success_count=3,
    )

    # 2. Trigger new intake incident in project-beta with matching symptoms
    beta_incident = Incident(
        id="inc-beta-001",
        title="Checkout Service CrashLoopBackOff memory limit exceeded",
        service="checkout-service",
        severity="P1",
        status=IncidentStatus.OPEN,
        symptoms=["CrashLoopBackOff", "memory limit exceeded"],
        project="project-beta",
        stack="kubernetes",
    )
    db.create_incident(beta_incident)

    rec_engine = RecurrenceAlertEngine(db=db)
    match = rec_engine.check_recurrence(beta_incident)

    assert match is not None
    assert match["matched"] is True
    assert match["same_project"] is False
    assert match["source_project"] == "project-alpha"
    assert match["target_project"] == "project-beta"
    assert match["trust_tier"] == "cross_project_unvalidated"
    assert "[CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT]" in match["alert_message"]
    assert "project-alpha" in match["alert_message"]
    assert "DO NOT apply without independent validation" in match["alert_message"]
    assert len(match["top_commands"]) > 0


def test_same_project_recurrence_matching(tmp_path):
    """Verify that same-project recurrence retains high-trust verified tier."""
    db_file = str(tmp_path / "global.db")
    db = DatabaseManager(db_path=db_file)

    incident_1 = Incident(
        id="inc-alpha-002",
        title="Gateway 504 Timeout",
        service="api-gateway",
        severity="P2",
        status=IncidentStatus.RESOLVED,
        symptoms=["504 Gateway Timeout", "upstream connection reset"],
        root_cause_category="Upstream Service Timeout",
        project="project-alpha",
    )
    db.create_incident(incident_1)

    events = [
        Event(
            incident_id="inc-alpha-002",
            sequence_idx=0,
            command_redacted="systemctl restart kong",
            exit_code=0,
            project="project-alpha",
        ),
    ]
    gen = RunbookGenerator(db=db)
    gen.generate_runbook_for_incident(incident=incident_1, events=events, historical_count=2, success_count=2)

    incoming_same = Incident(
        id="inc-alpha-003",
        title="API Gateway 504 Timeout recurring",
        service="api-gateway",
        severity="P2",
        status=IncidentStatus.OPEN,
        symptoms=["504 Gateway Timeout", "upstream connection reset"],
        project="project-alpha",
    )

    rec_engine = RecurrenceAlertEngine(db=db)
    match = rec_engine.check_recurrence(incoming_same)

    assert match is not None
    assert match["matched"] is True
    assert match["same_project"] is True
    assert match["source_project"] == "project-alpha"
    assert match["target_project"] == "project-alpha"
    assert match["trust_tier"] == "same_project_verified"
    assert "[SAME-PROJECT RECURRENCE MATCH]" in match["alert_message"]


def test_permission_gate_forbids_cross_project_auto_approve():
    """Verify that FixApplicationGate strictly forbids auto_approve for cross-project fixes."""
    executed = []

    req = FixExecutionRequest(
        runbook_id="rb-123",
        target_incident_id="inc-beta-001",
        target_project="project-beta",
        source_project="project-alpha",
        command="kubectl scale deployment/checkout --replicas=3",
        same_project=False,
        confirmed=True,
        auto_approve=True,  # Attempting to bypass
    )

    with pytest.raises(CrossProjectAutoApproveForbiddenError) as exc_info:
        FixApplicationGate.authorize_and_apply(req, runner_fn=lambda c: executed.append(c))

    assert "cannot be auto-applied under any configuration flag" in str(exc_info.value)
    assert "project-alpha" in str(exc_info.value)
    assert len(executed) == 0  # Command was never run


def test_permission_gate_cross_project_requires_dual_confirmation():
    """Verify that FixApplicationGate requires explicit typing of 'CONFIRM FROM <source_project>'."""
    executed = []

    # 1. Missing acknowledgment
    req_no_ack = FixExecutionRequest(
        runbook_id="rb-123",
        target_incident_id="inc-beta-001",
        target_project="project-beta",
        source_project="project-alpha",
        command="kubectl patch deployment/checkout -p '{\"spec\":{}}'",
        same_project=False,
        confirmed=True,
        cross_project_ack=None,
        auto_approve=False,
    )
    with pytest.raises(CrossProjectAcknowledgmentRequiredError) as exc_1:
        FixApplicationGate.authorize_and_apply(req_no_ack, runner_fn=lambda c: executed.append(c))
    assert "CONFIRM FROM PROJECT-ALPHA" in str(exc_1.value)
    assert len(executed) == 0

    # 2. Vague or generic acknowledgment (e.g. 'y', 'yes', 'CONFIRM')
    req_vague_ack = FixExecutionRequest(
        runbook_id="rb-123",
        target_incident_id="inc-beta-001",
        target_project="project-beta",
        source_project="project-alpha",
        command="kubectl patch deployment/checkout -p '{\"spec\":{}}'",
        same_project=False,
        confirmed=True,
        cross_project_ack="CONFIRM",
        auto_approve=False,
    )
    with pytest.raises(CrossProjectAcknowledgmentRequiredError):
        FixApplicationGate.authorize_and_apply(req_vague_ack, runner_fn=lambda c: executed.append(c))
    assert len(executed) == 0

    # 3. Exact matching acknowledgment: 'CONFIRM FROM project-alpha'
    req_exact_ack = FixExecutionRequest(
        runbook_id="rb-123",
        target_incident_id="inc-beta-001",
        target_project="project-beta",
        source_project="project-alpha",
        command="kubectl patch deployment/checkout -p '{\"spec\":{}}'",
        same_project=False,
        confirmed=True,
        cross_project_ack="CONFIRM FROM project-alpha",
        auto_approve=False,
    )
    result = FixApplicationGate.authorize_and_apply(req_exact_ack, runner_fn=lambda c: executed.append(c))

    assert result.executed is True
    assert result.status == "executed"
    assert "authorized with explicit dual-confirmation" in result.message
    assert len(executed) == 1
    assert executed[0] == "kubectl patch deployment/checkout -p '{\"spec\":{}}'"


def test_permission_gate_same_project_allows_auto_approve_and_single_confirm():
    """Verify that same-project fixes execute without dual-confirmation."""
    executed = []

    # 1. Single confirmation
    req_confirm = FixExecutionRequest(
        runbook_id="rb-same",
        target_incident_id="inc-alpha-001",
        target_project="project-alpha",
        source_project="project-alpha",
        command="systemctl reload nginx",
        same_project=True,
        confirmed=True,
        auto_approve=False,
    )
    res_1 = FixApplicationGate.authorize_and_apply(req_confirm, runner_fn=lambda c: executed.append(c))
    assert res_1.executed is True
    assert len(executed) == 1

    # 2. Auto-approve
    req_auto = FixExecutionRequest(
        runbook_id="rb-same",
        target_incident_id="inc-alpha-001",
        target_project="project-alpha",
        source_project="project-alpha",
        command="systemctl reload nginx",
        same_project=True,
        confirmed=False,
        auto_approve=True,
    )
    res_2 = FixApplicationGate.authorize_and_apply(req_auto, runner_fn=lambda c: executed.append(c))
    assert res_2.executed is True
    assert len(executed) == 2


def test_global_db_stack_and_project_detection():
    """Verify stack categorization heuristics and project tagging."""
    assert detect_stack("kubectl get pods -n kube-system") == "kubernetes"
    assert detect_stack("helm upgrade --install myapp ./chart") == "kubernetes"
    assert detect_stack("terraform apply -auto-approve") == "iac_terraform"
    assert detect_stack("docker-compose up -d") == "docker_containers"
    assert detect_stack("pg_dump -U postgres dbname") == "database"
    assert detect_stack("aws s3 cp file.txt s3://bucket") == "cloud_cli"
    assert detect_stack("npm run build && node server.js") == "app_runtime"


def test_legacy_database_migration_to_global_db(tmp_path):
    """Verify automatic migration of legacy opsgenome.db without project column into global.db."""
    legacy_dir = tmp_path / "legacy_workspace"
    legacy_dir.mkdir()
    legacy_db_file = legacy_dir / "opsgenome.db"

    # 1. Manually create an older schema SQLite DB without project and stack columns
    conn = sqlite3.connect(str(legacy_db_file))
    conn.execute("""
        CREATE TABLE incidents (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            trigger_source TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            service TEXT NOT NULL,
            environment TEXT NOT NULL,
            severity TEXT NOT NULL,
            resolved_by TEXT NOT NULL,
            symptoms TEXT,
            root_cause_category TEXT,
            summary TEXT,
            candidate_discard_at TEXT,
            metadata TEXT
        )
    """)
    conn.execute("""
        INSERT INTO incidents (id, started_at, trigger_source, status, title, service, environment, severity, resolved_by)
        VALUES ('inc-legacy-1', '2026-09-01T12:00:00Z', 'manual', 'resolved', 'Legacy Outage', 'old-service', 'prod', 'P1', 'sre')
    """)
    conn.commit()
    conn.close()

    # 2. Open modern DatabaseManager pointing to global.db in that folder
    modern_db_file = legacy_dir / "global.db"
    modern_db = DatabaseManager(db_path=str(modern_db_file))

    # 3. Verify that the legacy record was migrated into global.db with default 'legacy_project'
    migrated_inc = modern_db.get_incident("inc-legacy-1")
    assert migrated_inc is not None
    assert migrated_inc.title == "Legacy Outage"
    assert migrated_inc.project == "legacy_project"
    assert migrated_inc.service == "old-service"


def test_secret_redaction_fail_closed_on_global_db(tmp_path):
    """Verify that the database layer strictly enforces fail-closed secret redaction on global.db writes."""
    db_file = str(tmp_path / "global.db")
    db = DatabaseManager(db_path=db_file)

    # Attempt to persist an event with an unredacted raw AWS secret key
    raw_secret_cmd = "export AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"
    leaked_event = Event(
        id="ev-sec-01",
        incident_id="inc-sec-01",
        raw_command=raw_secret_cmd,
        project="project-alpha",
    )

    with pytest.raises(SecurityBoundaryViolation):
        db.save_event(leaked_event)
