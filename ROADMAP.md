# OpsGenome Production Roadmap

> **OpsGenome Core Loop** is fully implemented for local incident capture, in-memory secret redaction, explainable signal-vs-noise heuristic filtering, SQLite persistence with Fernet crypto utilities, 2-call LLM causal reasoning, earned confidence scoring with cold-start damping, and intake recurrence alerting.
>
> The following capabilities represent our planned post-hackathon enterprise production roadmap.

---

## 🗺️ Future Architecture Roadmap

### 1. Enterprise Alerting & Webhook Auto-Triggering
- **Production Integration:** Native bi-directional sync with PagerDuty, Opsgenie, Datadog, and Slack Incident Management apps.
- **Auto-Capture Initiation:** Dynamic session window spawning linked to active incident Slack channels.
- *Status:* Core webhook receiver and API contract built; enterprise OAuth and webhook signing verification planned for Phase 2.

### 2. Command Burst Rate Anomaly Detector & eBPF Kernel Probe
- **Statistical Sliding Window:** Real-time sliding window monitor on daemon command streams ($> 5$ ops commands in 30s) to open candidate capture windows automatically.
- **Auto-Discard Engine:** Candidate sessions with no state change within $N$ minutes auto-expire to prevent noise pollution.
- *Status:* In-memory daemon sliding window implemented; kernel-level eBPF burst probe planned for Phase 2.

### 3. Opt-in Team Cloud Sync & Multi-Org Cryptography
- **Per-Org Envelope Encryption:** Customer-managed KMS keys (AWS KMS / GCP Cloud KMS / HashiCorp Vault) encrypting operational memories before cross-team synchronization.
- **Federated Knowledge Sharing:** Cross-cluster runbook synchronization across engineering teams with strict redaction guarantees.
- *Status:* Local field-level authenticated encryption implemented; KMS cloud sync on roadmap.

### 4. Live Shadow Mode Co-Pilot
- **In-Flight Guidance:** Real-time terminal co-pilot that watches active incident commands as they are typed, matching them against historical causal graphs to predict next optimal actions and issue instant warnings against known failed dead-ends.
- *Status:* Heuristic prototype built; real-time streaming LLM co-pilot planned for Phase 2.

### 5. Interactive SRE Flight Simulator & Replay Onboarding
- **Flight Simulator for On-Call:** Step-by-step interactive terminal replay where junior engineers step through historical high-severity outages command-by-command with expert commentary and reasoning quizzes.
- *Status:* Local terminal replay player and web visualizer implemented; collaborative team simulations on roadmap.

### 6. Terminal PTY Output Stream Capture & Multi-Cloud Connectors
- **Kubernetes Infrastructure State Collector:** **COMPLETED (Phase 1)** — Implemented in `opsgenome/watcher/k8s.py` using official Kubernetes client APIs. Inspects pod phases, container readiness (`0/1`), restart counters, `CrashLoopBackOff` failure reasons, and ConfigMap `resourceVersion` / checksum deltas to verify real cluster state mutations without trusting exit code 0 alone.
- **Terminal PTY Stream Capture (Planned / Future Enhancement):** Dedicated pseudo-terminal (PTY) session wrapper to capture sanitized stdout/stderr streams non-intrusively without relying solely on shell traps. Current OpsGenome release deliberately grounds all operational decisions on passive command capture, exit codes, execution durations, and deterministic Kubernetes resource state deltas.
- **Multi-Cloud Connectors (Phase 2):** Native connectors for AWS CloudWatch/ECS and GCP Cloud Monitoring to poll cloud infrastructure health deltas directly before and after command executions.
- *Status:* Real Kubernetes State Collector implemented and verified against live cluster; PTY stdout wrapper and multi-cloud extensions planned for Phase 2.
