# OpsGenome: Architecture & Design Specification

> **Thesis:** Operational memory engine that converts ephemeral terminal troubleshooting into deterministic, verifiable organizational knowledge.

---

## 1. System Layers & Data Flow

```
+-------------------------------------------------------------------------+
|                        1. Ingestion Boundary                            |
|  - Zsh / Bash hooks: preexec / precmd traps                             |
|  - Webhook ingestion: PagerDuty / Opsgenie / Slack incident channels    |
|  - Command Burst Anomaly Detector: triggers incident window on spike    |
+------------------------------------+------------------------------------+
                                     | (Raw session payload)
                                     v
+-------------------------------------------------------------------------+
|                        2. Fail-Closed Security Boundary                 |
|  - Multi-pattern Regex: AWS, GCP, GitHub, Slack, JWT, DB URIs, PWDs    |
|  - Shannon Entropy Scanner: high-randomness unformatted tokens          |
|  - Exception safety: fail-closed -> [REDACTED_FAIL_CLOSED_ERROR]        |
+------------------------------------+------------------------------------+
                                     | (Clean, redacted events)
                                     v
+-------------------------------------------------------------------------+
|                        3. Signal Extraction & State Diff                |
|  - Pre-filter: drop trivial commands (ls, pwd, cd, clear)              |
|  - Exit-code weighting: exit != 0 -> Negative Knowledge / Dead End      |
|  - State delta evaluation: before/after health check diffs (when given) |
|  - Recency-to-resolution decay: prioritize actions preceding recovery   |
+------------------------------------+------------------------------------+
                                     | (Correlated event graph)
                                     v
+-------------------------------------------------------------------------+
|                        4. Storage & Persistence Engine                  |
|  - Client-side redaction + Fernet crypto utility + SQLite WAL           |
|  - Normalized models: Incidents, Events, Evidence, Runbooks, Snapshots  |
|  - Sub-millisecond signature indexing for instant recurrence lookup     |
+------------------------------------+------------------------------------+
                                     | (Deterministic evidence items)
                                     v
+-------------------------------------------------------------------------+
|                        5. Deterministic Evidence & AI Engine            |
|  - Evidence Grounding Validator: Publication Verification Gate          |
|  - Evidence Provenance Engine: 6-stage continuous backward trace        |
|  - Why / Why Not Generator: records chosen fix vs rejected alternatives |
|  - Knowledge Decay Engine: evaluates VERIFIED, AGING, STALE, CONTRADICTED|
|  - Sample-Size Damped Confidence: separated from historical success rate|
+------------------------------------+------------------------------------+
                                     | (API contracts & event streams)
                                     v
+-------------------------------------------------------------------------+
|                        6. Presentation & Incident Replay UX             |
|  - FastAPI modular server (port 8765) + Frontend static server (port 3000)|
|  - 5 Consolidated Views: Overview, Incidents, Knowledge, Replay, Search |
|  - Flagship Incident Replay: 9-column audit timeline ('Git Blame')      |
|  - Linear/Apple SRE Design: #F8FAFC canvas, crisp panels, slate typography|
+-------------------------------------------------------------------------+
```

---

## 2. Core Architectural Pillars

### A. Non-Intrusive Capture Boundary
OpsGenome does not require developers or SREs to change their daily habits. Shell hooks (`preexec` and `precmd`) record command lines, working directory, exit status, and execution duration directly from standard terminal sessions (stdout/stderr capture is planned for a dedicated PTY wrapper agent). In parallel, webhook endpoints catch PagerDuty, Opsgenie, and Slack alerts to bind commands directly to active incident IDs.

### B. Fail-Closed Security Isolation
Operational telemetry contains credentials by nature (connection strings, tokens, bearer headers). OpsGenome guarantees that:
- Redaction executes **in-memory before disk or network persistence**.
- Vendor patterns and Shannon entropy checks run concurrently.
- If any regex engine or parser throws an unexpected exception, the redaction handler fails closed, replacing the block with `[REDACTED_FAIL_CLOSED_ERROR]`.

### C. State-Transition Evaluation (No "Exit Code 0" Fallacy)
A script that returns exit code `0` is frequently not the fix (e.g., restarting a service whose underlying database is saturated). OpsGenome pairs commands with pre- and post-execution state snapshots captured via its live Kubernetes State Collector (`opsgenome/watcher/k8s.py`) or telemetry payloads. The collector connects to the cluster API using the official Kubernetes client to poll pod phases, `0/1` container readiness, restart counters, failure reasons (`CrashLoopBackOff`, `Error`, `OOMKilled`), and ConfigMap `resourceVersion` / checksum deltas. Only actions that produce a verified positive state delta are promoted to verified fix steps, while commands returning exit code `0` without restoring health are archived as Known Dead Ends. Collector connections fail visibly with specific typed exceptions (`K8sClusterUnreachableError`, `K8sNamespaceNotFoundError`, `K8sPermissionDeniedError`), never silently returning synthetic data.

### D. Why / Why Not Decision Model
For every synthesized runbook, OpsGenome captures the alternative hypotheses investigated by engineers and explains why they were ruled out. This forms an immutable audit trail that defends the chosen remediation against naive regressions.

### E. Knowledge Decay Lifecycle
Runbooks are living artifacts. OpsGenome computes an automated knowledge status for every operational memory:
- **`VERIFIED`** ($\le 30$ days, confirmed by successful state delta).
- **`AGING`** ($30 - 60$ days, no recent verification).
- **`STALE`** ($> 60$ days, flagged for validation).
- **`CONTRADICTED`** (invalidated by an incident where the step was executed but failed to recover the service).

---

## 3. Storage Model Specification

The local database uses SQLite with WAL (Write-Ahead Logging) mode enabled, matching `opsgenome/storage/db.py`:

```sql
-- Core Incident Model
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
    symptoms_json TEXT,
    root_cause_category TEXT,
    summary TEXT
);

-- Captured Terminal Events
CREATE TABLE events (
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
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

-- State Snapshots
CREATE TABLE state_snapshots (
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
);

-- Causal Chains
CREATE TABLE causal_chains (
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
);

-- Versioned Runbooks
CREATE TABLE runbooks (
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
    FOREIGN KEY(causal_chain_id) REFERENCES causal_chains(id)
);
```

---

## 4. Scalability & Hosted Roadmap

| Layer | Local MVP (Built) | Hosted Enterprise Target |
| :--- | :--- | :--- |
| **Storage** | SQLite with WAL & client-side secret redaction | Distributed PostgreSQL + TimescaleDB |
| **Vector Index** | Deterministic token signature hashing | pgvector + HNSW index embeddings |
| **Capture Agent**| Python shell hooks (`preexec`/`precmd`) | Lightweight Go/eBPF daemon with offline queue |
| **Auth & Access**| Localhost origin isolation | OIDC / SAML SSO with team-level RBAC |
| **Redaction Throughput** | 42,020 ops/sec (in-memory) | 500,000+ events/sec distributed pipeline |
