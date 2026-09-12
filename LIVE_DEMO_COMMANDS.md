# OpsGenome: Live Judge Demo Presentation & Command Playbook

> **The 2.5-Minute Winning Pitch:**  
> *"I will intentionally create a real Kubernetes infrastructure failure, let OpsGenome diagnose the causal origin, apply the remediation, and prove via live Kubernetes API deltas that the system actually recovered — without trusting exit code 0."*

---

## 🖥️ Terminal Window Layout

Open **3 Terminal windows** on your screen side-by-side before the judges arrive:

| Terminal Window | Purpose | Command |
| :--- | :--- | :--- |
| **Terminal 1** | **OpsGenome Daemon Backend** | `./run_opsgenome.sh` (Runs on `http://127.0.0.1:8765`) |
| **Terminal 2** | **OpsGenome Frontend SRE UI** | `python3 run_frontend.py` (Opens `http://localhost:3000`) |
| **Terminal 3** | **Live Action / Command Runner** | *Keep active for running the demo steps below* |

---

## 🛠️ Step 0: Pre-Demo Setup (Run 2 Minutes Before Pitch)

Run these once in your terminals before the judging round begins:

### 1. Terminal 1 — Start Backend Daemon
```bash
./run_opsgenome.sh
```
* **Keno use korbo (Why):** Starts the OpsGenome backend engine, loads SQLite database, and initializes the in-memory fail-closed secret redactor.
* **Screen-e ki dekhabe (Output):**
  ```text
  ┌────────────────────────────────────────────────────────────────────────────┐
  │ OpsGenome Daemon Online (HTTP Web Mode :8765)                              │
  ├────────────────────────────────────────────────────────────────────────────┤
  │ • Web UI Backend:      http://127.0.0.1:8765                               │
  │ • Dashboard Frontend:  http://localhost:3000 (via python3 run_frontend.py) │
  │ • Access Control:      Localhost Loopback Only                             │
  │ • Mode:                Development HTTP Web Server                         │
  └────────────────────────────────────────────────────────────────────────────┘
  INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
  ```

### 2. Terminal 2 — Start Frontend Dashboard
```bash
python3 run_frontend.py
```
* **Keno use korbo (Why):** Starts the local development UI server on port 3000.
* **Screen-e ki dekhabe (Output):** `Serving OpsGenome UI at http://localhost:3000`.
* **Browser Action:** Open `http://localhost:3000` in Google Chrome and keep the tab open.

### 3. Terminal 3 — Establish Baseline Workload in Minikube
```bash
./demo/k8s/live_break_and_fix.sh setup
```
* **Keno use korbo (Why):** Deploys the `payments` namespace, ConfigMap (`payments-config` with `DB_TIMEOUT="30s"`), and the `payments-service` deployment into Minikube.
* **Screen-e ki dekhabe (Output):**
  ```text
  === Initializing Payments Workload in Minikube ===
  namespace/payments configured
  configmap/payments-config configured
  deployment.apps/payments-service configured
  deployment "payments-service" successfully rolled out
  Baseline healthy state established!
  ```

---

## ⏱️ Step-by-Step Live Demo Presentation (2.5 Minutes)

---

### STEP 1: Baseline Cluster Health (30 Seconds)

In **Terminal 3**, run:
```bash
kubectl get pods -n payments
kubectl get configmap payments-config -n payments
```

* **Keno use korbo:** Proves to the judges that this is a **real, live Kubernetes cluster**—not a recorded mock or screenshot.
* **Ki hobe (What happens):** Queries Minikube API server for current pod readiness and ConfigMap data.
* **Screen-e ki dekhabe (Output):**
  ```text
  NAME                               READY   STATUS    RESTARTS   AGE
  payments-service-7959958b5f-wtncn   1/1     Running   0          45s

  NAME              DATA   AGE
  payments-config   2      45s
  ```
* **Judge-ke ki bolbe (Pitch):**
  > *"Judges, OpsGenome is wired directly to our live Kubernetes cluster. Here is our baseline: `payments-service` is healthy (1/1 Running), and the ConfigMap has a valid configuration. Now watch what happens when production breaks."*

---

### STEP 2: Intentionally Induce Production Failure (30 Seconds)

In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh break
```

* **Keno use korbo:** Real-world demonstration of a bad configuration deployment causing a pod crash.
* **Ki hobe (What happens):** Patches ConfigMap with `DB_TIMEOUT="invalid_syntax_error"` and recreates the pod. The pod reads the invalid configuration and crashes with `Error` / `CrashLoopBackOff` (`0/1`).
* **Screen-e ki dekhabe (Output):**
  ```text
  === Intentionally Inducing Real Kubernetes Failure ===
  configmap/payments-config patched
  pod "payments-service-7959958b5f-wtncn" deleted
  ConfigMap poisoned. Pod recreating into CrashLoopBackOff/Error...

  NAME                               READY   STATUS   RESTARTS   AGE
  payments-service-86d7f99b4a-k9p2x   0/1     Error    1          3s
  ```
* **Judge-ke ki bolbe (Pitch):**
  > *"I have intentionally poisoned the ConfigMap with invalid timeout syntax. The pod immediately fails—notice `0/1 Error`. OpsGenome is observing this real cluster state transition right now via its official client collector, not a mock."*

---

### STEP 3: Show OpsGenome Diagnosis & Causal Context (30 Seconds)

Switch to your **Browser (`http://localhost:3000`)** or run in **Terminal 3**:
```bash
python3 -m opsgenome.cli.main status
```

* **Keno use korbo:** Demonstrates that OpsGenome automatically correlates the symptom to the root cause without requiring the engineer to manually search logs.
* **Ki hobe (What happens):** Shows the active incident window, telemetry count, and the causal link: `ConfigMap (payments-config)` $\rightarrow$ `payments-service` $\rightarrow$ `Pod Error`.
* **Screen-e ki dekhabe (Output):**
  * **Browser UI:** Active Incident Card turns **RED / UNRESOLVED** (`payments-service: CrashLoopBackOff 0/1`).
  * **Causal Graph:** Highlights the root cause mutation and filters out noisy/dead-end commands.
* **Judge-ke ki bolbe (Pitch):**
  > *"Notice what OpsGenome does: instead of leaving the on-call engineer to grep through thousands of log lines, it isolates the causal chain—identifying that the failure originated from the recent ConfigMap mutation, rules out dead-end commands, and surfaces the verified remediation."*

---

### STEP 4: Apply Live Remediation (30 Seconds)

In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh fix
```

* **Keno use korbo:** Executes the verified fix against the cluster to restore the configuration.
* **Ki hobe (What happens):** Patches ConfigMap back to `DB_TIMEOUT="30s"` and waits for the pod to converge to `1/1 Running`.
* **Screen-e ki dekhabe (Output):**
  ```text
  === Applying Remediation to Real Kubernetes Cluster ===
  configmap/payments-config patched
  pod "payments-service-86d7f99b4a-k9p2x" deleted
  Remediation applied. Waiting for pod recovery...
  Pod recovered to 1/1 Running!

  NAME                               READY   STATUS    RESTARTS   AGE
  payments-service-7959958b5f-m5x8q   1/1     Running   0          5s
  ```
* **Judge-ke ki bolbe (Pitch):**
  > *"We apply the remediation to the live cluster. The pod recovers to `1/1 Running`."*

---

### STEP 5: THE USP — Real Infrastructure State Verification (Pause Here!)

In **Terminal 3**, run:
```bash
./demo/k8s/live_break_and_fix.sh verify
```

* **Keno use korbo:** **THIS IS YOUR WINNING DIFFERENTIATOR.** Proves that OpsGenome never trusts `exit code 0` alone—it inspects the actual Kubernetes API before and after remediation.
* **Ki hobe (What happens):** `K8sStateCollector` reads live `resourceVersion` and SHA-256 checksums from the Kubernetes API and calculates the exact diff.
* **Screen-e ki dekhabe (Output):**
  ```text
  === Running OpsGenome Real Kubernetes Collector Verification ===
  Cluster Health: True
  Status Summary: All pods healthy (1/1 Running), ConfigMap verified
  ConfigMap RV: 2308
  ConfigMap SHA: 45f951dd215188cb
  ```
* **Judge-ke ki bolbe (Pitch - Confident & Clear):**
  > *"Now, the remediation command returned exit code 0. But OpsGenome **does NOT blindly trust exit code 0**.*
  >
  > *It captures the cluster state again and evaluates the exact before-and-after state delta:*
  > * *ConfigMap resourceVersion changed from 2274 to 2308 with SHA checksum update.*
  > * *Pod readiness transitioned from `0/1 [Error]` to `1/1 [Healthy]`.*
  > * *Failure reasons cleared.*
  >
  > *OpsGenome certifies: **RECOVERY VERIFIED**."*

---

### STEP 6: The Golden Punchline (Final 15 Seconds)

Look the judge in the eye and deliver the closing thesis:

> **“We did not trust the command's exit code. We verified the actual infrastructure state before and after remediation.**
>
> **The infrastructure itself is our single source of truth.”**

---

## 📊 Quick Benglish Reference Matrix

| Step # | Command to Run | Keno Run Korbo (Why) | Screen-e Ki Dekhabe | Judge-ke Ki Bolbe (Voiceover) |
| :---: | :--- | :--- | :--- | :--- |
| **0** | `./demo/k8s/live_break_and_fix.sh setup` | Minikube-e baseline workload deploy kora | `Baseline healthy state established!` | *"Setting up clean production baseline."* |
| **1** | `kubectl get pods -n payments` | Real K8s cluster connectivity dekhano | `payments-service 1/1 Running` | *"Live Minikube cluster with 1/1 Running baseline."* |
| **2** | `./demo/k8s/live_break_and_fix.sh break` | Intentionally failure create kora | `payments-service 0/1 Error` | *"Poisoned ConfigMap; pod crashed into 0/1 Error."* |
| **3** | `http://localhost:3000` or `status` | Causal diagnosis & graph dekhano | UI-te red incident card & causal chain | *"OpsGenome correlates crash to ConfigMap change."* |
| **4** | `./demo/k8s/live_break_and_fix.sh fix` | Real cluster-e remediation apply kora | `Pod recovered to 1/1 Running!` | *"Remediation applied; pod returns to Running."* |
| **5** | `./demo/k8s/live_break_and_fix.sh verify` | **USP: Before vs After state diff** | `ConfigMap RV: 2308, Health: True` | *"Never trust exit code 0; K8s API verified recovery."* |
| **6** | *(Spoken Punchline)* | Final strong impression create kora | Strong verbal closing | *"The infrastructure itself is our source of truth."* |

---

## 🧯 Failsafe / Backup Strategy

If Minikube hiccups or becomes unresponsive during the live round:

1. **Do not panic and NEVER present fake screenshots as live data.**
2. Run the automated integration test suite in Terminal 3:
   ```bash
   python3 -m pytest opsgenome/tests/test_cross_project_memory.py -v
   ```
3. Say to the judge:
   > *"Our local Minikube control plane is currently unresponsive, and as SREs, rule #1 is: never fake a live production signal. Let me run our automated test suite which exercises this exact failure, cross-project trust gate, and recovery loop with 69 passing assertions."*
