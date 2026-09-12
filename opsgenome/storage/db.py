"""Encrypted Local-First SQLite Database Manager.

Schema:
- incidents (id, started_at, ended_at, trigger_source, status, title, service, environment, severity, resolved_by, symptoms_json, root_cause_category, summary)
- events (id, incident_id, timestamp, raw_command, exit_code, stdout_snippet, stderr_snippet, signal_weight, classification, duration_ms, cwd, tool_category)
- state_snapshots (id, incident_id, event_id, resource_type, before_state_json, after_state_json, diff_summary, is_healthy, status_summary)
- causal_chains (id, incident_id, symptom, hypothesis, evidence_event_ids_json, fix_event_ids_json, outcome, confidence_score, recovery_time_seconds)
- runbooks (id, causal_chain_id, title, root_cause_category, steps_json, success_count, failure_count, confidence_score, version, last_matched_at, service, symptom_signature, negative_knowledge_json, verification_commands_json)
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from opsgenome.security.crypto import LocalCryptoManager
from opsgenome.security.redactor import EventSanitizer, SecurityBoundaryViolation, redact_structure, redact_text
from opsgenome.storage.models import (
    BusFactorMetric,
    CausalChain,
    ChainOutcome,
    Event,
    EventClassification,
    Evidence,
    Incident,
    IncidentStatus,
    KnowledgeStatus,
    RankedHypothesis,
    RecurrenceSignature,
    Runbook,
    StateSnapshot,
    SystemicDriftReport,
    TriggerSource,
    WhyWhyNot,
)


class DatabaseManager:
    """Manages local SQLite database operations with at-rest encryption and architectural security boundary."""

    def __init__(self, db_path: str | Path | None = None, crypto_manager: LocalCryptoManager | None = None):
        self.sanitizer = EventSanitizer()
        if db_path is not None:
            self.db_path = str(db_path)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.crypto = crypto_manager or LocalCryptoManager(
                key_dir=str(Path(self.db_path).parent) if self.db_path != ":memory:" else "./.opsgenome_data"
            )
        elif "OPSGENOME_DB_PATH" in os.environ:
            self.db_path = os.environ["OPSGENOME_DB_PATH"]
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.crypto = crypto_manager or LocalCryptoManager()
        else:
            try:
                home_dir = Path.home() / ".opsgenome"
                home_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = str(home_dir / "global.db")
                self.crypto = crypto_manager or LocalCryptoManager(key_dir=str(home_dir))
            except (PermissionError, OSError):
                local_dir = Path("./.opsgenome_data")
                local_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = str(local_dir / "global.db")
                self.crypto = crypto_manager or LocalCryptoManager(key_dir=str(local_dir))

        self._mem_conn = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create exact relational tables, migrate missing columns, and build indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
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
                    symptoms_json TEXT,
                    root_cause_category TEXT,
                    summary TEXT,
                    project TEXT NOT NULL DEFAULT 'default',
                    stack TEXT NOT NULL DEFAULT 'general'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL DEFAULT '1.0',
                    timestamp TEXT NOT NULL,
                    raw_command TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    stdout_snippet TEXT,
                    stderr_snippet TEXT,
                    signal_weight REAL NOT NULL,
                    classification TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    cwd TEXT,
                    tool_category TEXT NOT NULL,
                    project TEXT NOT NULL DEFAULT 'default',
                    stack TEXT NOT NULL DEFAULT 'general',
                    FOREIGN KEY(incident_id) REFERENCES incidents(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    event_id TEXT,
                    resource_type TEXT NOT NULL,
                    before_state_json TEXT,
                    after_state_json TEXT,
                    diff_summary TEXT,
                    is_healthy INTEGER NOT NULL,
                    status_summary TEXT,
                    FOREIGN KEY(incident_id) REFERENCES incidents(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS causal_chains (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    symptom TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    evidence_event_ids_json TEXT NOT NULL,
                    fix_event_ids_json TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    recovery_time_seconds INTEGER NOT NULL,
                    FOREIGN KEY(incident_id) REFERENCES incidents(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runbooks (
                    id TEXT PRIMARY KEY,
                    causal_chain_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    root_cause_category TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    success_count INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    confidence_score REAL NOT NULL,
                    version INTEGER NOT NULL,
                    last_matched_at TEXT NOT NULL,
                    service TEXT NOT NULL,
                    symptom_signature TEXT,
                    negative_knowledge_json TEXT,
                    verification_commands_json TEXT,
                    project TEXT NOT NULL DEFAULT 'default',
                    stack TEXT NOT NULL DEFAULT 'general'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recurrence_signatures (
                    incident_id TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    error_patterns_json TEXT,
                    symptom_tokens_json TEXT,
                    signature_hash TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS systemic_drift (
                    id TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    root_cause_category TEXT NOT NULL,
                    incident_count INTEGER NOT NULL,
                    timeline_dates_json TEXT,
                    drift_summary TEXT NOT NULL,
                    backlog_recommendation TEXT NOT NULL,
                    severity TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    event_id TEXT,
                    evidence_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    raw_payload_json TEXT,
                    FOREIGN KEY(incident_id) REFERENCES incidents(id)
                )
            """)

            # Auto-migrate columns if table existed previously with older columns
            def ensure_columns(table: str, required_cols: list[tuple[str, str]]) -> None:
                cursor.execute(f"PRAGMA table_info({table})")
                existing = [row["name"] for row in cursor.fetchall()]
                for col_name, col_type in required_cols:
                    if col_name not in existing:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

            ensure_columns("incidents", [
                ("ended_at", "TEXT"),
                ("trigger_source", "TEXT DEFAULT 'manual'"),
                ("trigger_type", "TEXT DEFAULT 'manual'"),
                ("symptoms_json", "TEXT DEFAULT '[]'"),
                ("root_cause_category", "TEXT DEFAULT 'Unknown'"),
                ("summary", "TEXT DEFAULT ''"),
                ("project", "TEXT DEFAULT 'default'"),
                ("stack", "TEXT DEFAULT 'general'"),
            ])

            ensure_columns("events", [
                ("schema_version", "TEXT DEFAULT '1.0'"),
                ("signal_weight", "REAL DEFAULT 0.5"),
                ("causal_score", "REAL DEFAULT 0.5"),
                ("classification", "TEXT DEFAULT 'unknown'"),
                ("status", "TEXT DEFAULT 'unknown'"),
                ("tool_category", "TEXT DEFAULT 'system'"),
                ("project", "TEXT DEFAULT 'default'"),
                ("stack", "TEXT DEFAULT 'general'"),
            ])

            ensure_columns("causal_chains", [
                ("why_why_not_json", "TEXT DEFAULT '{}'"),
                ("evidence_json", "TEXT DEFAULT '[]'"),
                ("ranked_hypotheses_json", "TEXT DEFAULT '[]'"),
                ("disambiguation_required", "INTEGER DEFAULT 0"),
            ])

            ensure_columns("runbooks", [
                ("success_count", "INTEGER DEFAULT 1"),
                ("failure_count", "INTEGER DEFAULT 0"),
                ("confidence_score", "REAL DEFAULT 0.0"),
                ("earned_confidence_score", "REAL DEFAULT 0.0"),
                ("confidence_level", "TEXT DEFAULT 'cold_start'"),
                ("knowledge_status", "TEXT DEFAULT 'verified'"),
                ("service", "TEXT DEFAULT 'core-service'"),
                ("symptom_signature", "TEXT DEFAULT ''"),
                ("negative_knowledge_json", "TEXT DEFAULT '[]'"),
                ("verification_commands_json", "TEXT DEFAULT '[]'"),
                ("rollback_steps_json", "TEXT DEFAULT '[]'"),
                ("why_why_not_json", "TEXT DEFAULT '{}'"),
                ("evidence_citations_json", "TEXT DEFAULT '[]'"),
                ("provenance_json", "TEXT DEFAULT '{}'"),
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
                ("project", "TEXT DEFAULT 'default'"),
                ("stack", "TEXT DEFAULT 'general'"),
            ])

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_project ON incidents(project)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_runbooks_service ON runbooks(service, root_cause_category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_runbooks_project ON runbooks(project)")
            conn.commit()

        self._migrate_legacy_db_if_needed()

    def _migrate_legacy_db_if_needed(self) -> None:
        """Migrates any existing records from legacy opsgenome.db to global.db with 'legacy_project' tag."""
        if self.db_path == ":memory:":
            return
        current_path = Path(self.db_path)
        legacy_path = current_path.parent / "opsgenome.db"
        if not legacy_path.exists():
            return
        try:
            if legacy_path.resolve() == current_path.resolve():
                return
        except Exception:
            return

        try:
            with sqlite3.connect(str(legacy_path)) as legacy_conn:
                legacy_conn.row_factory = sqlite3.Row
                l_cur = legacy_conn.cursor()
                l_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'")
                if not l_cur.fetchone():
                    return

                with self._get_connection() as conn:
                    cur = conn.cursor()
                    # 1. Migrate Incidents
                    l_cur.execute("SELECT * FROM incidents")
                    for r in l_cur.fetchall():
                        cols = list(r.keys())
                        proj = r["project"] if "project" in cols and r["project"] else "legacy_project"
                        stk = r["stack"] if "stack" in cols and r["stack"] else "general"
                        cur.execute(
                            """INSERT OR IGNORE INTO incidents
                            (id, started_at, ended_at, trigger_source, status, title, service, environment, severity, resolved_by, symptoms_json, root_cause_category, summary, project, stack)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                r["id"], r["started_at"], r["ended_at"] if "ended_at" in cols else None,
                                r["trigger_source"], r["status"], r["title"], r["service"], r["environment"],
                                r["severity"], r["resolved_by"], r["symptoms_json"] if "symptoms_json" in cols else "[]",
                                r["root_cause_category"] if "root_cause_category" in cols else "Unknown",
                                r["summary"] if "summary" in cols else "",
                                proj, stk,
                            ),
                        )

                    # 2. Migrate Events
                    l_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
                    if l_cur.fetchone():
                        l_cur.execute("SELECT * FROM events")
                        for r in l_cur.fetchall():
                            cols = list(r.keys())
                            cur.execute(
                                """INSERT OR IGNORE INTO events
                                (id, incident_id, schema_version, timestamp, raw_command, exit_code, stdout_snippet, stderr_snippet, signal_weight, classification, duration_ms, cwd, tool_category, sequence_idx, project, stack)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    r["id"], r["incident_id"], r["schema_version"] if "schema_version" in cols else "1.0",
                                    r["timestamp"], r["raw_command"], r["exit_code"],
                                    r["stdout_snippet"] if "stdout_snippet" in cols else "",
                                    r["stderr_snippet"] if "stderr_snippet" in cols else "",
                                    r["signal_weight"] if "signal_weight" in cols else 0.5,
                                    r["classification"] if "classification" in cols else "unknown",
                                    r["duration_ms"] if "duration_ms" in cols else 0,
                                    r["cwd"] if "cwd" in cols else "",
                                    r["tool_category"] if "tool_category" in cols else "system",
                                    r["sequence_idx"] if "sequence_idx" in cols else 0,
                                    r["project"] if "project" in cols and r["project"] else "legacy_project",
                                    r["stack"] if "stack" in cols and r["stack"] else "general",
                                ),
                            )

                    # 3. Migrate Runbooks
                    l_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runbooks'")
                    if l_cur.fetchone():
                        l_cur.execute("SELECT * FROM runbooks")
                        for r in l_cur.fetchall():
                            cols = list(r.keys())
                            cur.execute(
                                """INSERT OR IGNORE INTO runbooks
                                (id, causal_chain_id, title, root_cause_category, steps_json, success_count, failure_count, confidence_score, version, last_matched_at, service, symptom_signature, project, stack)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    r["id"], r["causal_chain_id"] if "causal_chain_id" in cols else "",
                                    r["title"], r["root_cause_category"], r["steps_json"],
                                    r["success_count"], r["failure_count"], r["confidence_score"],
                                    r["version"], r["last_matched_at"], r["service"],
                                    r["symptom_signature"] if "symptom_signature" in cols else "",
                                    r["project"] if "project" in cols and r["project"] else "legacy_project",
                                    r["stack"] if "stack" in cols and r["stack"] else "general",
                                ),
                            )
                    conn.commit()
        except Exception:
            pass

    # --- Incidents ---

    def create_incident(self, incident: Incident) -> Incident:
        symptoms_str = " ".join(incident.symptoms or [])
        if not self.sanitizer.redactor.validate_clean(incident.title or "") or \
           not self.sanitizer.redactor.validate_clean(incident.summary or "") or \
           not self.sanitizer.redactor.validate_clean(symptoms_str):
            raise SecurityBoundaryViolation(
                "Security Boundary Violation: Database layer rejected unredacted incident containing raw secrets. "
                "Untrusted input must pass through EventSanitizer."
            )
        clean_title = redact_text(incident.title)
        clean_summary = redact_text(incident.summary or "")
        clean_symptoms = [redact_text(s) for s in incident.symptoms]
        incident.title = clean_title
        incident.summary = clean_summary
        incident.symptoms = clean_symptoms

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(incidents)")
            cols = [row["name"] for row in cursor.fetchall()]

            data_map: dict[str, Any] = {
                "id": incident.id,
                "started_at": incident.started_at.isoformat(),
                "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
                "trigger_source": incident.trigger_source.value if hasattr(incident.trigger_source, 'value') else str(incident.trigger_source),
                "trigger_type": incident.trigger_source.value if hasattr(incident.trigger_source, 'value') else str(incident.trigger_source),
                "status": incident.status.value if hasattr(incident.status, 'value') else str(incident.status),
                "title": clean_title,
                "service": incident.service,
                "environment": incident.environment,
                "severity": incident.severity,
                "resolved_by": incident.resolved_by,
                "symptoms_json": json.dumps(clean_symptoms),
                "root_cause_category": incident.root_cause_category,
                "summary": clean_summary,
                "project": incident.project,
                "stack": incident.stack,
            }

            valid_cols = [c for c in cols if c in data_map]
            placeholders = ", ".join(["?"] * len(valid_cols))
            col_names = ", ".join(valid_cols)
            values = [data_map[c] for c in valid_cols]

            cursor.execute(f"INSERT OR REPLACE INTO incidents ({col_names}) VALUES ({placeholders})", values)
            conn.commit()
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def list_incidents(
        self,
        limit: int = 50,
        status: IncidentStatus | None = None,
        service: str | None = None,
        project: str | None = None,
    ) -> list[Incident]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions: list[str] = []
            params: list[Any] = []
            if status:
                status_val = status.value if hasattr(status, 'value') else str(status)
                conditions.append("status = ?")
                params.append(status_val)
            if service:
                conditions.append("service = ?")
                params.append(service)
            if project:
                conditions.append("project = ?")
                params.append(project)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)
            cursor.execute(
                f"SELECT * FROM incidents {where_clause} ORDER BY started_at DESC LIMIT ?",
                tuple(params),
            )
            rows = cursor.fetchall()
            return [self._row_to_incident(r) for r in rows]


    def get_active_incident(self) -> Incident | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM incidents WHERE status = ? ORDER BY started_at DESC LIMIT 1",
                (IncidentStatus.OPEN.value,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        keys = row.keys()
        trigger_val = row["trigger_source"] if "trigger_source" in keys and row["trigger_source"] else (row["trigger_type"] if "trigger_type" in keys else "manual")
        return Incident(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"] if "ended_at" in keys else None,
            trigger_source=TriggerSource(trigger_val) if trigger_val in [t.value for t in TriggerSource] else TriggerSource.MANUAL,
            status=IncidentStatus(row["status"]) if row["status"] in [s.value for s in IncidentStatus] else IncidentStatus.OPEN,
            title=row["title"],
            service=row["service"],
            environment=row["environment"],
            severity=row["severity"],
            resolved_by=row["resolved_by"],
            symptoms=json.loads(row["symptoms_json"] or "[]") if "symptoms_json" in keys else [],
            root_cause_category=row["root_cause_category"] if "root_cause_category" in keys and row["root_cause_category"] else "Unknown",
            summary=row["summary"] if "summary" in keys and row["summary"] else "",
            project=row["project"] if "project" in keys and row["project"] else "default",
            stack=row["stack"] if "stack" in keys and row["stack"] else "general",
        )

    # --- Events (Captured Commands) ---

    def save_event(self, event: Event) -> Event:
        # Lowest practical persistence boundary: verify caller did not bypass sanitization
        cmd = getattr(event, "raw_command", "") or getattr(event, "command", "") or ""
        out = getattr(event, "stdout_snippet", "") or getattr(event, "stdout_summary", "") or ""
        err = getattr(event, "stderr_snippet", "") or getattr(event, "stderr_summary", "") or ""
        if not self.sanitizer.redactor.validate_clean(cmd) or \
           not self.sanitizer.redactor.validate_clean(out) or \
           not self.sanitizer.redactor.validate_clean(err):
            raise SecurityBoundaryViolation(
                "Security Boundary Violation: Database layer rejected unredacted event containing raw secrets. "
                "The database layer does not blindly trust callers; all inputs must pass through EventSanitizer."
            )

        # Architectural Security Boundary: In-memory sanitization & field-level encryption
        event = self.sanitizer.sanitize_event(event)
        enc_command = self.crypto.encrypt(event.raw_command or event.command_redacted)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(events)")
            cols = [row["name"] for row in cursor.fetchall()]

            data_map: dict[str, Any] = {
                "id": event.id,
                "incident_id": event.incident_id,
                "schema_version": event.schema_version,
                "timestamp": event.timestamp.isoformat(),
                "raw_command": enc_command,
                "command_redacted": enc_command,
                "exit_code": event.exit_code,
                "stdout_snippet": event.stdout_snippet or event.stdout_summary,
                "stderr_snippet": event.stderr_snippet or event.stderr_summary,
                "signal_weight": event.signal_weight if event.signal_weight is not None else event.causal_score,
                "causal_score": event.signal_weight if event.signal_weight is not None else event.causal_score,
                "classification": event.classification.value if hasattr(event.classification, 'value') else str(event.classification),
                "status": event.classification.value if hasattr(event.classification, 'value') else str(event.classification),
                "duration_ms": event.duration_ms,
                "cwd": event.cwd,
                "tool_category": event.tool_category,
                "sequence_idx": event.sequence_idx,
                "project": event.project,
                "stack": event.stack,
            }

            valid_cols = [c for c in cols if c in data_map]
            placeholders = ", ".join(["?"] * len(valid_cols))
            col_names = ", ".join(valid_cols)
            values = [data_map[c] for c in valid_cols]

            cursor.execute(f"INSERT OR REPLACE INTO events ({col_names}) VALUES ({placeholders})", values)
            conn.commit()
        return event

    def get_events_for_incident(self, incident_id: str) -> list[Event]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM events WHERE incident_id = ? ORDER BY timestamp ASC", (incident_id,)
            )
            rows = cursor.fetchall()
            events: list[Event] = []
            for r in rows:
                raw_field = r["raw_command"] if "raw_command" in r.keys() else r["command_redacted"]
                try:
                    dec_cmd = self.crypto.decrypt(raw_field)
                except Exception:
                    dec_cmd = raw_field

                events.append(
                    Event(
                        schema_version=r["schema_version"] if "schema_version" in r.keys() and r["schema_version"] else "1.0",
                        id=r["id"],
                        incident_id=r["incident_id"],
                        timestamp=r["timestamp"],
                        raw_command=dec_cmd,
                        exit_code=r["exit_code"],
                        stdout_snippet=r["stdout_snippet"] if "stdout_snippet" in r.keys() and r["stdout_snippet"] else (r["stdout_summary"] if "stdout_summary" in r.keys() else ""),
                        stderr_snippet=r["stderr_snippet"] if "stderr_snippet" in r.keys() and r["stderr_snippet"] else (r["stderr_summary"] if "stderr_summary" in r.keys() else ""),
                        signal_weight=r["signal_weight"] if "signal_weight" in r.keys() else r["causal_score"],
                        classification=EventClassification(r["classification"]) if "classification" in r.keys() and r["classification"] in [c.value for c in EventClassification] else EventClassification.UNKNOWN,
                        duration_ms=r["duration_ms"],
                        cwd=r["cwd"] if "cwd" in r.keys() and r["cwd"] else "",
                        tool_category=r["tool_category"] if "tool_category" in r.keys() else "system",
                        sequence_idx=r["sequence_idx"] if "sequence_idx" in r.keys() and r["sequence_idx"] is not None else 0,
                        project=r["project"] if "project" in r.keys() and r["project"] else "default",
                        stack=r["stack"] if "stack" in r.keys() and r["stack"] else "general",
                    )
                )
            return events

    # --- State Snapshots ---

    def save_state_snapshot(self, snap: StateSnapshot) -> StateSnapshot:
        # Lowest practical persistence boundary: verify no unredacted secrets in status or diff
        if not self.sanitizer.redactor.validate_clean(snap.status_summary or "") or \
           not self.sanitizer.redactor.validate_clean(snap.diff_summary or ""):
            raise SecurityBoundaryViolation(
                "Security Boundary Violation: Database layer rejected unredacted state snapshot containing raw secrets."
            )

        # Sanitize before and after state dictionaries
        safe_before, _ = redact_structure(snap.before_state or snap.raw_state) if (snap.before_state or snap.raw_state) else (None, [])
        safe_after, _ = redact_structure(snap.after_state) if snap.after_state else (None, [])
        safe_summary = redact_text(snap.status_summary or "")
        safe_diff = redact_text(snap.diff_summary or "")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(state_snapshots)")
            cols = [row["name"] for row in cursor.fetchall()]

            data_map: dict[str, Any] = {
                "id": snap.id,
                "incident_id": snap.incident_id,
                "event_id": snap.event_id,
                "resource_type": snap.resource_type,
                "before_state_json": json.dumps(safe_before),
                "after_state_json": json.dumps(safe_after),
                "diff_summary": safe_diff,
                "is_healthy": 1 if snap.is_healthy else 0,
                "status_summary": safe_summary,
                "timestamp": snap.timestamp.isoformat() if hasattr(snap, 'timestamp') else datetime.now(timezone.utc).isoformat(),
            }

            valid_cols = [c for c in cols if c in data_map]
            placeholders = ", ".join(["?"] * len(valid_cols))
            col_names = ", ".join(valid_cols)
            values = [data_map[c] for c in valid_cols]

            cursor.execute(f"INSERT OR REPLACE INTO state_snapshots ({col_names}) VALUES ({placeholders})", values)
            conn.commit()
        return snap

    save_snapshot = save_state_snapshot

    def get_snapshots_for_incident(self, incident_id: str) -> list[StateSnapshot]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM state_snapshots WHERE incident_id = ?", (incident_id,))
            rows = cursor.fetchall()
            return [
                StateSnapshot(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    event_id=r["event_id"],
                    resource_type=r["resource_type"] if "resource_type" in r.keys() else "k8s_pod",
                    before_state=(json.loads(r["before_state_json"] or "{}") or {}) if "before_state_json" in r.keys() else {},
                    after_state=(json.loads(r["after_state_json"] or "{}") or {}) if "after_state_json" in r.keys() else {},
                    diff_summary=r["diff_summary"] if "diff_summary" in r.keys() and r["diff_summary"] else "",
                    is_healthy=bool(r["is_healthy"]),
                    status_summary=r["status_summary"] if "status_summary" in r.keys() and r["status_summary"] else "",
                )
                for r in rows
            ]

    # --- Evidence ---

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence (
                    id, incident_id, event_id, evidence_type, summary, verified, timestamp, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.incident_id,
                    evidence.event_id,
                    evidence.evidence_type,
                    evidence.summary,
                    1 if evidence.verified else 0,
                    evidence.timestamp.isoformat() if hasattr(evidence.timestamp, 'isoformat') else str(evidence.timestamp),
                    json.dumps(evidence.raw_payload),
                ),
            )
            conn.commit()
        return evidence

    def get_evidence_for_incident(self, incident_id: str) -> list[Evidence]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE incident_id = ? ORDER BY timestamp ASC", (incident_id,))
            rows = cursor.fetchall()
            return [
                Evidence(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    event_id=r["event_id"],
                    evidence_type=r["evidence_type"],
                    summary=r["summary"],
                    verified=bool(r["verified"]),
                    timestamp=r["timestamp"],
                    raw_payload=json.loads(r["raw_payload_json"] or "{}"),
                )
                for r in rows
            ]

    def list_evidence(self) -> list[Evidence]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            return [
                Evidence(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    event_id=r["event_id"],
                    evidence_type=r["evidence_type"],
                    summary=r["summary"],
                    verified=bool(r["verified"]),
                    timestamp=r["timestamp"],
                    raw_payload=json.loads(r["raw_payload_json"] or "{}"),
                )
                for r in rows
            ]

    # --- Causal Chains ---

    def save_causal_chain(self, chain: CausalChain) -> CausalChain:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(causal_chains)")
            cols = [row["name"] for row in cursor.fetchall()]

            data_map: dict[str, Any] = {
                "id": chain.id,
                "incident_id": chain.incident_id,
                "symptom": chain.symptom,
                "hypothesis": chain.hypothesis,
                "evidence_event_ids_json": json.dumps(chain.evidence_event_ids),
                "fix_event_ids_json": json.dumps(chain.fix_event_ids),
                "outcome": chain.outcome.value if hasattr(chain.outcome, 'value') else str(chain.outcome),
                "confidence_score": chain.confidence_score,
                "recovery_time_seconds": chain.recovery_time_seconds,
                "why_why_not_json": json.dumps(chain.why_why_not.model_dump() if chain.why_why_not else {}),
                "evidence_json": json.dumps([e.model_dump() for e in chain.evidence_items], default=str),
                "ranked_hypotheses_json": json.dumps([h.model_dump() for h in chain.ranked_hypotheses]),
                "disambiguation_required": 1 if chain.disambiguation_required else 0,
            }

            valid_cols = [c for c in cols if c in data_map]
            placeholders = ", ".join(["?"] * len(valid_cols))
            col_names = ", ".join(valid_cols)
            values = [data_map[c] for c in valid_cols]

            cursor.execute(f"INSERT OR REPLACE INTO causal_chains ({col_names}) VALUES ({placeholders})", values)
            conn.commit()
        return chain

    def get_causal_chains_for_incident(self, incident_id: str) -> list[CausalChain]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM causal_chains WHERE incident_id = ?", (incident_id,))
            rows = cursor.fetchall()
            chains: list[CausalChain] = []
            for r in rows:
                keys = r.keys()
                wwn_raw = json.loads(r["why_why_not_json"]) if "why_why_not_json" in keys and r["why_why_not_json"] else None
                wwn = WhyWhyNot(**wwn_raw) if wwn_raw else None
                ev_raw = json.loads(r["evidence_json"]) if "evidence_json" in keys and r["evidence_json"] else []
                ev_items = [Evidence(**item) for item in ev_raw] if ev_raw else []
                ranked_h_raw = json.loads(r["ranked_hypotheses_json"]) if "ranked_hypotheses_json" in keys and r["ranked_hypotheses_json"] else []
                ranked_h = [RankedHypothesis(**h) for h in ranked_h_raw] if ranked_h_raw else []
                disamb_req = bool(r["disambiguation_required"]) if "disambiguation_required" in keys and r["disambiguation_required"] else False
                chains.append(
                    CausalChain(
                        id=r["id"],
                        incident_id=r["incident_id"],
                        symptom=r["symptom"],
                        hypothesis=r["hypothesis"],
                        evidence_event_ids=json.loads(r["evidence_event_ids_json"] or "[]"),
                        fix_event_ids=json.loads(r["fix_event_ids_json"] or "[]"),
                        outcome=ChainOutcome(r["outcome"]) if r["outcome"] in [o.value for o in ChainOutcome] else ChainOutcome.SUCCESS,
                        confidence_score=r["confidence_score"],
                        recovery_time_seconds=r["recovery_time_seconds"],
                        evidence_items=ev_items,
                        why_why_not=wwn,
                        ranked_hypotheses=ranked_h,
                        disambiguation_required=disamb_req,
                    )
                )
            return chains

    # --- Runbooks ---

    def save_runbook(self, runbook: Runbook) -> Runbook:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(runbooks)")
            cols = [row["name"] for row in cursor.fetchall()]

            now_iso = datetime.now(timezone.utc).isoformat()
            data_map: dict[str, Any] = {
                "id": runbook.id,
                "causal_chain_id": runbook.causal_chain_id,
                "title": runbook.title,
                "root_cause_category": runbook.root_cause_category,
                "steps_json": json.dumps([s.model_dump() for s in runbook.steps], default=str),
                "success_count": runbook.success_count,
                "failure_count": runbook.failure_count,
                "total_incidents_recorded": runbook.success_count + runbook.failure_count,
                "successful_resolutions": runbook.success_count,
                "escalations_required": runbook.failure_count,
                "confidence_score": runbook.confidence_score,
                "earned_confidence_score": runbook.earned_confidence_score or runbook.confidence_score,
                "confidence_level": runbook.confidence_level.value if hasattr(runbook.confidence_level, 'value') else str(runbook.confidence_level),
                "knowledge_status": runbook.knowledge_status.value if hasattr(runbook.knowledge_status, 'value') else str(runbook.knowledge_status),
                "version": runbook.version,
                "last_matched_at": runbook.last_matched_at.isoformat() if hasattr(runbook, 'last_matched_at') else now_iso,
                "service": runbook.service,
                "symptom_signature": runbook.symptom_signature,
                "negative_knowledge_json": json.dumps([d.model_dump() for d in runbook.negative_knowledge_dead_ends], default=str),
                "verification_commands_json": json.dumps(runbook.verification_commands, default=str),
                "rollback_steps_json": json.dumps([r.model_dump() for r in runbook.rollback_steps], default=str),
                "why_why_not_json": json.dumps(runbook.why_why_not.model_dump() if runbook.why_why_not else {}),
                "evidence_citations_json": json.dumps(runbook.evidence_citations),
                "provenance_json": json.dumps(runbook.provenance.model_dump(), default=str) if hasattr(runbook, 'provenance') else "{}",
                "created_at": runbook.created_at.isoformat() if hasattr(runbook, 'created_at') else now_iso,
                "updated_at": runbook.updated_at.isoformat() if hasattr(runbook, 'updated_at') else now_iso,
                "project": runbook.project,
                "stack": runbook.stack,
            }

            valid_cols = [c for c in cols if c in data_map]
            placeholders = ", ".join(["?"] * len(valid_cols))
            col_names = ", ".join(valid_cols)
            values = [data_map[c] for c in valid_cols]

            cursor.execute(f"INSERT OR REPLACE INTO runbooks ({col_names}) VALUES ({placeholders})", values)
            conn.commit()
        return runbook

    def list_runbooks(self, service: str | None = None, project: str | None = None) -> list[Runbook]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions: list[str] = []
            params: list[Any] = []
            if service:
                conditions.append("service = ?")
                params.append(service)
            if project:
                conditions.append("project = ?")
                params.append(project)
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor.execute(f"SELECT * FROM runbooks {where_clause} ORDER BY confidence_score DESC", tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_runbook(r) for r in rows]

    def get_runbook(self, runbook_id: str) -> Runbook | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM runbooks WHERE id = ?", (runbook_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_runbook(row)

    def _row_to_runbook(self, row: sqlite3.Row) -> Runbook:
        keys = row.keys()
        succ = (
            row["success_count"]
            if "success_count" in keys and row["success_count"] is not None
            else (row["successful_resolutions"] if "successful_resolutions" in keys and row["successful_resolutions"] is not None else 1)
        )
        fail = (
            row["failure_count"]
            if "failure_count" in keys and row["failure_count"] is not None
            else (row["escalations_required"] if "escalations_required" in keys and row["escalations_required"] is not None else 0)
        )
        total = succ + fail
        conf = succ / total if total > 0 else 0.0

        if total < 3:
            conf_display = f"Not enough data yet (N={total})"
        else:
            conf_display = f"{int(conf * 100)}% — {succ} of {total} uses"

        wwn_raw = json.loads(row["why_why_not_json"]) if "why_why_not_json" in keys and row["why_why_not_json"] else None
        wwn = WhyWhyNot(**wwn_raw) if wwn_raw else None
        ev_citations = json.loads(row["evidence_citations_json"]) if "evidence_citations_json" in keys and row["evidence_citations_json"] else []
        k_status = row["knowledge_status"] if "knowledge_status" in keys and row["knowledge_status"] else "verified"
        dead_ends = json.loads(row["negative_knowledge_json"] or "[]") if "negative_knowledge_json" in keys else []

        return Runbook(
            id=row["id"],
            causal_chain_id=row["causal_chain_id"] if "causal_chain_id" in keys else "",
            title=row["title"],
            root_cause_category=row["root_cause_category"] if "root_cause_category" in keys else "Unknown",
            steps=json.loads(row["steps_json"]) if "steps_json" in keys else [],
            success_count=succ,
            failure_count=fail,
            confidence_score=round(conf, 2),
            knowledge_status=KnowledgeStatus(k_status) if k_status in [k.value for k in KnowledgeStatus] else KnowledgeStatus.VERIFIED,
            version=row["version"] if "version" in keys else 1,
            last_matched_at=row["last_matched_at"] if "last_matched_at" in keys else datetime.now(timezone.utc),
            service=row["service"] if "service" in keys else "core-service",
            symptom_signature=row["symptom_signature"] if "symptom_signature" in keys and row["symptom_signature"] else "",
            known_dead_ends=dead_ends,
            negative_knowledge_dead_ends=dead_ends,
            verification_commands=json.loads(row["verification_commands_json"] or "[]") if "verification_commands_json" in keys else [],
            why_why_not=wwn,
            evidence_citations=ev_citations,
            confidence_display=conf_display,
            project=row["project"] if "project" in keys and row["project"] else "default",
            stack=row["stack"] if "stack" in keys and row["stack"] else "general",
        )

    # --- Signatures & Drift ---

    def save_signature(self, sig: RecurrenceSignature) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO recurrence_signatures (
                    incident_id, service, error_patterns_json, symptom_tokens_json, signature_hash
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (
                    sig.incident_id,
                    sig.service,
                    json.dumps(sig.error_patterns),
                    json.dumps(sig.symptom_tokens),
                    sig.signature_hash,
                ),
            )
            conn.commit()

    def save_drift_report(self, report: SystemicDriftReport) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO systemic_drift (
                    id, service, root_cause_category, incident_count,
                    timeline_dates_json, drift_summary, backlog_recommendation, severity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    report.id,
                    report.service,
                    report.root_cause_category,
                    report.incident_count,
                    json.dumps(report.timeline_dates),
                    report.drift_summary,
                    report.backlog_recommendation,
                    report.severity,
                ),
            )
            conn.commit()

    def list_drift_reports(self) -> list[SystemicDriftReport]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM systemic_drift ORDER BY incident_count DESC")
            rows = cursor.fetchall()
            return [
                SystemicDriftReport(
                    id=r["id"],
                    service=r["service"],
                    root_cause_category=r["root_cause_category"],
                    incident_count=r["incident_count"],
                    timeline_dates=json.loads(r["timeline_dates_json"] or "[]"),
                    drift_summary=r["drift_summary"],
                    backlog_recommendation=r["backlog_recommendation"],
                    severity=r["severity"],
                )
                for r in rows
            ]
