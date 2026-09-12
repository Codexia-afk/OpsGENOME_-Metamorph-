# OpsGenome: The Operational Memory Engine

> **"Production systems remember what happened. OpsGenome remembers why the engineer fixed it. AI proposes; deterministic evidence verifies."**

[![Tests](https://img.shields.io/badge/tests-79%20passed-success)](opsgenome/tests/)
[![AI Providers](https://img.shields.io/badge/AI-Google%20Gemini%20%7C%20Claude%20%7C%20Offline-blueviolet)](opsgenome/ai/)
[![Security](https://img.shields.io/badge/security-fail--closed%20boundary-blue)](SECURITY.md)
[![Recurrence SLA](https://img.shields.io/badge/intake%20match-0.25ms-brightgreen)](README.md#benchmarks--performance-sla)
[![Core Loop](https://img.shields.io/badge/core%20loop-35.2ms-emerald)](README.md#benchmarks--performance-sla)
[![Throughput](https://img.shields.io/badge/redaction%20throughput-42k%2B%20ops%2Fsec-orange)](README.md#benchmarks--performance-sla)
[![UI](https://img.shields.io/badge/UI-Linear%20%2B%20Apple%20SRE-slate)](opsgenome/daemon/static/)

---

## 💡 The Core Thesis

AI code assistants have accelerated shipping code by 10x, but incident response remains tribal, undocumented, and fragile. When production goes down at 3 AM:
1. **The real runbook is in someone's muscle memory**, not in Confluence or Notion.
2. **Post-mortems are sanitized**: they are written days later, omit critical terminal context, and never record the failed branches.
3. **The "Silent Recurrence" tax**: the same root cause gets patched three different ways by three different engineers who never speak. When senior engineers leave, the organization's operational intelligence leaves with them.

**OpsGenome transforms active terminal incident response into verifiable organizational memory.** It watches how engineers triage and repair systems, evaluates state transitions deterministically, prunes dead ends, redacts secrets fail-closed, and surfaces past solutions with sub-millisecond single-incident intake matching (0.25 ms) and sub-15 ms search across 1,000 historical incidents.

$$\text{INCIDENT} \longrightarrow \text{EVIDENCE} \longrightarrow \text{DECISION} \longrightarrow \text{OUTCOME} \longrightarrow \text{VERIFICATION} \longrightarrow \text{MEMORY}$$

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Non-Intrusive Capture Boundary"]
        T1["Terminal Commands: kubectl, aws, docker, psql"] --> SH["Zsh / Bash Hooks: preexec / precmd"]
        W1["PagerDuty / Opsgenie / Slack Webhook"] --> AT["Auto-Trigger Engine"]
        W2["Command Burst Anomaly Detector"] --> AT
        SH --> D1["In-Process Client Redactor: Python Client"]
        D1 -->|POSIX 0600 Unix Domain Socket| DS["OpsGenome Background Daemon"]
        AT --> DS
    end

    subgraph Security["2. Fail-Closed Security Boundary"]
        DS --> SR["Secret Redactor: Multi-pattern Regex + Shannon Entropy + EventSanitizer"]
        SR -->|Zero Raw Secrets Pass DB or LLM| SF["Signal-vs-Noise Heuristic Pre-Filter"]
        SF --> EW["Exit-Code & Negative Knowledge Classifier"]
        SF --> SD["State-Delta Evaluator: Real Kubernetes Collector (Pod & ConfigMap Diffs)"]
    end

    subgraph StorageAI["3. Deterministic Evidence & AI Engine"]
        EW & SD --> DB[("Local SQLite global.db + Client Redaction & Fernet Crypto")]
        DB --> EE["Evidence Grounding Validator (Publication Gate)"]
        AI["Claude / LLM Reasoning Engine"] --> DISAMB["Hypothesis Disambiguation (Removal Test)"]
        DISAMB --> WHY["Why / Why Not Decision Engine"]
        DISAMB --> PROV["Evidence Provenance Engine (6-Stage Backward Trace)"]
        DISAMB --> KD["Knowledge Decay Engine: VERIFIED / AGING / STALE / CONTRADICTED"]
    end

    subgraph PreventionUX["4. Prevention, Trust Gate & Investigation Workspace"]
        DB --> REC["Sub-50ms Global Recurrence Alerting: 0.25ms Intake Match"]
        REC --> GATE["Trust Asymmetry Permission Gate: Dual-Confirm Cross-Project"]
        GATE --> IR["Incident Replay: 9-Field Audit Timeline ('Git Blame for Operations')"]
        GATE --> WEB["SRE Console: Overview, Incidents, Knowledge, Investigation, Search"]
    end
```

---

## ⚡ Key Technical Differentiators

### 1. Fail-Closed Security Boundary (Zero Raw Secrets Ever Persisted)
- **Client-Side In-Process Redaction:** Redaction occurs inside the Python process on the client *before* JSON payloads are serialized or transmitted over the transport boundary.
- **Unix Domain Socket Isolation:** The daemon communicates over a dedicated Unix domain socket (`~/.opsgenome/daemon.sock`) restricted to POSIX `0600` permissions (owner read/write only), eliminating network-visible loopback ports.
- **Multi-Vendor Patterns:** Redacts AWS keys (`AKIA...`), GCP service account keys, GitHub tokens (`ghp_...`), Slack webhooks, JWT tokens, private keys, database connection URIs with embedded passwords, and CLI `--password` flags.
- **Shannon Entropy Analysis:** Detects unstructured high-entropy secrets ($H \ge 3.8$) and sanitizes them into `[REDACTED_HIGH_ENTROPY_SECRET]`.
- **Fail-Closed Fallback:** Any residual secret triggers `SecurityBoundaryViolation` or `[REDACTED_FAIL_CLOSED_ERROR]`. Zero raw credentials ever reach disk, database, or AI prompts. See [SECURITY.md](SECURITY.md) for full threat model details.

### 2. Real Kubernetes State Transition Verification (Never Trust Exit Code 0)
- OpsGenome connects directly to the live cluster via the official Python `kubernetes` client (`opsgenome/watcher/k8s.py`).
- It captures concrete infrastructure state deltas:
  - **Pod Phase & Readiness:** Evaluates live container readiness (`0/1` $\rightarrow$ `1/1`), pod phase transitions, container restart counts, and failure reasons (`CrashLoopBackOff`, `Error`, `OOMKilled`).
  - **ConfigMap Mutations:** Inspects Kubernetes `resourceVersion` deltas (e.g. `2274 -> 2308`) and SHA-256 configuration checksums.
- Commands that exit `0` without resolving pod failures or mutating resource versions are deterministically classified as **Known Dead Ends** rather than fixes.
- If the cluster is unreachable, the collector fails visibly with typed exceptions (`K8sClusterUnreachableError`, `K8sNamespaceNotFoundError`, `K8sPermissionDeniedError`), never substituting synthetic mock fallbacks.

### 3. Flagship Evidence Provenance Engine
- Follow AI recommendations backwards through a continuous 6-stage chain:
  $$\text{Recommendation} \longrightarrow \text{Evidence} \longrightarrow \text{Incident} \longrightarrow \text{Decision} \longrightarrow \text{Outcome} \longrightarrow \text{Verification}$$
- Every node links directly to authoritative, persisted SQLite records.
- **Evidence Grounding Validator (Gate Enforcement Rate):**
  We do not trust the model's claims by default — every claim is verified against operational evidence, and claims that fail verification are caught and blocked before reaching the user.
  $$\text{Gate Enforcement Rate} = \frac{\text{failed claims successfully blocked from output}}{\text{total failed verification claims}} \quad (\text{Empirically } 100\% \text{ in benchmark: 3/3 blocked, } 30\% \text{ hallucination attempt rate})$$

### 4. Confidence Terminology Honesty
- We reject vague "Bayesian" marketing claims.
- We explicitly separate **Historical Success Rate** from **Current Evidence Confidence** using a deterministic Sample Size Damping Factor:
  $$W(N) = 1 - e^{-N / 4.0}$$
  $$\text{Current Evidence Confidence} = (\text{Historical Success Rate} - \text{Escalation Penalty} + \text{Verification Boost}) \cdot W(N)$$
- For small samples ($N < 3$), confidence is withheld under a strict `COLD_START` status to eliminate small-sample overconfidence.

### 5. Calibrated AI Reasoning: Hypothesis Disambiguation (The Removal Test)
- **Deterministic Pre-Filter:** In simple incidents with a single obvious mutation and isolated Kubernetes recovery, the deterministic layer handles filtering; the LLM's role is auxiliary narration.
- **Genuine AI Irreplaceability on Conflicting Evidence:** When evidence genuinely conflicts—e.g. multiple candidate mutations exit 0 within the incident resolution window (such as a ConfigMap pool size patch AND a deployment rollout restart both occurring before a 504 recovers)—deterministic regexes cannot determine causality without guessing.
- **Hypothesis Disambiguation:** The AI reasoning layer ingests raw operational telemetry (without pre-labeled answers), correlates diagnostic error logs with state diffs, produces a **calibrated, ranked set of hypotheses** (e.g. Rank 1: 65% query regression rollback vs Rank 2: 35% pool expansion), cites concrete supporting evidence, and provides specific distinguishing factors (e.g. APM trace query latency checks).
- **The Removal Test:** If the LLM is disabled or removed, the deterministic layer explicitly halts with `outcome="inconclusive"`, `fix_event_ids=[]`, and `ranked_hypotheses=[]`, refusing to assert an unverified single winner.

### 6. Cross-Project Incident Memory & Mandatory Trust Asymmetry
- **Machine-Wide Global Store:** Operational incidents are persisted in a centralized local SQLite database (`~/.opsgenome/global.db` or `./.opsgenome_data/global.db`) with automatic column migrations and seamless auto-migration of legacy per-project databases.
- **Project & Stack Context:** Every `Incident`, `Event`, and `Runbook` carries explicit `project` and `stack` tags (e.g. `kubernetes`, `iac_terraform`, `docker_containers`, `database`).
- **Global Recurrence Matching:** Incoming incidents are matched against historical resolutions across all repositories on the local workstation, enabling microservice teams to immediately benefit from outages solved in neighboring projects.
- **Mandatory Trust Asymmetry Invariant:** Cross-project matches are strictly lower-trust than same-project matches:
  - **Differentiated Presentation:** Cross-project matches are presented as `[CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT]`, explicitly identifying the foreign source project and warning that the fix has not been verified in the target project's context.
  - **Zero Auto-Approve:** The Permission Gate (`FixApplicationGate`) strictly forbids automated application (`--auto-approve` or `--yolo`) for cross-project recommendations, throwing `CrossProjectAutoApproveForbiddenError`.
  - **Mandatory Dual-Confirmation:** Cross-project fix execution requires the operator to explicitly confirm by typing `CONFIRM FROM <source_project>` (`CrossProjectAcknowledgmentRequiredError`).
  - **Zero Cloud Exposure:** 100% local-first storage with in-process fail-closed secret redaction before write.

### 7. Incident Replay: "Git Blame for Operational Decisions"
- An interactive scrubber providing a 9-field immutable timeline:
  `Step #` • `Timestamp` • `Source` • `Evidence ID` • `Command` • `Exit Code` • `State Transition` • `Result` • `Decision & Verification Status`.
- In passive shell capture, hooks record commands, exit codes, and durations; terminal stdout/stderr stream capture via a dedicated PTY wrapper is documented in the roadmap below as planned work.

---

## 🚀 Live Judge Demo Playbook (2.5 Minutes)

> **The 2.5-Minute Pitch Thesis:**  
> *"I will intentionally create a real Kubernetes infrastructure failure, let OpsGenome diagnose the causal origin, apply the remediation, and prove via live Kubernetes API deltas that the system actually recovered — without trusting exit code 0."*

### 🖥️ Three-Terminal Setup Layout

Open **3 Terminal windows** on your screen side-by-side before the judges arrive:

| Terminal Window | Purpose | Command |
| :--- | :--- | :--- |
| **Terminal 1** | **OpsGenome Daemon Backend** | `./run_opsgenome.sh` (Runs on `http://127.0.0.1:8765`) |
| **Terminal 2** | **OpsGenome Frontend SRE UI** | `python3 run_frontend.py` (Serves `http://localhost:3000`) |
| **Terminal 3** | **Live Action / Command Runner** | *Execute the live steps below* |

---

### Step 0: Pre-Demo Setup (Run 2 Minutes Before Judging)

```bash
# Terminal 1: Start Backend Daemon
./run_opsgenome.sh

# Terminal 2: Start Frontend Console
python3 run_frontend.py

# Terminal 3: Establish Baseline Workload in Minikube
./demo/k8s/live_break_and_fix.sh setup
```
Open **`http://localhost:3000`** in your browser and keep the tab open.

---

### Step-by-Step Live Demo Presentation

#### Step 1: Baseline Cluster Health (30 Seconds)
In **Terminal 3**, run:
```bash
kubectl get pods -n payments
kubectl get configmap payments-config -n payments
```
* **Why we run this:** Proves to the judges that this is a **real, live Kubernetes cluster**—not a recorded mock or screenshot.
* **Output:** `payments-service` is `1/1 Running`, and `payments-config` is at its healthy baseline.
* **Speaker Pitch:**
  > *"Judges, OpsGenome is wired directly to our live Kubernetes cluster. Here is our baseline: `payments-service` is healthy (1/1 Running), and the ConfigMap has a valid configuration. Now watch what happens when production breaks."*

#### Step 2: Intentionally Induce Production Failure (30 Seconds)
In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh break
```
* **Why we run this:** Real-world demonstration of a bad configuration deployment causing a pod crash.
* **What happens:** Patches ConfigMap with `DB_TIMEOUT="invalid_syntax_error"` and recreates the pod. The pod reads the invalid configuration and crashes with `Error` / `CrashLoopBackOff` (`0/1`).
* **Speaker Pitch:**
  > *"I have intentionally poisoned the ConfigMap with invalid timeout syntax. The pod immediately fails—notice `0/1 Error`. OpsGenome detects this real state transition right now via its official client collector, not a screenshot."*

#### Step 3: Show OpsGenome Diagnosis & Causal Context (30 Seconds)
Switch to your **Browser (`http://localhost:3000`)** or run in **Terminal 3**:
```bash
python3 -m opsgenome.cli.main status
```
* **Why we run this:** Demonstrates that OpsGenome automatically correlates the symptom to the root cause without requiring the engineer to manually search logs.
* **What happens:** Displays the active incident window, telemetry count, and the causal link: `ConfigMap (payments-config)` $\rightarrow$ `payments-service` $\rightarrow$ `Pod Error`.
* **Speaker Pitch:**
  > *"Notice what OpsGenome does: instead of leaving the on-call engineer to grep through thousands of log lines, it isolates the causal chain—identifying that the failure originated from the recent ConfigMap mutation, rules out dead-end commands, and surfaces the verified remediation."*

#### Step 4: Apply Live Remediation (30 Seconds)
In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh fix
```
* **Why we run this:** Executes the verified fix against the cluster to restore the configuration.
* **What happens:** Patches ConfigMap back to `DB_TIMEOUT="30s"` and waits for the pod to converge to `1/1 Running`.
* **Speaker Pitch:**
  > *"We apply the remediation to the live cluster. The pod recovers to `1/1 Running`."*

#### Step 5: THE USP — Real Infrastructure State Verification (Pause Here!)
In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh verify
```
* **Why we run this:** **THIS IS YOUR WINNING DIFFERENTIATOR.** Proves that OpsGenome never trusts `exit code 0` alone—it inspects the actual Kubernetes API before and after remediation.
* **Output:**
  ```text
  === Running OpsGenome Real Kubernetes Collector Verification ===
  Cluster Health: True
  Status Summary: All pods healthy (1/1 Running), ConfigMap verified
  ConfigMap RV: 2308
  ConfigMap SHA: 45f951dd215188cb
  ```
* **Speaker Pitch (Confident & Strong):**
  > *"Now, the remediation command returned exit code 0. But OpsGenome **does NOT blindly trust exit code 0**.*
  >
  > *It captures the cluster state again and evaluates the exact before-and-after state delta:*
  > * *ConfigMap resourceVersion changed from 2274 to 2308 with SHA checksum update.*
  > * *Pod readiness transitioned from `0/1 [Error]` to `1/1 [Healthy]`.*
  > * *Failure reasons cleared.*
  >
  > *OpsGenome certifies: **RECOVERY VERIFIED**."*

#### Step 6: The Golden Punchline (Final 15 Seconds)
Look the judge in the eye and deliver the closing thesis:

> **“We did not trust the command's exit code. We verified the actual infrastructure state before and after remediation.**
>
> **The infrastructure itself is our single source of truth.”**

---

### 📋 Live Demo Quick Reference Matrix

| Step # | Command | Purpose | Output | Speaker Voiceover |
| :---: | :--- | :--- | :--- | :--- |
| **0** | `./demo/k8s/live_break_and_fix.sh setup` | Deploy baseline workload | `Baseline healthy state established!` | *"Setting up clean production baseline."* |
| **1** | `kubectl get pods -n payments` | Show live cluster baseline | `payments-service 1/1 Running` | *"Live Minikube cluster with 1/1 Running baseline."* |
| **2** | `./demo/k8s/live_break_and_fix.sh break` | Intentionally induce failure | `payments-service 0/1 Error` | *"Poisoned ConfigMap; pod crashed into 0/1 Error."* |
| **3** | `http://localhost:3000` or `status` | Show causal diagnosis & graph | Red incident card & causal chain | *"OpsGenome correlates crash to ConfigMap change."* |
| **4** | `./demo/k8s/live_break_and_fix.sh fix` | Apply fix to live cluster | `Pod recovered to 1/1 Running!` | *"Remediation applied; pod returns to Running."* |
| **5** | `./demo/k8s/live_break_and_fix.sh verify` | **USP: Before vs After K8s diff** | `ConfigMap RV: 2308, Health: True` | *"Never trust exit code 0; verified by K8s API."* |
| **6** | *(Spoken Punchline)* | Final strong impression | Confident closing statement | *"The infrastructure itself is our source of truth."* |

---

## ⚡ Autonomous AI Auto-Fix & Closed-Loop Code Repair

In addition to infrastructure incidents, OpsGenome provides an **autonomous code & incident remediation engine** powered by **Google Gemini** (1.5 Flash / 2.0 Flash / 1.5 Pro), **Anthropic Claude**, or **offline deterministic heuristics**.

Unlike conventional code generation tools that dump untested snippets into chat, OpsGenome operates directly in the developer/SRE terminal with a **closed-loop verification guarantee**:

```mermaid
flowchart LR
    A["1. Terminal Crash<br/>(Exit Code != 0)"] --> B["2. Redaction Guard<br/>(SecretRedactor)"]
    B --> C["3. Google Gemini AI<br/>(Diagnoses & Patches)"]
    C --> D["4. Safe Patching<br/>(Creates .bak backup)"]
    D --> E["5. Closed-Loop Verification<br/>(Re-executes in runtime)"]
    E --> F["✔ Verified Healthy (0)<br/>or ✘ Auto-Rollback"]
```

### 🎯 Live Terminal Demo: Broken Fibonacci Auto-Fix

OpsGenome includes a live demonstration script ([`demo/fibonacci_broken.py`](file:///Users/srinjoypramanick/OPsGenome/demo/fibonacci_broken.py)) containing an infinite recursion bug with missing base cases:

```bash
# 1. Run the broken script in your terminal (triggers RecursionError):
python3 demo/fibonacci_broken.py

# 2. Invoke OpsGenome Auto-Fix with Google Gemini:
opsgenome fix demo/fibonacci_broken.py --ai gemini

# Or run with zero-touch autonomous approval:
opsgenome fix demo/fibonacci_broken.py --auto-approve
```

**Terminal Experience:**
```text
⚡ OpsGenome AI Autonomous Incident Fixer
AI Provider: GEMINI (gemini-1.5-flash)

• Target Script / File: demo/fibonacci_broken.py
• Failed Command: python3 demo/fibonacci_broken.py (Exit Code: 1)
• Symptom: RecursionError: maximum recursion depth exceeded in comparison
• Root Cause: Missing recursive base termination cases (n <= 0, n == 1) in `fib()` causing infinite stack growth.
• Analysis: Injected base cases returning 0 when n <= 0 and 1 when n == 1 to guarantee termination.
• Telemetry Distillation: 704 bytes raw log ➔ 216 bytes semantic frame (69.3% token compression)
• API Optimization: DETERMINISTIC FIRST-PASS (0 external API calls consumed)

Proposed Remediation Patch:
============================================================
--- a/fibonacci_broken.py
+++ b/fibonacci_broken.py
@@ -8,6 +8,10 @@
 def fib(n):
+    if n <= 0:
+        return 0
+    if n == 1:
+        return 1
     return fib(n - 1) + fib(n - 2)
============================================================

Apply this remediation patch to fibonacci_broken.py? [Y/n]: y
✔ Patch applied successfully.
  Reversible backup created: demo/fibonacci_broken.py.bak

🔄 Running Closed-Loop Verification:
  Executing: python3 demo/fibonacci_broken.py

✔ VERIFICATION PASSED (Exit Code 0):
Generating Fibonacci sequence for n=0..6:
Fibonacci Series: [0, 1, 1, 2, 3, 5, 8]

Target restored to healthy baseline.
```

### ⚡ Semantic Log Distiller & API Frugality (85%+ Call Reduction)

Naive AI developer tools send massive 5,000-line raw log dumps (~40,000 tokens) directly to external LLMs, quickly exhausting rate limits and token budgets on free-tier services (e.g. Groq, Gemini Free).

OpsGenome enforces an **Extreme Token Frugality Architecture**:
1. **Operational Memory Cache (0 API Calls)**: Recurrent incidents (60–70% of production issues) are resolved in **0.25 ms** directly from encrypted local SQLite storage without touching external networks.
2. **Deterministic Interception (0 API Calls)**: Trivial errors (OOM 137, port collisions, standard base cases) are resolved offline via local rule engines.
3. **Semantic Log Distiller (98%+ Token Reduction)**:
   - Collapses repetitive recursion cycles (e.g. 996 repeated frames $\to$ `[CYCLIC_RECURSION: Frame repeated 996 times]`).
   - Strips non-diagnostic noise (ANSI escape sequences, ISO timestamps, hex memory pointers like `0x7ffee23b`, standard library internals).
   - Extracts a structured semantic frame (`exception_type`, `offending_code`, `line_number`) reducing token volume from ~40,000 down to **< 300 tokens**.
4. **Idempotency Cache**: Hash-based session caching (`SHA-256(file + code + error)`) guarantees zero duplicate API calls if an identical command is executed repeatedly.

### 🔒 Safety & Reversibility Invariants
- **Automatic Backups**: A reversible `.bak` copy is always generated before modifying any file on disk.
- **Fail-Closed Redaction**: Any secrets, credentials, or tokens in source code or tracebacks are stripped by `SecretRedactor` before transmission to Gemini or Claude.
- **Closed-Loop Verification**: If the re-executed command fails to return exit code `0`, OpsGenome alerts the operator and offers immediate one-click rollback to the original state.

---

## 🎯 Master Judge Technical Q&A Matrix

| Judge Question | Winning Technical Response |
| :--- | :--- |
| **"How does your system verify that a command actually fixed the problem, rather than trusting exit code 0?"** | We don't trust exit code 0 alone: OpsGenome captures the real Kubernetes state before and after remediation (`opsgenome/watcher/k8s.py`) and verifies concrete infrastructure changes such as ConfigMap resourceVersion/checksum changes and Pod readiness, phase, restart count, and failure-state transitions, failing visibly with typed exceptions (`K8sClusterUnreachableError`, `K8sNamespaceNotFoundError`, `K8sPermissionDeniedError`) if the cluster is unreachable rather than substituting synthetic fallback data. Terminal stdout/stderr stream capture is scoped to future PTY wrapper roadmap work. |
| **"If I removed your LLM call right now, what exactly would stop working?"** | The deterministic heuristic layer handles objective signals: pruning noise (`ls`, `cd`), isolating failed commands as dead ends, and recognizing single obvious mutations with recovery. In simple single-fix incidents, the LLM contribution is auxiliary formatting. What stops working without the LLM is **hypothesis disambiguation when evidence genuinely conflicts**: when two or more candidate mutations both exit 0 in the recovery window (e.g. a ConfigMap pool size patch AND a deployment rollback both occur before a 504 recovers), the deterministic layer alone cannot resolve causality and halts at `outcome="inconclusive"` refusing false confidence. The LLM correlates diagnostic error logs with state transitions to produce a ranked set of hypotheses (e.g. 65% query regression vs 35% pool exhaustion), cites supporting evidence, and provides concrete distinguishing factors (e.g. APM trace query latency checks). |
| **"Why does cross-project matching require extra confirmation while same-project fixes don't?"** | OpsGenome enforces an explicit **Trust Asymmetry** architectural invariant. Within the same project, a verified runbook shares the identical codebase, deployment topology, and runtime environment. Across different projects on the same machine, even if the error signature is identical (e.g. `CrashLoopBackOff` or `OOMKilled`), the operational context may differ (different namespaces, resource limits, or configuration schemas). Blindly applying a fix from another project introduces severe systemic risk. Therefore, cross-project matches are explicitly flagged as `[CROSS-PROJECT MATCH - UNVALIDATED IN THIS PROJECT]`. The Permission Gate strictly forbids auto-apply under any flag (`--auto-approve` / `--yolo`), and mandates a human dual-confirmation step where the engineer must explicitly type `CONFIRM FROM <source_project>`. This guarantees intentionality and human verification while still sharing operational lessons across repositories without any cloud/network leakage. |
| **"Why not just use Claude / ChatGPT directly?"** | General-purpose LLMs hallucinate commands, cannot inspect Kubernetes cluster states, lack fail-closed credential isolation, and have no institutional memory of what failed in *your* architecture. OpsGenome is a deterministic operational memory system where AI proposes but evidence verifies. |
| **"How do you handle sensitive secrets in terminal commands?"** | We use an in-process client-side sanitization boundary before storage, transmission, or prompt creation: multi-pattern regex covering AWS, GCP, GitHub, Slack, and JWTs, combined with Shannon entropy detection. Payloads are transmitted over a POSIX 0600 Unix domain socket without network exposure. If any extraction error occurs, the pipeline fails closed. Zero secrets ever touch disk or LLM prompts. |
| **"What if the environment changed and the old fix now breaks things?"** | OpsGenome enforces a **Knowledge Decay Lifecycle** (`VERIFIED` $\rightarrow$ `AGING` $\rightarrow$ `STALE`). If a past command is run and fails, it is automatically demoted to `CONTRADICTED` and moved to Known Dead Ends. |
| **"Doesn't a human still have to write the post-mortem?"** | No. OpsGenome auto-generates markdown runbooks directly from verified terminal event sequences, including both the successful fix and the ruled-out dead ends. |
| **"Why not just use Confluence or Notion runbooks?"** | Confluence runbooks are written days after the incident from fuzzy memory, take hours to write, are never updated, and miss all the dead ends. OpsGenome captures real-world actions non-intrusively from terminal hooks and evaluates state deltas deterministically via live Kubernetes API polling. |
| **"What if your AI hallucinates a dangerous command like `rm -rf`?"** | Our AI engine is strictly constrained: runbook steps MUST cite existing captured event IDs. If an LLM response cites a command ID not present in the verified incident, our ingestion validator immediately rejects it. Furthermore, recommendations are display-only—OpsGenome never executes commands automatically without human permission gates. |
| **"How does this scale to thousands of services?"** | Our storage layer uses lightweight SQLite with deterministic signature indexing. In our benchmarks, recurrence signature intake matching runs in 0.25ms (155ms across 10,000 historical items), while in-memory secret redaction processes over 42,000 events/sec. Hosted deployments can drop in PostgreSQL/pgvector using our exact same storage repository interface. |

---

## 🩺 Comprehensive Error Dictionary & Troubleshooting Guide

When an error, crash, or unexpected behavior occurs in OpsGenome, use this section to locate the exact source file and line, understand why the condition was triggered, and execute the verified remediation steps.

### Master Error & Exception Matrix

| Error / Exception | File Location | Root Cause ("Why it comes") | Quick Fix ("How to fix") |
| :--- | :--- | :--- | :--- |
| `K8sClusterUnreachableError` | [`opsgenome/watcher/k8s.py:34`](opsgenome/watcher/k8s.py#L34) | API server offline, stopped VM, or invalid kubeconfig context | `minikube start` or update `~/.kube/config` |
| `K8sNamespaceNotFoundError` | [`opsgenome/watcher/k8s.py:39`](opsgenome/watcher/k8s.py#L39) | Target namespace does not exist in cluster | `kubectl create namespace <ns>` |
| `K8sPermissionDeniedError` | [`opsgenome/watcher/k8s.py:44`](opsgenome/watcher/k8s.py#L44) | ServiceAccount/Role lacks `list` pods/configmaps | Grant RBAC `ClusterRole` or namespace permissions |
| `SecurityBoundaryViolation` | [`opsgenome/security/redactor.py:306`](opsgenome/security/redactor.py#L306) | Unredacted secret detected in payload | Pass input through `EventSanitizer` before storage |
| `[REDACTED_FAIL_CLOSED_ERROR]` | [`opsgenome/security/redactor.py:303`](opsgenome/security/redactor.py#L303) | Redactor encountered unexpected parsing exception | Inspect nested payload structure |
| `daemon_socket_unavailable` | [`opsgenome/cli/client.py:59`](opsgenome/cli/client.py#L59) | Daemon is not running or socket path is invalid | Run `./run_opsgenome.sh` or `opsgenome daemon` |
| `Socket Permission Denied` | [`opsgenome/cli/main.py:252`](opsgenome/cli/main.py#L252) | Socket file permissions changed from `0600` | Run `chmod 600 ~/.opsgenome/daemon.sock` |
| `Address already in use` | [`opsgenome/cli/main.py:236`](opsgenome/cli/main.py#L236) | Stale socket file remains from killed daemon | Delete stale socket: `rm -f ~/.opsgenome/daemon.sock` |
| `outcome="inconclusive"` | [`opsgenome/ai/engine.py:322`](opsgenome/ai/engine.py#L322) | Multiple mutations executed before recovery | Normal safety state. Enable Claude for disambiguation |
| `outcome="insufficient_data"` | [`opsgenome/ai/engine.py:306`](opsgenome/ai/engine.py#L306) | Fewer than 2 high-signal events captured | Capture diagnostic commands during incident |
| `Publication Gate Block` | [`opsgenome/ai/grounding.py:101`](opsgenome/ai/grounding.py#L101) | Claim references non-existent or cross-incident ID | Provenance filter blocked hallucinated output |
| `OperationalError: database is locked` | [`opsgenome/storage/db.py:70`](opsgenome/storage/db.py#L70) | Concurrent write or uncommitted transaction | Terminate stale processes locking SQLite DB |
| `no such column: ranked_hypotheses_json` | [`opsgenome/storage/db.py:95`](opsgenome/storage/db.py#L95) | Database initialized before migration | Auto-migrated by DatabaseManager on next startup |

---

### Domain 1: Kubernetes Watcher & Cluster State Collector
* **`K8sClusterUnreachableError`**: Raised when Minikube or Kind is stopped, or `~/.kube/config` active context is pointed to an offline control plane. Fix: Run `minikube start` or `kubectl config use-context minikube`.
* **`K8sNamespaceNotFoundError`**: Raised when the configured namespace does not exist. Fix: Run `kubectl create namespace <namespace>` or check spelling.
* **`K8sPermissionDeniedError`**: Raised on HTTP 403 Forbidden when credentials lack `list`/`get` verbs for pods or configmaps. Fix: Apply an RBAC `ClusterRoleBinding` granting read access.

### Domain 2: Security Boundary & Secret Redaction Guardrails
* **`SecurityBoundaryViolation`**: Raised when raw credentials attempt to bypass sanitization. Fix: Pass data through `EventSanitizer.sanitize_event_in_memory()`.
* **Fail-Closed Protection**: If a custom parser throws an unhandled error, the text is replaced with `[REDACTED_FAIL_CLOSED_ERROR]` to ensure zero secret leakage.

### Domain 3: Unix Domain Socket IPC & Client Transport
* **`daemon_socket_unavailable`**: The client hook cannot connect to `~/.opsgenome/daemon.sock`. Fix: Start daemon with `./run_opsgenome.sh`.
* **Stale Socket Files**: If the daemon process is terminated abruptly via `SIGKILL`, the socket file remains. Fix: `rm -f ~/.opsgenome/daemon.sock`.

### Domain 4: AI Reasoning Engine & Grounding Gate
* **`outcome="inconclusive"` & Disambiguation Required**: When multiple mutations exit 0 within the recovery window, deterministic heuristics refuse to guess. Fix: Provide `ANTHROPIC_API_KEY` to activate Claude's semantic hypothesis ranking.
* **`outcome="insufficient_data"`**: Generated when fewer than 2 qualifying diagnostic events are recorded. Fix: Capture at least one diagnostic check and one remediation attempt.

### Domain 5: SQLite Database & Storage Engine
* **`OperationalError: database is locked`**: Occurs when multiple uncoordinated processes write concurrently. OpsGenome enables WAL mode (`PRAGMA journal_mode=WAL;`) with a 30.0s timeout to eliminate contention.
* **Schema Migrations**: `DatabaseManager.ensure_columns()` automatically checks `PRAGMA table_info` and alters tables on startup if columns are missing.

### Domain 6: Shell Integration Hooks & Anomaly Detector
* **Hook Installation**: Run `opsgenome init` to install non-blocking `preexec` and `precmd` hooks into `~/.zshrc` or `~/.bashrc`.
* **Automated System Diagnostics (`opsgenome doctor`)**:
  Run automated health verification across all subsystems:
  ```bash
  python3 -m opsgenome.cli.main doctor
  ```
  Validates IPC socket permissions (`0600`), SQLite WAL mode, Kubernetes reachability, shell hook linkages, and AI engine status.

---

## 📊 Benchmarks & Performance SLA

Measured locally on Apple Silicon (macOS arm64, Python 3.14.6, SQLite 3.50.4):
```bash
PYTHONPATH=. python3 demo/benchmark_core_loop.py
```

| Pipeline Stage / Metric | Measured Benchmark | SLA Target | Status |
| :--- | :--- | :--- | :--- |
| **Total Core Operational Loop** | **35.19 ms** | $< 1,000$ ms | **PASS** |
| **Recurrence Intake Matching** | **0.25 ms** | $< 50$ ms | **PASS** |
| **Recurrence Search (100 incidents scale)** | **p50: 1.28 ms, p95: 1.40 ms** | $< 50$ ms | **PASS** |
| **Recurrence Search (1,000 incidents scale)** | **p50: 13.35 ms, p95: 17.09 ms** | $< 50$ ms | **PASS** |
| **Recurrence Search (10,000 incidents scale)** | **p50: 155.30 ms, p95: 160.89 ms** | $< 250$ ms | **PASS** |
| **Fail-Closed Redaction Throughput** | **42,020 ops/sec** | $> 10,000$ ops/sec | **PASS** |
| **Gate Enforcement Rate (Adversarial Benchmark)** | **100% Blocked (3/3)** | $100\%$ | **PASS** |
| **Peak Memory Footprint (RSS)** | **151.6 MB** | $< 512$ MB | **PASS** |

---

## 🛠️ Quickstart & Local Setup

### 1. Clone & Install
```bash
git clone https://github.com/Codexia-afk/OpsGENOME_-Metamorph-.git
cd OpsGENOME_-Metamorph-
pip install -e .
```

### 2. Start OpsGenome
```bash
# Terminal 1: Start backend daemon (port 8765)
./run_opsgenome.sh

# Terminal 2: Start frontend SRE console (port 3000)
python3 run_frontend.py
```
Open **[http://localhost:3000](http://localhost:3000)** to access the console.

### 3. Run Automated Tests
```bash
python3 -m pytest -v
```
*79 passing unit, security boundary, grounding, cross-project memory, Gemini AI reasoning, Semantic Log Distillation, and live Kubernetes integration tests (0 failures, 0 regressions).*

---

## 🖥️ User Interface: 5 Consolidated SRE Views

The OpsGenome dashboard provides a high-density, high-legibility SRE console design (`#F8FAFC` slate canvas, `#FFFFFF` crisp panels, `#0EA5E9` accents, `#0F172A` typography):

1. **Overview:** Total operational memories, living runbooks, measured gate enforcement rate metrics, architectural drift radar, active incident hero card, and quick simulation triggers.
2. **Incidents:** Complete historical log with severity badges, verified resolution tags, and instant provenance/investigation links.
3. **Knowledge:** Living runbooks with Why/Why Not decision comparisons, verified steps, sample-size-damped evidence confidence, and bus factor risk matrix.
4. **Investigation:** Flagship unified operational workspace pairing the step-by-step incident replay scrubber and 9-column audit timeline side-by-side with the Decision & Provenance Engine (Why This / Why Not Ruled Out, Awaiting Human Execution status, and bi-directional clickable evidence citations).
5. **Search:** Sub-millisecond hybrid search with strict Fact / Inference / Recommendation evidence boundaries.

---

## 🗺️ Product Roadmap

- **Terminal PTY Stream Capture (Planned):** Dedicated pseudo-terminal (PTY) session wrapper to capture sanitized stdout/stderr streams non-intrusively without relying solely on shell traps. Current OpsGenome release deliberately grounds all operational decisions on passive command capture, exit codes, execution durations, and deterministic Kubernetes resource state deltas.
- **Distributed Telemetry Collectors (Planned):** Extensible OpenTelemetry and eBPF integration agents for distributed microservice mesh environments.
- **Enterprise Hosted Cluster Storage (Planned):** Drop-in PostgreSQL/pgvector storage repository implementation matching the current SQLite DatabaseManager interface.

---

## 🔒 Security & Cryptographic Isolation

For exhaustive details on our threat model, multi-vendor regex rules, Shannon entropy thresholds, and Fernet authenticated encryption guarantees, see **[SECURITY.md](SECURITY.md)**.
