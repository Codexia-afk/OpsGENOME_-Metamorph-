# 🧬 OpsGenome — Comprehensive Error Dictionary & Diagnostic Guide

> **Quick Reference**: When an error, crash, or unexpected behavior occurs in OpsGenome, use this document to locate the exact source file and line, understand why the condition was triggered, and execute the verified remediation steps.

---

## Table of Contents
1. [Diagnostic Flowchart](#1-diagnostic-flowchart)
2. [Master Error & Exception Matrix](#2-master-error--exception-matrix)
3. [Domain 1: Kubernetes Watcher & Cluster State Collector](#3-domain-1-kubernetes-watcher--cluster-state-collector)
4. [Domain 2: Security Boundary & Secret Redaction Guardrails](#4-domain-2-security-boundary--secret-redaction-guardrails)
5. [Domain 3: Unix Domain Socket IPC & Client Transport](#5-domain-3-unix-domain-socket-ipc--client-transport)
6. [Domain 4: AI Reasoning Engine & Grounding Gate](#6-domain-4-ai-reasoning-engine--grounding-gate)
7. [Domain 5: SQLite Database & Storage Engine](#7-domain-5-sqlite-database--storage-engine)
8. [Domain 6: Shell Integration Hooks & Anomaly Detector](#8-domain-6-shell-integration-hooks--anomaly-detector)
9. [Automated System Diagnostics (`opsgenome doctor`)](#9-automated-system-diagnostics-opsgenome-doctor)

---

## 1. Diagnostic Flowchart

```
What symptom are you observing?
│
├── 🔴 "Failed to connect to Kubernetes cluster" or "K8sClusterUnreachableError"
│   └── Go to Domain 1: Check minikube status, kubeconfig context, and cluster IP.
│
├── 🔴 "SecurityBoundaryViolation: Sanitization post-validation failed"
│   └── Go to Domain 2: Unredacted secret detected. Inspect payload or custom patterns.
│
├── 🔴 "status: daemon_socket_unavailable" or terminal commands not being recorded
│   └── Go to Domain 3: Start daemon (`opsgenome daemon`), inspect ~/.opsgenome/daemon.sock permissions.
│
├── 🟡 Runbook says "Ambiguous / Multi-Candidate Remediation" (outcome: "inconclusive")
│   └── Go to Domain 4: Normal AI safety behavior! Multiple mutations occurred; supply Anthropic API key.
│
├── 🔴 "OperationalError: database is locked"
│   └── Go to Domain 5: Check for lingering CLI processes holding exclusive SQLite locks.
│
└── 🟡 Running a full system checkup
    └── Run `opsgenome doctor` in your terminal for automated verification.
```

---

## 2. Master Error & Exception Matrix

| Error / Exception | File Location | Root Cause ("Why it comes") | Quick Fix ("How to fix") |
| :--- | :--- | :--- | :--- |
| `K8sClusterUnreachableError` | [`opsgenome/watcher/k8s.py:34`](opsgenome/watcher/k8s.py#L34) | API server offline, dead VM, or invalid kubeconfig context | `minikube start` or update `~/.kube/config` |
| `K8sNamespaceNotFoundError` | [`opsgenome/watcher/k8s.py:39`](opsgenome/watcher/k8s.py#L39) | Target namespace does not exist in cluster | `kubectl create namespace <ns>` |
| `K8sPermissionDeniedError` | [`opsgenome/watcher/k8s.py:44`](opsgenome/watcher/k8s.py#L44) | ServiceAccount/Role lacks `list` pods/configmaps | Grant RBAC `ClusterRole` or namespace permissions |
| `SecurityBoundaryViolation` | [`opsgenome/security/redactor.py:306`](opsgenome/security/redactor.py#L306) | Unredacted secret detected in payload | Pass input through `EventSanitizer` before storage |
| `[REDACTED_FAIL_CLOSED_ERROR]` | [`opsgenome/security/redactor.py:303`](opsgenome/security/redactor.py#L303) | Redactor encountered unexpected parsing exception | Inspect nested payload structure |
| `daemon_socket_unavailable` | [`opsgenome/cli/client.py:59`](opsgenome/cli/client.py#L59) | Daemon is not running or socket path is invalid | Run `opsgenome daemon` |
| `Socket Permission Denied` | [`opsgenome/cli/main.py:246`](opsgenome/cli/main.py#L246) | Socket file permissions changed from `0600` | Run `chmod 600 ~/.opsgenome/daemon.sock` |
| `Address already in use` | [`opsgenome/cli/main.py:230`](opsgenome/cli/main.py#L230) | Stale socket file remains from killed daemon | Delete stale socket: `rm -f ~/.opsgenome/daemon.sock` |
| `outcome="inconclusive"` | [`opsgenome/ai/engine.py:322`](opsgenome/ai/engine.py#L322) | Multiple mutations executed before recovery | Normal safety state. Enable Claude for disambiguation |
| `outcome="insufficient_data"` | [`opsgenome/ai/engine.py:306`](opsgenome/ai/engine.py#L306) | Fewer than 2 high-signal events captured | Capture diagnostic commands during incident |
| `Publication Gate Block` | [`opsgenome/ai/grounding.py:101`](opsgenome/ai/grounding.py#L101) | Claim references non-existent or cross-incident ID | Provenance filter blocked hallucinated output |
| `OperationalError: database is locked` | [`opsgenome/storage/db.py:70`](opsgenome/storage/db.py#L70) | Concurrent write or uncommitted transaction | Terminate stale processes locking SQLite DB |
| `no such column: ranked_hypotheses_json` | [`opsgenome/storage/db.py:95`](opsgenome/storage/db.py#L95) | Database initialized before migration | Auto-migrated by DatabaseManager on next startup |

---

## 3. Domain 1: Kubernetes Watcher & Cluster State Collector

### 1.1 `K8sClusterUnreachableError`
* **Where it originates**:
  - Definition: [`opsgenome/watcher/k8s.py:34`](opsgenome/watcher/k8s.py#L34)
  - Raised at: Lines 85, 95, 105, 119, 123, 192, 194, 217, 219
* **Why the error comes**:
  OpsGenome uses the official Python `kubernetes` client to query the real API server (e.g. `https://192.168.64.2:8443`). This exception is raised when:
  1. The local Minikube or Kind cluster is stopped or paused.
  2. The kubeconfig file at `~/.kube/config` is missing or contains an invalid active context.
  3. The API server URL/certificate does not match or times out.
* **How to diagnose**:
  ```bash
  # Check if Kubernetes is responding
  kubectl cluster-info
  
  # Check Minikube status
  minikube status
  ```
* **How to fix**:
  ```bash
  # 1. Start Minikube or Kind
  minikube start
  
  # 2. Verify current context points to your cluster
  kubectl config current-context
  
  # 3. Test cluster reachability using Python collector
  python3 -c "from opsgenome.watcher.k8s import K8sCollector; print(K8sCollector().check_cluster_health())"
  ```
* **Verification**:
  ```bash
  pytest opsgenome/tests/test_k8s_collector_integration.py -v
  ```

---

### 1.2 `K8sNamespaceNotFoundError`
* **Where it originates**:
  - Definition: [`opsgenome/watcher/k8s.py:39`](opsgenome/watcher/k8s.py#L39)
  - Raised at: Line 111
* **Why the error comes**:
  The collector was initialized with a namespace (e.g. `K8sCollector(namespace="payments")`), but that namespace does not exist in the active cluster.
* **How to diagnose**:
  ```bash
  kubectl get namespaces
  ```
* **How to fix**:
  ```bash
  # Create the missing target namespace
  kubectl create namespace payments
  ```
* **Verification**:
  ```bash
  python3 -c "from opsgenome.watcher.k8s import K8sCollector; c = K8sCollector(namespace='payments'); print('Namespace exists:', c.check_cluster_health()['healthy'])"
  ```

---

### 1.3 `K8sPermissionDeniedError`
* **Where it originates**:
  - Definition: [`opsgenome/watcher/k8s.py:44`](opsgenome/watcher/k8s.py#L44)
  - Raised at: Lines 115, 191, 216
* **Why the error comes**:
  The active credentials in `~/.kube/config` (or in-cluster ServiceAccount token) returned an HTTP `403 Forbidden` when attempting to list Pods or ConfigMaps in the target namespace.
* **How to diagnose**:
  ```bash
  kubectl auth can-i list pods -n payments
  kubectl auth can-i list configmaps -n payments
  ```
* **How to fix**:
  Grant the required read-only RBAC permissions to the service account or user:
  ```yaml
  apiVersion: rbac.authorization.k8s.io/v1
  kind: Role
  metadata:
    namespace: payments
    name: opsgenome-reader
  rules:
  - apiGroups: [""]
    resources: ["pods", "configmaps"]
    verbs: ["get", "list"]
  ```
  Apply with:
  ```bash
  kubectl apply -f role.yaml
  ```

---

## 4. Domain 2: Security Boundary & Secret Redaction Guardrails

### 2.1 `SecurityBoundaryViolation`
* **Where it originates**:
  - Definition: [`opsgenome/security/redactor.py:306`](opsgenome/security/redactor.py#L306)
  - Enforced in Redactor: Lines 368, 372
  - Enforced in Storage: [`opsgenome/storage/db.py:275, 395, 478`](opsgenome/storage/db.py#L275)
* **Why the error comes**:
  OpsGenome implements a **fail-closed architectural security boundary**. If any captured command, environment variable, or snapshot payload contains an unredacted secret (such as an AWS Access Key `AKIA...`, Bearer Token, JWT, or database password) when calling `db.save_event()` or `db.create_incident()`, the database refuses to write and raises `SecurityBoundaryViolation`.
* **How to diagnose**:
  Inspect the error message. It will specify which field failed:
  ```text
  SecurityBoundaryViolation: Security Boundary Violation: Database layer rejected unredacted event containing raw secrets. Untrusted input must pass through EventSanitizer.
  ```
* **How to fix**:
  Never pass raw strings directly to storage. Always run them through `EventSanitizer` or `SecretRedactor`:
  ```python
  from opsgenome.security.redactor import EventSanitizer
  
  sanitizer = EventSanitizer()
  safe_event = sanitizer.sanitize_event(untrusted_event)
  db.save_event(safe_event)
  ```
* **Verification**:
  ```bash
  pytest opsgenome/tests/test_adversarial_security_boundary.py -v
  ```

---

### 2.2 `[REDACTED_FAIL_CLOSED_ERROR]`
* **Where it originates**:
  - Defined in: [`opsgenome/security/redactor.py:303`](opsgenome/security/redactor.py#L303)
* **Why the error comes**:
  When redacting nested data structures (e.g. recursive dictionaries or lists in Kubernetes state snapshots), if an object exceeds maximum recursion depth (>20 levels) or raises an unexpected parsing error, OpsGenome replaces the entire branch with `"[REDACTED_FAIL_CLOSED_ERROR]"` rather than risking unredacted credential leakage.
* **How to fix**:
  Ensure state snapshot metadata is valid JSON-serializable structures without circular references.

---

## 5. Domain 3: Unix Domain Socket IPC & Client Transport

### 5.1 `status: "daemon_socket_unavailable"`
* **Where it originates**:
  - Code: [`opsgenome/cli/client.py:59`](opsgenome/cli/client.py#L59)
* **Why the error comes**:
  When terminal hooks attempt to dispatch an executed command to the daemon, the Unix domain socket at `~/.opsgenome/daemon.sock` does not exist on disk.
* **How to diagnose**:
  ```bash
  ls -la ~/.opsgenome/daemon.sock
  ```
* **How to fix**:
  Start the OpsGenome daemon in a terminal or background process:
  ```bash
  opsgenome daemon
  ```
  Or if running on a custom socket:
  ```bash
  export OPSGENOME_SOCKET_PATH="/tmp/custom_opsgenome.sock"
  opsgenome daemon --socket-path "$OPSGENOME_SOCKET_PATH"
  ```
* **Verification**:
  ```bash
  pytest opsgenome/tests/test_client_redaction_socket.py -v
  ```

---

### 5.2 Stale Socket File ("Address already in use")
* **Where it originates**:
  - Code: [`opsgenome/cli/main.py:230`](opsgenome/cli/main.py#L230)
* **Why the error comes**:
  A previous daemon process was terminated abruptly (e.g. `kill -9`), leaving behind the dead socket file `~/.opsgenome/daemon.sock`.
* **How to fix**:
  OpsGenome's startup script automatically detects dead sockets, but you can manually clean it:
  ```bash
  rm -f ~/.opsgenome/daemon.sock
  opsgenome daemon
  ```

---

### 5.3 Socket Permission Denied (Not `0600`)
* **Where it originates**:
  - Code: [`opsgenome/cli/main.py:246`](opsgenome/cli/main.py#L246)
* **Why the error comes**:
  To protect captured operational commands from other local users on a multi-user machine, OpsGenome strictly sets socket permissions to `0600` (read/write only by the socket owner). If permissions were modified or another user attempts to connect, the OS will reject the socket connection.
* **How to fix**:
  ```bash
  chmod 600 ~/.opsgenome/daemon.sock
  ```

---

## 6. Domain 4: AI Reasoning Engine & Grounding Gate

### 6.1 Ambiguous Multi-Candidate State (`outcome="inconclusive"`)
* **Where it originates**:
  - Code: [`opsgenome/ai/engine.py:311-324`](opsgenome/ai/engine.py#L311-L324)
* **Why it occurs**:
  This is **not a bug** — it is an intentional safety feature! When multiple candidate mutations (e.g. `kubectl rollout undo` AND `kubectl set env`) occurred before recovery, deterministic heuristic layers refuse to guess. The engine flags `disambiguation_required=True` and `outcome="inconclusive"`.
* **How to fix**:
  1. **Option A: With Anthropic Claude API (Semantic Disambiguation)**:
     Set your API key so Claude can analyze the temporal APM telemetry:
     ```bash
     export ANTHROPIC_API_KEY="sk-ant-..."
     ```
  2. **Option B: Offline Mode**:
     OpsGenome will automatically generate an honest conditional triage runbook ("Manual Triage Required — Ambiguous Candidates") without hallucinating a false single cause.
* **Verification**:
  ```bash
  python3 demo/simulate_ambiguous_incident.py
  ```

---

### 6.2 Insufficient Data (`outcome="insufficient_data"`)
* **Where it originates**:
  - Code: [`opsgenome/ai/engine.py:297-308`](opsgenome/ai/engine.py#L297-L308)
* **Why it occurs**:
  Fewer than 2 qualifying operational events were captured during the incident session, and no remediation mutation was observed. OpsGenome refuses to hallucinate a root cause from thin air.
* **How to fix**:
  Ensure commands are executed during an active incident window (`opsgenome start-incident <title>`), or manually associate diagnostic commands before resolving.

---

### 6.3 Grounding Gate Publication Rejection
* **Where it originates**:
  - Code: [`opsgenome/ai/grounding.py:93-136`](opsgenome/ai/grounding.py#L93-L136)
* **Why it occurs**:
  An AI-generated runbook claim referenced an evidence ID that:
  1. Does not exist in the evidence store (`rejection_reason="Evidence ID ... does not exist in store (hallucination)"`).
  2. Belongs to a different incident (`rejection_reason="Evidence ... belongs to incident ..., not ..."`).
  3. Is unverified.
* **How the system handles it**:
  The publication gate automatically strips the unverified claim so that **no hallucinated claim leaks to the published runbook**. The metric `gate_enforcement_rate` will report `1.0` (100% blocked).

---

## 7. Domain 5: SQLite Database & Storage Engine

### 7.1 `sqlite3.OperationalError: database is locked`
* **Where it originates**:
  - Code: [`opsgenome/storage/db.py:70`](opsgenome/storage/db.py#L70)
* **Why it comes**:
  SQLite default journal mode was locked by a long-running process or simultaneous writes from multiple terminal sessions.
* **How to fix**:
  OpsGenome enables `PRAGMA journal_mode=WAL;` (Write-Ahead Logging) and `PRAGMA busy_timeout = 5000;`. If a lock still occurs:
  ```bash
  # Check for running Python processes holding the DB
  lsof ~/.opsgenome/opsgenome.db
  
  # Terminate stale process if found
  kill -9 <PID>
  ```

---

### 7.2 Missing Database Columns / Schema Migration
* **Where it originates**:
  - Code: [`opsgenome/storage/db.py:90-120`](opsgenome/storage/db.py#L90-L120)
* **Why it comes**:
  If a database file was created on an older version of OpsGenome before `ranked_hypotheses_json` or `disambiguation_required` was introduced.
* **How to fix**:
  `DatabaseManager` contains an automatic startup migration. Simply running any CLI command (e.g. `opsgenome status`) will automatically detect missing columns and execute `ALTER TABLE` to bring the database to the current schema.

---

## 8. Domain 6: Shell Integration Hooks & Anomaly Detector

### 8.1 Commands Not Appearing in Incident Session
* **Where it originates**:
  - Hooks: [`opsgenome/hooks/opsgenome.zsh`](opsgenome/hooks/opsgenome.zsh) / `opsgenome.bash`
* **Why it occurs**:
  1. The shell hooks have not been sourced in the current terminal window.
  2. The daemon socket path environment variable `OPSGENOME_SOCKET_PATH` is pointing to an invalid location.
* **How to fix**:
  ```bash
  # 1. Install hooks
  opsgenome init
  
  # 2. Source in current shell
  source ~/.zshrc    # or source ~/.bashrc
  
  # 3. Test capture manually
  opsgenome redact-and-send -c "echo 'testing opsgenome'" -e 0 -d 15
  ```

---

## 9. Automated System Diagnostics (`opsgenome doctor`)

To instantly check the health of all subsystems at once, run:

```bash
opsgenome doctor
```

### Sample Output:
```text
┌────────────────────────────────────────────────────────────────────────────┐
│ OpsGenome Doctor — System Health & Diagnostic Suite                        │
├────────────────────────────────────────────────────────────────────────────┤
│ • Daemon Socket:       ACTIVE (0600, owner matches)                        │
│ • SQLite Database:     HEALTHY (WAL mode enabled, all columns present)     │
│ • Kubernetes Cluster:  CONNECTED (payments namespace active, RBAC ok)      │
│ • Shell Integration:   INSTALLED (~/.zshrc hook active)                    │
│ • AI Reasoning Engine: READY (Offline deterministic heuristic + fallback)  │
└────────────────────────────────────────────────────────────────────────────┘
```

If any check fails, `opsgenome doctor` prints the exact section of this guide to consult for the fix.
