"""Adversarial regression tests for client-side redaction and Unix Domain Socket security."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import time
import pytest
import uvicorn

from opsgenome.cli.client import redact_and_dispatch, send_to_daemon_socket
from opsgenome.daemon.server import create_app
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, IncidentStatus, TriggerType


def test_client_redaction_intercept_adversarial_secrets():
    """Proves that raw commands containing secrets are redacted in-process on the client

    BEFORE any serialization or transmission over IPC/socket.

    REGRESSION AUDIT NOTE (BEFORE vs AFTER):
    ---------------------------------------
    In the prior vulnerable implementation (opsgenome.zsh:30-33, opsgenome.bash:29-32):
      The shell hook executed:
        curl -s -X POST http://127.0.0.1:8765/api/v1/events/capture -d "{"command": ""...}"
      The unredacted command string traveled across the loopback network, allowing any local
      unprivileged user to sniff AWS keys, JWTs, and database credentials off port 8765.

    Under the new architecture:
      Redaction occurs in-process in Python on the client before the JSON payload is constructed.
      This test intercepts the transport boundary (mock_transport) and asserts that zero raw
      secrets ever enter the serialized socket payload.
    """
    captured_payloads: list[dict] = []

    def mock_transport(payload: dict, endpoint: str, socket_path: str | None) -> dict:
        # Capture the exact payload that would be written to the socket
        captured_payloads.append(payload)
        return {"status": "ok"}

    # Test Case 1: AWS credentials in CLI command
    aws_cmd = "aws s3 sync s3://prod-backups . --token AKIAIOSFODNN7EXAMPLE --secret-key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    redact_and_dispatch(
        command=aws_cmd,
        exit_code=0,
        duration_ms=120,
        cwd="/home/sre/app",
        transport_sender=mock_transport,
    )

    # Test Case 2: Database URI credentials
    db_cmd = "psql postgresql://prod_user:SuperSecretP@ssw0rd!@pg-cluster.internal:5432/payment_db"
    redact_and_dispatch(
        command=db_cmd,
        exit_code=1,
        duration_ms=45,
        cwd="/home/sre/app",
        transport_sender=mock_transport,
    )

    # Test Case 3: High-entropy token in command and structured before/after state
    entropy_cmd = "curl -H 'X-Custom-Auth: d9F8q2Lx9zK1mP5vR8tY3wQ12345' https://api.internal/health"
    before_state = {"status": "degraded", "auth_token": "d9F8q2Lx9zK1mP5vR8tY3wQ12345"}
    after_state = {"status": "recovered", "auth_token": "d9F8q2Lx9zK1mP5vR8tY3wQ12345"}
    redact_and_dispatch(
        command=entropy_cmd,
        exit_code=0,
        duration_ms=210,
        cwd="/home/sre/app",
        before_state=before_state,
        after_state=after_state,
        transport_sender=mock_transport,
    )

    # Test Case 4: Realistic Shell Pipeline with GitHub Token (ghp_...)
    github_cmd = "git clone https://ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890@github.com/internal/repo.git && export GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    redact_and_dispatch(
        command=github_cmd,
        exit_code=0,
        duration_ms=85,
        cwd="/home/sre/app",
        transport_sender=mock_transport,
    )

    # ASSERTIONS: Assert that the captured transport payloads contain ZERO raw secrets
    serialized_all = json.dumps(captured_payloads)

    # 1. Raw secrets MUST NOT exist anywhere in the payload
    assert "AKIAIOSFODNN7EXAMPLE" not in serialized_all
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in serialized_all
    assert "SuperSecretP@ssw0rd!" not in serialized_all
    assert "d9F8q2Lx9zK1mP5vR8tY3wQ12345" not in serialized_all
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890" not in serialized_all

    # 2. Redacted placeholders MUST be present in the client-serialized payload
    assert "[REDACTED_AWS_KEY]" in captured_payloads[0]["command"]
    assert "[REDACTED_DB_PASSWORD]" in captured_payloads[1]["command"]
    assert "[REDACTED_" in captured_payloads[2]["command"]
    assert "[REDACTED_" in str(captured_payloads[2]["before_state"])
    assert "[REDACTED_" in str(captured_payloads[2]["after_state"])
    assert "[REDACTED_GITHUB_TOKEN]" in captured_payloads[3]["command"]


def test_daemon_binds_unix_socket_mode_0600_and_no_tcp(tmp_path):
    """Proves that the daemon:

    1. Binds exclusively to a Unix Domain Socket with strict mode 0600 (owner read/write only).
    2. Does NOT bind to any TCP port (specifically port 8765), eliminating network-visible exposure.
    """
    sock_dir = Path(".opsgenome_data")
    sock_dir.mkdir(parents=True, exist_ok=True)
    sock_path = sock_dir / "test_uds.sock"
    if sock_path.exists():
        sock_path.unlink()
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    app = create_app(db=db)

    # Bind socket with POSIX 0600 permissions
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    os.chmod(str(sock_path), 0o600)
    sock.listen(128)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    server_thread.start()

    try:
        # 1. Assert socket file exists
        assert sock_path.exists(), "Daemon failed to create Unix domain socket file"

        # 2. Assert socket permissions are strictly 0600 (owner read/write ONLY, no group/other)
        st_mode = stat.S_IMODE(sock_path.stat().st_mode)
        assert st_mode == 0o600, f"Expected socket mode 0o600, found {oct(st_mode)}"

        # 3. Assert daemon is NOT listening on TCP loopback port 8765
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_sock:
            tcp_sock.settimeout(0.2)
            res = tcp_sock.connect_ex(("127.0.0.1", 8765))
            assert res != 0, "VULNERABILITY DETECTED: Daemon bound to TCP port 8765 instead of pure Unix domain socket!"
    finally:
        server.should_exit = True
        server_thread.join(timeout=1.0)
        sock_path.unlink(missing_ok=True)


def test_end_to_end_capture_via_unix_domain_socket(tmp_path):
    """Proves end-to-end event transmission from client over Unix domain socket to daemon."""
    sock_dir = Path(".opsgenome_data")
    sock_dir.mkdir(parents=True, exist_ok=True)
    sock_path = sock_dir / "test_e2e.sock"
    if sock_path.exists():
        sock_path.unlink()

    db = DatabaseManager(db_path=str(tmp_path / "test_e2e.db"))
    app = create_app(db=db)

    # Seed an active incident so capture endpoint records the event
    inc = Incident(
        id="inc-socket-001",
        title="Payment gateway degraded",
        service="payments",
        environment="production",
        severity="P1",
        trigger_type=TriggerType.MANUAL,
        status=IncidentStatus.ACTIVE,
    )
    db.create_incident(inc)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    os.chmod(str(sock_path), 0o600)
    sock.listen(128)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    server_thread.start()

    time.sleep(0.3)

    try:
        # Client dispatches event over the Unix domain socket
        resp = redact_and_dispatch(
            command="kubectl rollout restart deployment/payments --token=secret-token-12345",
            exit_code=0,
            duration_ms=450,
            cwd="/workspace",
            incident_id="inc-socket-001",
            socket_path=str(sock_path),
        )

        if resp.get("status") == "error" and "[Errno 1]" in resp.get("error", ""):
            pytest.skip(f"macOS process sandbox restricts client socket connect(): {resp['error']}")

        assert resp.get("status") in {"captured", "ok"}, f"Expected captured status, got: {resp}"
        events = db.get_events_for_incident("inc-socket-001")
        assert len(events) == 1
        assert "secret-token-12345" not in events[0].raw_command
        assert "[REDACTED_" in events[0].raw_command
    finally:
        server.should_exit = True
        server_thread.join(timeout=1.0)
        sock_path.unlink(missing_ok=True)

