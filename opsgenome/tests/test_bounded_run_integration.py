"""Integration Tests for Bounded Command Execution and Error Parsing across Stacks."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from click.testing import CliRunner
from opsgenome.cli.main import cli
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Event, Incident, IncidentStatus


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_bounded_run_python_checkout(tmp_path, repo_root, monkeypatch):
    """Run real Python script and assert stored event has exact parsed_error fields."""
    db_file = str(tmp_path / "global.db")
    monkeypatch.setenv("OPSGENOME_DB_PATH", db_file)
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    checkout_dir = repo_root / "demo-projects" / "svc-checkout"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.chdir(str(checkout_dir))
        result = runner.invoke(cli, ["run", "python3 checkout.py"])

    # Command fails with exit code 1 as expected
    assert result.exit_code == 1

    db = DatabaseManager(db_path=db_file)
    incidents = db.list_incidents()
    assert len(incidents) >= 1
    inc = incidents[-1]

    events = db.get_events_for_incident(inc.id)
    assert len(events) >= 1
    event = events[-1]

    # Verify structured parsed_error fields
    pe = event.parsed_error
    assert pe is not None
    assert pe["language"] == "python"
    assert pe["exception_type"] == "KeyError"
    assert pe["message"] == "'api_secret_key'"
    assert pe["file"].endswith("checkout.py")
    assert pe["line"] == 17
    assert len(pe["stack_frames"]) >= 1
    assert pe["stack_frames"][0]["line"] == 17
    assert pe["stack_frames"][0]["function"] == "init_payment_gateway"

    assert event.project == "svc-checkout"
    assert event.stack == "python"


def test_bounded_run_java_billing(tmp_path, repo_root, monkeypatch):
    """Run real Java script and assert stored event has exact parsed_error fields (file & line)."""
    db_file = str(tmp_path / "global.db")
    monkeypatch.setenv("OPSGENOME_DB_PATH", db_file)
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    billing_dir = repo_root / "demo-projects" / "svc-billing"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.chdir(str(billing_dir))
        result = runner.invoke(cli, ["run", "java BillingService.java"])

    assert result.exit_code == 1

    db = DatabaseManager(db_path=db_file)
    incidents = db.list_incidents()
    assert len(incidents) >= 1
    inc = incidents[-1]

    events = db.get_events_for_incident(inc.id)
    assert len(events) >= 1
    event = events[-1]

    pe = event.parsed_error
    assert pe is not None
    assert pe["language"] == "java"
    # Root cause in Caused by: chain
    assert pe["exception_type"] == "java.lang.NullPointerException"
    assert 'jurisdictionCode' in pe["message"]
    assert pe["file"] == "BillingService.java"
    assert pe["line"] == 29
    assert len(pe["stack_frames"]) >= 1
    assert pe["stack_frames"][0]["file"] == "BillingService.java"
    assert pe["stack_frames"][0]["line"] == 29
    assert "calculateTaxAmount" in pe["stack_frames"][0]["function"]

    assert event.project == "svc-billing"
    assert event.stack == "java"


def test_bounded_run_javascript_auth(tmp_path, repo_root, monkeypatch):
    """Run real Node.js script and assert stored event has exact parsed_error fields."""
    db_file = str(tmp_path / "global.db")
    monkeypatch.setenv("OPSGENOME_DB_PATH", db_file)
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    auth_dir = repo_root / "demo-projects" / "svc-auth"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.chdir(str(auth_dir))
        result = runner.invoke(cli, ["run", "node auth.js"])

    assert result.exit_code == 1

    db = DatabaseManager(db_path=db_file)
    incidents = db.list_incidents()
    assert len(incidents) >= 1
    inc = incidents[-1]

    events = db.get_events_for_incident(inc.id)
    assert len(events) >= 1
    event = events[-1]

    pe = event.parsed_error
    assert pe is not None
    assert pe["language"] == "javascript"
    assert pe["exception_type"] == "TypeError"
    assert "authorization" in pe["message"]
    assert pe["file"].endswith("auth.js")
    assert pe["line"] == 12
    assert len(pe["stack_frames"]) >= 1
    assert pe["stack_frames"][0]["function"] == "parseBearerToken"

    assert event.project == "svc-auth"
    assert event.stack == "javascript"


def test_bounded_run_terraform_network(tmp_path, repo_root, monkeypatch):
    """Run real Terraform plan and assert stored event has exact parsed_error fields."""
    db_file = str(tmp_path / "global.db")
    monkeypatch.setenv("OPSGENOME_DB_PATH", db_file)
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    network_dir = repo_root / "demo-projects" / "infra-network"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.chdir(str(network_dir))
        result = runner.invoke(cli, ["run", "terraform plan"])

    assert result.exit_code == 1

    db = DatabaseManager(db_path=db_file)
    incidents = db.list_incidents()
    assert len(incidents) >= 1
    inc = incidents[-1]

    events = db.get_events_for_incident(inc.id)
    assert len(events) >= 1
    event = events[-1]

    pe = event.parsed_error
    assert pe is not None
    assert pe["language"] == "terraform"
    assert "environment" in pe["message"]
    assert pe["file"] == "main.tf"
    assert pe["line"] == 5

    assert event.project == "infra-network"
    assert event.stack == "terraform"


def test_cross_project_recurrence_across_stacks(tmp_path, repo_root, monkeypatch):
    """Step 7: Run checkout, resolve it, then run checkout-v2 and confirm cross-project match fires."""
    db_file = str(tmp_path / "global.db")
    monkeypatch.setenv("OPSGENOME_DB_PATH", db_file)
    monkeypatch.setenv("PYTHONPATH", str(repo_root))

    runner = CliRunner()

    # 1. Run svc-checkout bug
    checkout_dir = repo_root / "demo-projects" / "svc-checkout"
    os.chdir(str(checkout_dir))
    res1 = runner.invoke(cli, ["run", "python3 checkout.py"])
    assert res1.exit_code == 1

    # Resolve svc-checkout incident so runbook lands in global store
    res_resolve = runner.invoke(cli, ["resolve"])
    assert res_resolve.exit_code == 0
    assert "✔ Incident Resolved" in res_resolve.output

    # 2. Run svc-checkout-v2 bug in second project
    checkout_v2_dir = repo_root / "demo-projects" / "svc-checkout-v2"
    os.chdir(str(checkout_v2_dir))
    res2 = runner.invoke(cli, ["run", "python3 order_processor.py"])
    assert res2.exit_code == 1

    # 3. Verify cross-project match
    db = DatabaseManager(db_path=db_file)
    active_inc = db.get_active_incident()
    assert active_inc is not None
    assert active_inc.project == "svc-checkout-v2"

    rec_engine = RecurrenceAlertEngine(db=db)
    match = rec_engine.check_recurrence(active_inc, current_project="svc-checkout-v2")

    assert match is not None
    assert match["matched"] is True
    assert match["same_project"] is False
    assert match["source_project"] == "svc-checkout"
    assert match["target_project"] == "svc-checkout-v2"
    assert match["similarity_score"] >= 0.50
    assert match["trust_tier"] == "cross_project_unvalidated"
    assert "[CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT]" in match["alert_message"]
    assert "svc-checkout" in match["alert_message"]
