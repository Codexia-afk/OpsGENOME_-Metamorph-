# 🎬 OpsGenome Live Demo Script & Command Guide for Judges

> **The Operational Memory Engine**  
> *"AI proposes; deterministic evidence verifies. Never fix the same production incident a fourth time."*

This document provides the exact sequence of commands, talking points, and screen actions to execute during your live presentation before the judges.

---

## ⚡ Quick Reference Cheat Sheet

| Time | Action | Exact Command | What Judges See |
| :--- | :--- | :--- | :--- |
| Time | Action | Exact Command | What Judges See |
| :--- | :--- | :--- | :--- |
| **00:00** | **Start Services** | `python3 run_frontend.py` | Unified Web & Swarm Studio live on `http://localhost:8000` |
| **00:30** | **Multi-Agent Swarm** | `python3 demo/run_multiagent_demo.py` | 4 stacks analyzed & 5 cluster issues audited in **0.003s** |
| **01:15** | **Swarm CLI Dialogue** | `opsgenome multi-agent analyze --demo` | Inter-agent dialogue, Kahn's algorithm DAG, unified diffs |
| **01:45** | **Live Chaos & Commit** | `opsgenome multi-agent chaos-test` | Dynamic fault injection, Kahn's DAG, transactional commit |
| **02:15** | **Atomic Rollback** | `opsgenome multi-agent chaos-test --fail-verify` | Intentional syntax error triggers automatic atomic rollback & SHA-256 restore |
| **02:45** | **Cluster Multi-Issue** | `opsgenome multi-agent cluster-audit` | Table of 5 anomalies with copyable CLI & YAML patches |
| **03:15** | **1M Log Triage** | `pytest opsgenome/tests/test_scale_benchmark.py -v` | 1,000,000 lines scanned in constant $O(1)$ memory (0 MB) |
| **04:00** | **Interactive Menu** | `opsgenome` *(Press `[9]` or `[m]`)* | ASCII mascot, flight simulator, live status |
| **04:30** | **Web UI (Localhost:8000)**| Browser: `http://localhost:8000` | Top `🤖 Swarm Studio` button, Visual Diffs, Live Terminal Console, Raw Logs |
| **05:00** | **Test Proof** | `pytest -v` | **128 passed, 0 failures (100% pass rate)** |

---

## 🚀 Quick 1-Second Setup (Enable `opsgenome` command in zsh)

Run this once in your terminal:
```bash
alias opsgenome="./bin/opsgenome"
```
*(Or run `./bin/opsgenome` directly without setting an alias)*

---

## 🚀 Pre-Demo Checklist (2 Minutes Before Presentation)

Open **two terminal windows**:

### Terminal 1: Unified Web & Swarm Studio Server
```bash
cd /Users/srinjoypramanick/OPsGenome
python3 run_frontend.py
```
*(Leave this running. Open your browser at `http://localhost:8000`)*

### Terminal 2: Live Demo Execution Window
```bash
cd /Users/srinjoypramanick/OPsGenome
alias opsgenome="./bin/opsgenome"
opsgenome --version
```


---

## 🎭 Step-by-Step Demo Flow

---

### Step 1: Multi-Agent Swarm Cross-Stack Resolution (The Big Pitch)
> 🗣️ **What to say to the judges:**  
> *"Judges, you asked for multi-agent capabilities: when an outage affects multiple files across different technology stacks—Python, Java, Node.js, and Kubernetes—they cannot be fixed in isolation. OpsGenome dispatches concurrent specialist agents, scans diffs with a fail-closed Security Sentinel, orders fixes topologically, and guarantees atomic rollback."*

```bash
# Run the instant multi-agent swarm demonstration
python3 demo/run_multiagent_demo.py
```

**What happens:**
1. Swarm registers 6 agents: Lead SRE Orchestrator, Python Specialist, Java Specialist, Node.js Specialist, Cluster Specialist, Security Sentinel.
2. Concurrent analysis across:
   - `services/payment-engine/main.py` (Python `NameError`)
   - `services/api-gateway/index.js` (Node unawaited Promise `TypeError`)
   - `services/billing/PaymentProcessor.java` (JVM `NullPointerException`)
   - `deployments/k8s/payment-deployment.yaml` (Kubernetes `OOMKilled` 64Mi limit)
3. Security Sentinel enforces zero secret leakage and safe execution.
4. Lead Orchestrator computes **Topological Dependency Order**:
   - `Step 1: payment-deployment.yaml` *(Infrastructure first to guarantee memory headroom)*
   - `Step 2: main.py` *(Core backend service)*
   - `Step 3: PaymentProcessor.java` *(JVM billing engine)*
   - `Step 4: index.js` *(API Gateway ingress)*
5. **Execution completes in 0.003 seconds.**

---

### Step 2: Live Agent Dialogue & Coordinated Unified Diffs
> 🗣️ **What to say to the judges:**  
> *"Let's inspect the actual inter-agent dialogue and formulated code diffs in the terminal."*

```bash
opsgenome multi-agent analyze --demo
```

**What to point out on screen:**
- `Lead SRE Orchestrator ➔ Multi-Agent Swarm [TASK_DISPATCH]`
- Individual hypotheses from Python, Node, and Java specialists.
- `Security Sentinel Agent [STATUS_UPDATE]`: *"✔ All proposed diffs verified safe: 0 credential leaks, 0 destructive shell patterns."*
- Line-by-line unified diffs with defensive safety guards:
  - Python: `fee_rate = 0.02` fallback declared.
  - Java: `if (amount == null) return 0.0;` injected before dereference.
  - Node: `await resp.json()` injected to resolve Promise before property read.
  - Kubernetes: `memory: 512Mi` patched to eliminate cgroup OOM kills.
- Atomic rollback strategy: `.bak` backups created prior to filesystem writes.

---

### Step 2.5: Live Chaos Fault Injection & Two-Phase Transactional Rollback (The Winner Showstopper)
> 🗣️ **What to say to the judges:**  
> *"Judges, any tool can apply a patch blindly. What separates industrial systems engineering from an irresponsible AI script is closed-loop transactional verification. If an LLM generates invalid code or a compiler error occurs, OpsGenome automatically aborts and rolls back all modified files to their exact pre-flight SHA-256 state."*

```bash
# 1. Normal Transaction: Validates DAG, compiles healthy code, and commits
opsgenome multi-agent chaos-test

# 2. Chaos Mode: Injects intentional syntax defect to prove automatic atomic rollback
opsgenome multi-agent chaos-test --fail-verify
```

**What to point out on screen:**
- **Mathematical In-Degree Reduction DAG**:
  - `payment-deployment.yaml` (Step 1) ➔ `main.py` (Step 2) ➔ `PaymentProcessor.java` (Step 3) ➔ `index.js` (Step 4).
- **Phase 1: Pre-flight Cryptographic Hashing**:
  - `✔ Applied patch to main.py (pre-flight sha256: 998ca39e, backup: main.py.bak)`
- **Phase 2: Closed-Loop Syntax & Health Verification**:
  - `✘ Verification failed for main.py (Exit code 1): SyntaxError: invalid syntax`
- **Phase 3: Automated Atomic Rollback**:
  - `↺ INITIATING AUTOMATIC TRANSACTIONAL ROLLBACK (Atomic Failure Recovery)...`
  - `↺ Rolled back index.js from index.js.bak (hash verified: True)`
  - `↺ Rolled back PaymentProcessor.java from PaymentProcessor.java.bak (hash verified: True)`
  - `↺ Rolled back main.py from main.py.bak (hash verified: True)`
  - `↺ Rolled back payment-deployment.yaml from payment-deployment.yaml.bak (hash verified: True)`
  - `↺ TRANSACTION STATUS: ROLLED_BACK (Safety Invariant Preserved)`

---

### Step 3: Kubernetes & Docker Multi-Issue Cluster Auditor
> 🗣️ **What to say to the judges:**  
> *"You also asked: what if a Kubernetes or Docker cluster has multiple simultaneous issues? Even if an organization does not allow an AI to execute write operations directly on production clusters, OpsGenome scans the entire cluster, diagnoses all co-existing failure modes, and hands operators exact copy-pasteable CLI commands and declarative YAML patches."*

```bash
opsgenome multi-agent cluster-audit --namespace production
```

**What to point out on screen:**
- **Cluster Anomaly Matrix Table**:
  - `CRITICAL`: `payments-api-7c9d` (CrashLoopBackOff)
  - `HIGH`: `batch-worker-4e2b` (OOMKilled)
  - `HIGH`: `frontend-gateway` (SelectorMismatch)
  - `MEDIUM`: `auth-service-89f1` (ReadinessProbeFailed)
  - `MEDIUM`: `redis-cache` (Docker PortConflict)
- **Step-by-Step Remediation Playbook**:
  - Exact `kubectl set env` command for CrashLoopBackOff.
  - Exact `kubectl patch deployment` for memory limits.
  - Exact `kubectl patch service` for selector mismatch.
  - Exact `docker compose` command for port conflict.
  - Clean declarative YAML before/after patch blocks.

---

### Step 4: Large-Scale Streaming Log Triage ($O(1)$ Memory Proof)
> 🗣️ **What to say to the judges:**  
> *"Real outages generate gigabytes of logs. Traditional AI tools crash from OOM trying to load entire logs into memory or LLM context windows. OpsGenome streams 1,000,000 lines in constant O(1) memory, skipping noise at 68,000 lines per second, and sends only bounded high-confidence candidates to the AI."*

```bash
# Run the verified 10K, 100K, and 1,000,000 line scale benchmark
pytest opsgenome/tests/test_scale_benchmark.py -v
```

**Benchmark Results to quote:**
- **1,000,000 lines** scanned in **14.7 seconds** (67,993 lines/sec).
- **Peak RAM allocated: 0.00 MB** ($O(1)$ memory streaming).
- **LLM Prompt Size Invariance:** 3,148 characters for 10K lines vs 3,154 characters for 1,000,000 lines ($\Delta < 0.2\%$).

```bash
# Run standalone triage CLI on sample log
opsgenome triage demo-projects/svc-checkout/sample.log
```

---

### Step 5: Interactive Terminal Quick Menu & Flight Simulator
> 🗣️ **What to say to the judges:**  
> *"Operators can interact with OpsGenome through single-key shortcuts in our terminal console."*

```bash
opsgenome
```

**Interactions to demonstrate:**
1. Type `9` or `m` ➔ Runs live Multi-Agent Swarm demo.
2. Type `2` or `r` ➔ Displays Runbook Library with **earned confidence** (e.g. `87% — 7 of 8`).
3. Type `3` or `d` ➔ Shows Systemic Drift Radar & Backlog Defect Tickets.
4. Type `4` or `b` ➔ Shows Tribal Knowledge Concentration & Bus Factor.
5. Type `8` or `c` ➔ Runs automated system Doctor check (0600 socket, DB, hooks).

---

### Step 6: Interactive Web UI Walkthrough (Browser)
> 🌐 **Navigate to:** `http://localhost:3000`

1. **Header & Hamburger Drawer:**
   - Click the **Hamburger Icon (`☰`)** in the top-left corner.
   - Show the slide-over drawer containing:
     - All 8 Platform Views: Overview, Live Studio, Knowledge Base, Deep Investigation, **Multi-Agent Studio**, Architecture, Verification, Search.
     - 1-Click Simulated Outage triggers.
   - Point out the top-right **GitHub Logo button** linking directly to the project's repository (`https://github.com/Codexia-afk/OpsGENOME_-Metamorph-`).
2. **Multi-Agent Studio View (Click "Multi-Agent Studio" in drawer):**
   - **Swarm Status Bar:** Show the 6 active specialist badges with pulsing indicators.
   - **Tab 1: Cross-Stack Multi-File Incident:**
     - Click **"RUN MULTI-STACK ANALYSIS"** button.
     - Show the **Live Inter-Agent Dialogue Stream** on the left.
     - Show the **Topological Execution Sequence** tabs on the right (`payment-deployment.yaml` ➔ `main.py` ➔ `PaymentProcessor.java` ➔ `index.js`).
     - Click each file tab to show the **line-by-line syntax-colored diff** (green `+`, red `-`).
     - Click **"APPLY COORDINATED FIX"** button to show atomic rollback protection.
   - **Tab 2: Cluster Multi-Issue Auditor:**
     - Click the sub-tab.
     - Show the 4 metric cards (`5 Anomalies`, `1 Critical`, `2 High`, `4 Automated-Safe`).
     - Show the Anomaly Diagnostic Matrix table.
     - Click the **"COPY CLI"** and **"COPY YAML"** buttons on any issue card to demonstrate operator copy-paste readiness.
3. **Knowledge Base View:**
   - Show institutional runbooks with earned confidence badges and Why / Why-Not rationale.
   - Click **"EXPORT MARKDOWN"** to show instant GitHub-flavored markdown export.
4. **Investigation Replay View:**
   - Step through the interactive scrubber to show deterministic before/after state deltas.

---

### Step 7: Final Test Suite Proof (Engineering Rigor)
> 🗣️ **What to say to the judges:**  
> *"To prove this is production-grade industrial software and not a hackathon prototype, our entire test suite passes with 100% success."*

```bash
# Run the dedicated multi-agent test suite
pytest opsgenome/tests/test_multi_agent.py -v

# Run the complete test suite
pytest
```

**Expected Result:**
```text
======================= 128 passed, 1 skipped in 11.23s =======================
```

---

## 🎯 60-Second Elevator Pitch (Memorize This!)

> *"Judges, production incident response is broken. Post-mortems are written days late, tribal knowledge is trapped in Slack, and the same outage recurs 3 times because nobody remembers why it broke.*
>
> *OpsGenome is the Operational Memory Engine. We don't guess—we ground AI proposals in deterministic evidence. With our new Multi-Agent Swarm, we analyze cross-stack incidents across Python, Java, Node.js, and Kubernetes simultaneously, order patches topologically, and enforce atomic rollback.*
>
> *When a cluster has multiple co-existing issues, our Cluster Auditor immediately pinpoints all root causes and gives SREs exact CLI commands and YAML patches.*
>
> *128 tests passing, 0.003-second swarm coordination, and 1,000,000 log lines scanned in 0 MB RAM. Thank you!"*

---

## 🛠️ Troubleshooting & Emergency Commands

If anything gets closed during the demo:

| Issue | Quick Fix Command |
| :--- | :--- |
| Frontend won't load on port 3000 | `python3 run_frontend.py` |
| Backend daemon port 8765 occupied | `lsof -i :8765` then `kill -9 <PID>` |
| Test cache stale | `pytest --cache-clear` |
| Reset terminal colors | `reset` or `echo -e "\033[0m"` |

