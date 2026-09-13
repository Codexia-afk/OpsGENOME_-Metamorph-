"""Client-Side In-Process Redactor and Unix Domain Socket Event Dispatcher.

Guarantees:
1. Commands and state telemetry are redacted in-process on the client BEFORE any
   serialization, network socket transmission, or subprocess boundary.
2. Transmission occurs strictly over a local Unix domain socket restricted to
   the current user (mode 0600), never over a network-visible TCP loopback port.
"""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any
from opsgenome.security.redactor import EventSanitizer, SecretRedactor, redact_structure, redact_text

DEFAULT_SOCKET_PATH = Path.home() / ".opsgenome" / "daemon.sock"


def get_default_socket_path() -> str:
    if "OPSGENOME_SOCKET_PATH" in os.environ:
        return os.environ["OPSGENOME_SOCKET_PATH"]
    try:
        home_dir = Path.home() / ".opsgenome"
        home_dir.mkdir(parents=True, exist_ok=True)
        return str(home_dir / "daemon.sock")
    except (PermissionError, OSError):
        local_dir = Path(__file__).resolve().parents[2] / ".opsgenome_data"
        local_dir.mkdir(parents=True, exist_ok=True)
        return str(local_dir / "daemon.sock")


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    """HTTP client connection over Unix domain socket using Python standard library."""

    def __init__(self, uds_path: str, timeout: float = 2.0):
        super().__init__("localhost", timeout=timeout)
        self.uds_path = uds_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.uds_path)


def send_to_daemon_socket(
    payload: dict[str, Any],
    endpoint: str = "/api/v1/events/capture",
    socket_path: str | None = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Transmits an already-redacted JSON payload over a Unix domain socket to the local daemon."""
    sock_path = socket_path or get_default_socket_path()
    if not os.path.exists(sock_path):
        return {"status": "daemon_socket_unavailable", "socket_path": sock_path}

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "Host": "localhost",
    }

    conn = UnixSocketHTTPConnection(sock_path, timeout=timeout)
    try:
        conn.request("POST", endpoint, body=body, headers=headers)
        response = conn.getresponse()
        resp_data = response.read().decode("utf-8")
        try:
            return json.loads(resp_data)
        except Exception:
            return {"status": "ok", "http_status": response.status, "body": resp_data}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def redact_and_dispatch(
    command: str,
    exit_code: int = 0,
    duration_ms: int = 0,
    cwd: str = "",
    incident_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    socket_path: str | None = None,
    transport_sender=None,
    stdout_snippet: str | None = None,
    stderr_snippet: str | None = None,
) -> dict[str, Any]:
    """Redacts command and environment in-process on client BEFORE socket transmission.

    CRITICAL SECURITY INVARIANT:
    Raw command string is NEVER passed to curl, NEVER serialized into JSON,
    and NEVER transmitted over socket. Only sanitized fields are serialized.
    """
    redactor = SecretRedactor()

    # Step 1: In-process client-side redaction (BEFORE any transmission or serialization)
    redacted_cmd, _ = redactor.redact(command)

    # In-process state snapshot redaction if provided
    safe_before, _ = redact_structure(before_state) if before_state else (None, [])
    safe_after, _ = redact_structure(after_state) if after_state else (None, [])
    safe_cwd = redact_text(cwd) if cwd else ""

    # Ensure no raw secret remains
    assert redactor.validate_clean(redacted_cmd), "Client-side redaction failed clean validation"

    # Step 2: Build payload ONLY with sanitized data
    payload: dict[str, Any] = {
        "command": redacted_cmd,
        "exit_code": int(exit_code),
        "duration_ms": int(duration_ms),
        "cwd": safe_cwd,
    }
    if stdout_snippet:
        payload["stdout_snippet"] = redact_text(stdout_snippet)
    if stderr_snippet:
        payload["stderr_snippet"] = redact_text(stderr_snippet)
    if incident_id:
        payload["incident_id"] = incident_id
    if safe_before:
        payload["before_state"] = safe_before
    if safe_after:
        payload["after_state"] = safe_after

    # Step 3: Transmit via Unix domain socket
    sender = transport_sender or send_to_daemon_socket
    return sender(payload, endpoint="/api/v1/events/capture", socket_path=socket_path)


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if len(args) > 0 else sys.stdin.read()
    code = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
    dur = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    workdir = args[3] if len(args) > 3 else os.getcwd()
    sock = args[4] if len(args) > 4 else None

    if cmd:
        redact_and_dispatch(
            command=cmd,
            exit_code=code,
            duration_ms=dur,
            cwd=workdir,
            socket_path=sock,
        )
