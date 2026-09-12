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
|  - State transition verification: pod state & HTTP response delta       |
|  - Recency-to-resolution decay: prioritize actions preceding recovery   |
+------------------------------------+------------------------------------+
                                     | (Correlated event graph)
                                     v
+-------------------------------------------------------------------------+
|                        4. Storage & Persistence Engine                  |
|  - Field-level authenticated encryption (Fernet AES/HMAC) + SQLite       |
|  - Normalized models: Incidents, Events, Evidence, Runbooks, Snapshots  |
|  - Sub-millisecond signature indexing for instant recurrence lookup     |
+------------------------------------+------------------------------------+
                                     | (Deterministic evidence items)
                                     v
+-------------------------------------------------------------------------+
|                        5. Deterministic Evidence & AI Engine            |
|  - Evidence Grounding Validator: supported claims / total claims        |
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
OpsGenome does not require developers or SREs to change their daily habits. Shell hooks (`preexec` and `precmd`) record command lines, working directory, exit status, duration, and output streams directly from standard terminal sessions. In parallel, webhook endpoints catch PagerDuty alerts to bind commands directly to active incident IDs.

### B. Fail-Closed Security Isolation
Operational telemetry contains credentials by nature (connection strings, tokens, bearer headers). OpsGenome guarantees that:
- Redaction executes **in-memory before disk or network persistence**.
- Vendor patterns and Shannon entropy checks run concurrently.
- If any regex engine or parser throws an unexpected exception, the redaction handler fails closed, replacing the block with `[REDACTED_FAIL_CLOSED_ERROR]`.

### C. State-Transition Verification (No "Exit Code 0" Fallacy)
A script that returns exit code `0` is frequently not the fix (e.g., restarting a service whose underlying database is saturated). OpsGenome pairs commands with pre- and post-execution state snapshots (HTTP latency, pod status, error rates). Only actions that produce a positive state delta are promoted to verified fix steps.

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

The local database uses SQLite with WAL (Write-Ahead Logging) mode enabled:

```sql
-- Core Incident Model
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    service TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    root_cause TEXT,
    commander TEXT
);

-- Captured Terminal Events
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    command TEXT NOT NULL,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    duration_ms REAL,
    is_noise INTEGER DEFAULT 0,
    signal_score REAL DEFAULT 0.0,
    cwd TEXT,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

-- Deterministic Evidence Records
CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_id TEXT,
    category TEXT NOT NULL, -- fact, inference, recommendation
    description TEXT NOT NULL,
    metric_name TEXT,
    before_value TEXT,
    after_value TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

-- Versioned Runbooks
CREATE TABLE runbooks (
    id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    trigger_pattern TEXT NOT NULL,
    title TEXT NOT NULL,
    steps TEXT NOT NULL, -- JSON array of verified steps
    confidence_score REAL DEFAULT 0.0,
    sample_size INTEGER DEFAULT 1,
    status TEXT DEFAULT 'VERIFIED',
    why_why_not TEXT, -- JSON structure of chosen vs ruled-out options
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

## 4. Scalability & Hosted Roadmap

| Layer | Local MVP (Built) | Hosted Enterprise Target |
| :--- | :--- | :--- |
| **Storage** | Encrypted SQLite with WAL | Distributed PostgreSQL + TimescaleDB |
| **Vector Index** | Deterministic token signature hashing | pgvector + HNSW index embeddings |
| **Capture Agent**| Python shell hooks (`preexec`/`precmd`) | Lightweight Go/eBPF daemon with offline queue |
| **Auth & Access**| Localhost origin isolation | OIDC / SAML SSO with team-level RBAC |
| **Throughput** | 42,650 ops/sec | 500,000+ events/sec distributed pipeline |
