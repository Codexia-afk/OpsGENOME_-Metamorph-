# 🏆 OpsGenome — National Hackathon Judge Demo Playbook & Command Cheat Sheet

> **One-Line Positioning:**  
> *"OpsGenome turns complex cross-stack incidents into coordinated, security-validated, dependency-aware remediation — using a swarm of specialized agents instead of a single black-box AI."*

---

## ⚡ 0. Pre-Presentation Setup

Open **two terminal windows** side-by-side:

### Terminal 1 — Start Web & Swarm Studio
```bash
cd /Users/srinjoypramanick/OPsGenome
python3 run_frontend.py
```
* **Expected Output:** `🚀 OpsGenome Unified Web & Swarm Studio Online on Port 8000`
* **Open in Browser:** **`http://localhost:8000`**

### Terminal 2 — Setup CLI Alias & Health Check
```bash
cd /Users/srinjoypramanick/OPsGenome
alias opsgenome="./bin/opsgenome"
opsgenome --version
opsgenome doctor
```

---

## 🎬 Cluster 1 — Hero Demo: Multi-Agent Swarm Cross-Stack Resolution

### 🎤 What to Say to Judges:
> *"Judges, when an outage hits multiple files across different technology stacks—Python, Java, Node.js, and Kubernetes—they cannot be fixed in isolation. OpsGenome dispatches six specialist agents concurrently, consults a fail-closed Security Sentinel, orders fixes topologically using Kahn’s algorithm, and enforces atomic rollback."*

### Demo 1 — Instant End-to-End Swarm (0.003s)
```bash
python3 demo/run_multiagent_demo.py
```

#### What the Judges See:
* **6 Specialist Agents Registered:**
  - Lead SRE Orchestrator
  - Python Specialist Agent
  - Java / JVM Specialist Agent
  - Node.js Specialist Agent
  - Cluster & Infra Specialist Agent
  - Security Sentinel Agent
* **Concurrent Diagnostics:**
  - Python `NameError` (undefined variable)
  - Node.js `TypeError` (unawaited async response Promise)
  - Java `NullPointerException` (unboxing null Double)
  - Kubernetes `OOMKilled` (undersized 64Mi container limit)
* **Topological Dependency Execution Sequence (Kahn’s Algorithm):**
  $$\text{Manifests (K8s)} \longrightarrow \text{Backend Services (Java, Python)} \longrightarrow \text{Ingress Gateway (Node.js)}$$

---

## 💻 Cluster 2 — Detailed Inter-Agent Dialogue & Safety Sentinel

### Run:
```bash
opsgenome multi-agent analyze --demo
```

#### What the Judges See:
* **Real-time inter-agent communication messages:**
  - `[TASK_DISPATCH]`
  - `[DIAGNOSTIC_HYPOTHESIS]`
  - `[SAFETY_CHECK]`
  - `[STATUS_UPDATE]`
  - `[COORDINATED_PLAN]`
* **Security Sentinel Verification:**
  - `✔ Security Sentinel verified: 0 credential leaks, 0 destructive shell patterns, fail-closed boundaries enforced.`
* **Line-by-Line Syntax Diffs:**
  - Formulated unified diffs with exact line numbers and root causes.
  - `.bak` automatic rollback and verification strategy.

---

## 📂 Cluster 3 — Prove It Is NOT Hardcoded (Physical Files on Disk)

### 🎤 What to Say to Judges:
> *"All of these target microservices and incident logs exist as real, physical files on disk in our repository. Nothing is hardcoded into the orchestrator."*

### Demo 1 — Inspect Physical Incident Log
```bash
cat demo-projects/multi-stack-incident/logs/cross_stack_incident.log
```

### Demo 2 — Inspect Physical Kubernetes Event Stream
```bash
cat demo-projects/multi-stack-incident/logs/k8s_cluster_events.log
```

### Demo 3 — Run Swarm Against Physical Disk Files Directly
```bash
opsgenome multi-agent analyze \
  --file demo-projects/multi-stack-incident/services/payment-engine/main.py \
  --file demo-projects/multi-stack-incident/services/api-gateway/index.js \
  --file demo-projects/multi-stack-incident/services/billing/PaymentProcessor.java \
  --file demo-projects/multi-stack-incident/deployments/k8s/payment-deployment.yaml
```
*(Demonstrates that OpsGenome dynamically analyzes and extracts errors from physical disk files).*

---

## ☸️ Cluster 4 — Kubernetes & Docker Cluster Multi-Issue Auditor

### 🎤 What to Say to Judges:
> *"Even if an enterprise restricts an AI from writing directly to production clusters, OpsGenome audits all co-existing failure modes across namespaces and gives SREs exact copyable CLI commands and declarative GitOps YAML patches."*

### Run:
```bash
opsgenome multi-agent cluster-audit
```

#### 5 Simultaneous Failure Modes Diagnosed:
1. **CrashLoopBackOff (`payments-api-7c9d`):** Missing mandatory `DATABASE_URL` environment variable (*CRITICAL*).
2. **OOMKilled (`batch-worker-4e2b`):** 64Mi cgroup memory limit exceeded; Linux kernel sent Exit Code 137 (*HIGH*).
3. **SelectorMismatch (`frontend-gateway`):** Service `selector.app=web-v1` does not match active pod label `web-v2` (*HIGH*).
4. **ReadinessProbeFailed (`auth-service-89f1`):** Probe targets port 8081 while service listens on 9090 (*MEDIUM*).
5. **PortConflict (`redis-cache`):** Host port 6379 already bound by existing daemon (*MEDIUM*).

#### Outputs Produced:
* Exact, copyable `kubectl` commands (`kubectl set env`, `kubectl patch`).
* Docker Compose scaling & recovery commands.
* Declarative YAML unified diff patches ready for GitOps pull requests.

---

## 🌐 Cluster 5 — Web UI & Live Swarm Studio

1. Open **`http://localhost:8000`** in your browser.
2. Click **🤖 Swarm Studio** in the sidebar.

### 3 Interactive Swarm Modes to Showcase:
* **Mode 1 — Visual Cards & Diffs:**
  - 6 active specialist agent badges.
  - Inter-agent message thread.
  - Topological Kahn's Algorithm sequence cards.
  - Unified color-coded diff viewers with copy buttons.
* **Mode 2 — Live Terminal Console:**
  - Real-time terminal output mirroring the CLI experience.
  - One-click `📋 Copy Terminal Output` button.
* **Mode 3 — Raw Incident Logs:**
  - Direct live view of physical log files with syntax highlighting.
* **Cluster Multi-Issue Auditor View:**
  - Visual anomaly matrix table with severity tags, copyable CLI fixes, and YAML patches.

---

## ⚡ Cluster 6 — Large-Scale Log Triage (1 Million Lines)

### 🎤 What to Say to Judges:
> *"Real outages generate gigabytes of logs that overwhelm LLMs and cause token budget exhaustion. OpsGenome streams one million lines in constant memory while filtering noise before sending relevant information to the reasoning layer."*

### Run Benchmark:
```bash
pytest opsgenome/tests/test_scale_benchmark.py -v
```

#### Benchmark Results:
* **Throughput:** $1,000,000$ lines processed in **$14.7$ seconds** (~$68,000$ lines/second).
* **Memory Footprint:** **Constant memory** allocation ($0.00$ MB peak heap growth).
* **Constant LLM Context Size:** $<0.2\%$ prompt token variance between $10,000$ and $1,000,000$ log lines thanks to the Semantic Log Distiller.

---

## 🛡️ Cluster 7 — Chaos Testing & Automatic Transactional Rollback

When judges ask: *"What if the AI writes invalid code or a patch fails live verification?"*

### 1. Normal Mode (Validates Syntax & Commits):
```bash
opsgenome multi-agent chaos-test
```
* Output: `✔ TRANSACTION STATUS: VERIFIED_AND_COMMITTED`

### 2. Chaos Mode (Injects Intentional Syntax Error to Prove Rollback):
```bash
opsgenome multi-agent chaos-test --fail-verify
```
* **Watch OpsGenome:**
  1. Catches the syntax failure (`SyntaxError: invalid syntax`).
  2. Halts the transaction immediately.
  3. Initiates **Automatic Transactional Rollback**:
     - `↺ Rolled back index.js from index.js.bak (hash verified: True)`
     - `↺ Rolled back PaymentProcessor.java from PaymentProcessor.java.bak (hash verified: True)`
     - `↺ Rolled back main.py from main.py.bak (hash verified: True)`
     - `↺ Rolled back payment-deployment.yaml from payment-deployment.yaml.bak (hash verified: True)`
  4. Restores all files to their exact pre-incident state with verified SHA-256 hashes!

---

## 🔌 Running & Initializing the OpsGenome APIs

OpsGenome provides a complete REST and WebSocket API for headless automated integration:

### 1. Starting the API Server
You have two ways to run the API:

* **Method A: Unified API & Web Server (Recommended):**
  ```bash
  python3 run_frontend.py
  ```
  Runs on port `8000`. Serves both the Web App UI and all REST API endpoints.

* **Method B: Dedicated Standalone Daemon (Port 8765):**
  ```bash
  python3 -m opsgenome.cli.main daemon --host 127.0.0.1 --port 8765
  # Or simply:
  ./run_opsgenome.sh
  ```

### 2. Interactive Swagger UI (API Documentation)
Open **`http://localhost:8000/docs`** (or `http://localhost:8765/docs` if using standalone daemon) to view and test all endpoints interactively in your browser.

### 3. Key REST API Endpoints

#### Health & Status:
```bash
curl http://localhost:8000/api/v1/health
```

#### Swarm Operational Status & Registered Agents:
```bash
curl http://localhost:8000/api/v1/multi-agent/swarm-status
```

#### Trigger Multi-Agent Cross-Stack Analysis via API:
```bash
curl -X POST http://localhost:8000/api/v1/multi-agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"use_demo_incident": true}'
```

#### Trigger Kubernetes Cluster Multi-Issue Audit via API:
```bash
curl -X POST http://localhost:8000/api/v1/multi-agent/cluster-audit \
  -H "Content-Type: application/json" \
  -d '{"namespace": "payments"}'
```

#### AI Engine Status Check:
```bash
opsgenome doctor
```

---

## 🧪 Automated Test Suite Verification

### Run Multi-Agent Tests (7 tests):
```bash
pytest opsgenome/tests/test_multi_agent.py -v
```

### Run Full Test Suite (128 tests):
```bash
pytest opsgenome/tests/ -v
```
* **Result:** `128 passed, 0 failures, 100% pass rate.`

---

## 📌 Quick Command Cheat Sheet

| Task | Exact Command |
| :--- | :--- |
| **Start Web & API** | `python3 run_frontend.py` *(Opens port 8000)* |
| **Setup CLI Alias** | `alias opsgenome="./bin/opsgenome"` |
| **Doctor / Healthcheck**| `opsgenome doctor` |
| **Hero Multi-Agent Demo** | `python3 demo/run_multiagent_demo.py` |
| **Detailed Swarm Dialogue**| `opsgenome multi-agent analyze --demo` |
| **Physical File Analysis** | `opsgenome multi-agent analyze --file demo-projects/multi-stack-incident/services/payment-engine/main.py` |
| **Cluster Multi-Issue Audit**| `opsgenome multi-agent cluster-audit` |
| **Chaos Verification Test** | `opsgenome multi-agent chaos-test` |
| **Chaos Rollback Test** | `opsgenome multi-agent chaos-test --fail-verify` |
| **Single-File AI Auto-Fix**| `opsgenome fix demo-projects/multi-stack-incident/services/payment-engine/main.py` |
| **Scale Benchmark (1M lines)**| `pytest opsgenome/tests/test_scale_benchmark.py -v` |
| **Full Test Suite** | `pytest opsgenome/tests/ -v` |
| **Interactive API Docs** | `http://localhost:8000/docs` |

---

## 🧨 Golden Rule for the Presentation
> **DO NOT** spend the first 2 minutes explaining theory or slides.  
> Instead:  
> **Show the Failure** $\longrightarrow$ **Show the Agents** $\longrightarrow$ **Show the Reasoning** $\longrightarrow$ **Show the Security Check** $\longrightarrow$ **Show the Fix** $\longrightarrow$ **Show the Verification**.
