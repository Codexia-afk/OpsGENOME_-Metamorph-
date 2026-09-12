"""OpsGenome Hackathon Core Loop Demo Script.

Implements the exact 6-step scenario:
1. Simulate Incident 1: Kubernetes pod CrashLoopBackOff caused by a ConfigMap change.
   Runs a realistic messy sequence of ~15 commands including 2-3 dead ends,
   ending in `kubectl rollout undo` that fixes it.
2. Auto-classify fix sequence, generate runbook with confidence "Not enough data yet (N=1)".
3. Simulate Incident 2: Same root cause pattern on a different day.
4. Surface Incident 1 runbook immediately at the start of Incident 2 (<50ms).
5. Resolve Incident 2 using suggested fix -> Confidence updates to "100% — 2 of 2".
6. Simulate Incident 3 (Root cause drift under same symptom) -> Show systemic drift & bus factor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sys
import time
from tabulate import tabulate
from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.prevention.bus_factor import BusFactorAnalyzer
from opsgenome.prevention.drift import DriftDetectionEngine
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.security.redactor import redact_event_payload
from opsgenome.signal.filter import SignalFilter
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    Event,
    Incident,
    IncidentStatus,
    StateSnapshot,
    TriggerSource,
)

# Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{BOLD}{CYAN}{'=' * 78}{RESET}")
    print(f"{BOLD}{CYAN}🚀 {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 78}{RESET}\n")


def run_demo():
    # Use a clean demo database
    demo_db_path = "./.opsgenome_data/demo_opsgenome.db"
    if os.path.exists(demo_db_path):
        os.remove(demo_db_path)

    db = DatabaseManager(db_path=demo_db_path)
    signal_filter = SignalFilter(high_signal_threshold=0.60)
    gen = RunbookGenerator(db=db, signal_filter=signal_filter)
    rec_engine = RecurrenceAlertEngine(db=db)

    # -------------------------------------------------------------------------
    # STEP 1: INCIDENT 1 (CrashLoopBackOff with messy 15-command sequence)
    # -------------------------------------------------------------------------
    print_header("STEP 1: INCIDENT 1 — Kubernetes Pod CrashLoopBackOff (Messy ~15 Commands)")
    print(f"{YELLOW}Trigger: Deployment revision caused CrashLoopBackOff on payments-service.{RESET}")
    print(f"{YELLOW}An engineer starts investigating in terminal with secret env vars, dead ends, and trials.{RESET}\n")

    inc1 = Incident(
        id="inc-k8s-001",
        title="CRITICAL: payments-service Pod CrashLoopBackOff",
        service="payments-service",
        environment="production",
        severity="P1",
        trigger_source=TriggerSource.MANUAL,
        status=IncidentStatus.OPEN,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=25),
        symptoms=["Pod CrashLoopBackOff", "HTTP 502 Bad Gateway across payment gateway"],
    )
    db.create_incident(inc1)

    # 15 realistic commands with noise, dead-ends, secret leakage, and verified fix
    raw_commands = [
        # Noise
        ("ls -la", 0, "total 32\ndrwxr-xr-x  app app", ""),
        ("pwd", 0, "/app/deployments/k8s", ""),
        # Investigation
        ("kubectl get pods -n production -l app=payments-service", 0, "NAME READY STATUS RESTARTS AGE\npayments-service-67f9b8 0/1 CrashLoopBackOff 5 8m", ""),
        ("kubectl describe pod payments-service-67f9b8 -n production", 0, "State: Waiting\n  Reason: CrashLoopBackOff\nLast State: Terminated (Exit Code 1)", ""),
        ("kubectl logs payments-service-67f9b8 -n production --tail=30", 0, "Error: Invalid database config parameter 'pool_timeout_ms'\npanic: configuration validation failed", ""),
        # Dead End 1: Restarting without fixing config
        ("kubectl rollout restart deployment/payments-service -n production", 0, "deployment.apps/payments-service restarted", ""),
        # Investigation check: still crashing!
        ("kubectl get pods -n production", 0, "payments-service-89a1c2 0/1 CrashLoopBackOff 1 15s", ""),
        # Dead End 2: Scaling up (exit code 1 due to resource quota)
        ("kubectl scale deployment payments-service --replicas=10 -n production", 1, "", "Error from server (Forbidden): exceeded quota: compute-resources, requested: 10"),
        # Secret Leakage during debug: Printing env with API keys & credentials
        ("kubectl exec -it payments-service-89a1c2 -n production -- env AWS_SECRET=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY API_KEY=d9F8q2Lx9zK1mP5vR8tY3wQ_7", 0, "DATABASE_URL=postgres://admin:P@ssword987@localhost:5432/payments", ""),
        # Dead End 3: Trying to patch wrong configmap key
        ("kubectl patch configmap payments-config -n production -p '{\"data\":{\"dummy_flag\":\"true\"}}'", 0, "configmap/payments-config patched", ""),
        # Diagnostic diff
        ("kubectl rollout history deployment/payments-service -n production", 0, "REVISION CHANGE-CAUSE\n1 Initial deployment\n2 Update configmap and connection limits", ""),
        ("kubectl describe configmap payments-config -n production", 0, "Data\n====\npool_timeout_ms: invalid_str_5000", ""),
        # VERIFIED FIX: Rolling back deployment
        ("kubectl rollout undo deployment/payments-service -n production", 0, "deployment.apps/payments-service rolled back", ""),
        # Verification check
        ("kubectl get pods -n production -l app=payments-service", 0, "NAME READY STATUS RESTARTS AGE\npayments-service-54a2b1 1/1 Running 0 20s", ""),
        ("curl -I -s http://payments.internal/healthz", 0, "HTTP/1.1 200 OK\nContent-Type: application/json", ""),
    ]

    events1: list[Event] = []
    print(f"{CYAN}Capturing terminal commands with IN-MEMORY SECRET REDACTION before storage:{RESET}")

    for idx, (raw_cmd, exit_c, stdout, stderr) in enumerate(raw_commands):
        # 1. Secret redaction before disk
        red_cmd, red_out, red_err, audits = redact_event_payload(raw_cmd, stdout, stderr)

        ev = Event(
            id=f"ev-1-{idx+1:02d}",
            incident_id=inc1.id,
            timestamp=inc1.started_at + timedelta(seconds=idx * 40),
            raw_command=red_cmd,
            exit_code=exit_c,
            stdout_snippet=red_out[:200],
            stderr_snippet=red_err[:200],
            tool_category="kubectl" if "kubectl" in red_cmd else ("network" if "curl" in red_cmd else "system"),
        )
        db.save_event(ev)
        events1.append(ev)

        if audits:
            print(f"  {RED}🔒 [SECRET REDACTED in memory]{RESET} {red_cmd[:65]}")
        else:
            print(f"  {DIM}[Captured #{idx+1:02d}]{RESET} $ {red_cmd[:60]}")

    # Snapshot before / after fix
    snap1 = StateSnapshot(
        id="snap-1",
        incident_id=inc1.id,
        event_id=events1[12].id,  # rollout undo
        resource_type="k8s_pod",
        before_state={"status": "CrashLoopBackOff", "ready": "0/1"},
        after_state={"status": "Running", "ready": "1/1"},
        diff_summary="State transition from CrashLoopBackOff to Running 1/1",
        is_healthy=True,
        status_summary="Running 1/1",
    )
    db.save_state_snapshot(snap1)

    # -------------------------------------------------------------------------
    # STEP 2: AUTO-CLASSIFY FIX SEQUENCE & GENERATE RUNBOOK (N=1)
    # -------------------------------------------------------------------------
    print_header("STEP 2: SIGNAL FILTER & AI REASONING — RUNBOOK SYNTHESIS (N=1)")
    inc1.status = IncidentStatus.RESOLVED
    inc1.ended_at = datetime.now(timezone.utc)
    inc1.resolved_by = "sarah_sre"

    chain1, runbook1 = gen.generate_runbook_for_incident(
        incident=inc1,
        events=events1,
        snapshots=[snap1],
        is_success=True,
    )

    print(f"{GREEN}✔ Signal Filter Evaluated {len(events1)} events:{RESET}")
    table_eval = []
    for e in events1:
        table_eval.append([
            e.id,
            e.raw_command[:45],
            e.exit_code,
            f"{e.signal_weight:.2f}",
            e.classification.value.upper(),
        ])
    print(tabulate(table_eval, headers=["Event ID", "Redacted Command", "Exit", "Signal Weight", "Classification"], tablefmt="simple"))

    print(f"\n{BOLD}{GREEN}✔ Synthesized Runbook:{RESET} {runbook1.title}")
    print(f"• Root Cause: {CYAN}{runbook1.root_cause_category}{RESET}")
    print(f"• Earned Confidence: {YELLOW}{runbook1.confidence_display}{RESET}")
    print(f"• Knowledge Lifecycle Status: {GREEN}{runbook1.knowledge_status.value.upper()}{RESET}")
    print(f"• Steps:")
    for s in runbook1.steps:
        print(f"    {BOLD}Step {s.step_number}:{RESET} {s.title} -> {CYAN}$ {s.command}{RESET}")
    print(f"• Known Dead Ends Captured: {len(runbook1.known_dead_ends or runbook1.negative_knowledge_dead_ends)}")
    for d in (runbook1.known_dead_ends or runbook1.negative_knowledge_dead_ends):
        print(f"    {RED}✘ Ruled Out:{RESET} {d.command} ({d.why_it_failed[:40]}...)")
    if runbook1.why_why_not:
        print(f"• Why / Why Not Decision Engine Grounding:")
        for wr in runbook1.why_why_not.why_reasons:
            print(f"    {GREEN}✔ Why:{RESET} {wr}")
        for wna in runbook1.why_why_not.why_not_alternatives:
            print(f"    {RED}✘ Why Not:{RESET} {wna['action']} ({wna['reason_rejected'][:50]}...)")

    # -------------------------------------------------------------------------
    # STEP 3 & 4: INCIDENT 2 — RECURRENCE DETECTED AT INTAKE (<50ms)
    # -------------------------------------------------------------------------
    print_header("STEP 3 & 4: INCIDENT 2 — RECURRENCE ALERTING BEFORE DEBUGGING FINISHES")
    print(f"{YELLOW}A week later, an alert fires for payments-service with matching CrashLoopBackOff symptoms.{RESET}")

    inc2 = Incident(
        id="inc-k8s-002",
        title="CRITICAL: payments-service CrashLoopBackOff following release",
        service="payments-service",
        environment="production",
        severity="P1",
        trigger_source=TriggerSource.MANUAL,
        status=IncidentStatus.OPEN,
        started_at=datetime.now(timezone.utc),
        symptoms=["Pod CrashLoopBackOff", "HTTP 502 Bad Gateway"],
    )
    db.create_incident(inc2)

    # Instant recurrence check
    t0 = time.time()
    recurrence_match = rec_engine.check_recurrence(inc2)
    elapsed_ms = (time.time() - t0) * 1000

    print(f"\n{BOLD}{YELLOW}⚡ INTAKE RECURRENCE ALERT TRIGGERED ({elapsed_ms:.1f}ms):{RESET}")
    print(f"• Matched Past Runbook: {CYAN}{recurrence_match['matched_runbook_title']}{RESET}")
    print(f"• Match Similarity: {GREEN}{int(recurrence_match['similarity_score'] * 100)}%{RESET}")
    print(f"• Current Confidence: {YELLOW}{recurrence_match['confidence_score'] * 100:.0f}% ({recurrence_match['confidence_level']}){RESET}")
    print(f"• Surfaced 1-Click Fix Command:")
    for c in recurrence_match["top_commands"]:
        print(f"    {BOLD}{GREEN}$ {c}{RESET}")

    # -------------------------------------------------------------------------
    # STEP 5: RESOLVE INCIDENT 2 WITH SUGGESTED FIX -> CONFIDENCE UPDATES TO 100% (2 of 2)
    # -------------------------------------------------------------------------
    print_header("STEP 5: RESOLVE INCIDENT 2 — EARNED CONFIDENCE RISES TO 100% (2 of 2)")
    print(f"{CYAN}Engineer applies the surfaced fix command directly:{RESET}")
    print(f"  $ kubectl rollout undo deployment/payments-service -n production")

    ev2_1 = Event(
        id="ev-2-01",
        incident_id=inc2.id,
        raw_command="kubectl rollout undo deployment/payments-service -n production",
        exit_code=0,
        stdout_snippet="deployment.apps/payments-service rolled back",
        tool_category="kubectl",
    )
    ev2_2 = Event(
        id="ev-2-02",
        incident_id=inc2.id,
        raw_command="kubectl get pods -n production -l app=payments-service",
        exit_code=0,
        stdout_snippet="payments-service-91a2 1/1 Running 0 10s",
        tool_category="kubectl",
    )
    db.save_event(ev2_1)
    db.save_event(ev2_2)

    inc2.status = IncidentStatus.RESOLVED
    inc2.ended_at = datetime.now(timezone.utc)
    inc2.resolved_by = "marcus_devops"

    chain2, runbook2 = gen.generate_runbook_for_incident(
        incident=inc2,
        events=[ev2_1, ev2_2],
        is_success=True,
    )

    print(f"\n{BOLD}{GREEN}✔ Incident 2 Resolved Successfully!{RESET}")
    print(f"• Updated Runbook: {runbook2.title} (v{runbook2.version})")
    print(f"• Success Uses: {runbook2.success_count} | Failures: {runbook2.failure_count}")
    print(f"• Earned Confidence Score: {BOLD}{GREEN}{runbook2.confidence_display}{RESET}")

    # -------------------------------------------------------------------------
    # STEP 6: SIMULATE INCIDENT 3 (ROOT CAUSE DRIFT UNDER SAME SYMPTOM) & DASHBOARD
    # -------------------------------------------------------------------------
    print_header("STEP 6: SYSTEMIC DRIFT RADAR & BUS FACTOR ANALYSIS")
    print(f"{YELLOW}Simulating Incident 3: A repeat symptom on payments-service caused by an OOMKilled memory limit.{RESET}")

    inc3 = Incident(
        id="inc-k8s-003",
        title="CRITICAL: payments-service Pod CrashLoopBackOff (OOM)",
        service="payments-service",
        environment="production",
        severity="P1",
        trigger_source=TriggerSource.MANUAL,
        status=IncidentStatus.RESOLVED,
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ended_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=45),
        resolved_by="sarah_sre",
        symptoms=["Pod CrashLoopBackOff", "Exit code 137 OOMKilled"],
        root_cause_category="Container Memory Limit Exhaustion (OOMKilled)",
    )
    db.create_incident(inc3)

    # Add auth incident for bus factor demonstration
    inc_auth = Incident(
        id="inc-auth-001",
        title="Auth Gateway TLS Handshake Error",
        service="auth-gateway",
        environment="production",
        severity="P1",
        status=IncidentStatus.RESOLVED,
        resolved_by="dave_security",
        root_cause_category="TLS Certificate Expiration & Ingress Handshake Failure",
    )
    db.create_incident(inc_auth)

    # 1. Systemic Drift
    drift_engine = DriftDetectionEngine(db=db, recurrence_threshold=2)
    drift_reports = drift_engine.analyze_drift()

    print(f"\n{BOLD}{RED}🔍 SYSTEMIC DRIFT DETECTED:{RESET}")
    drift_table = []
    for d in drift_reports:
        drift_table.append([d.service, d.root_cause_category, d.incident_count, d.severity, d.backlog_recommendation[:60] + "..."])
    print(tabulate(drift_table, headers=["Service", "Root Cause Category", "Recurrences", "Severity", "Backlog Action Item"], tablefmt="fancy_grid"))

    # 2. Bus Factor
    bus_analyzer = BusFactorAnalyzer(db=db)
    bus_metrics = bus_analyzer.analyze_services()

    print(f"\n{BOLD}{CYAN}👥 BUS FACTOR & TRIBAL KNOWLEDGE MATRIX:{RESET}")
    bus_table = []
    for b in bus_metrics:
        bus_table.append([b.service, b.bus_factor_score, b.top_expert, f"{int(b.top_expert_share * 100)}%", b.risk_level.value.upper() if hasattr(b.risk_level, 'value') else str(b.risk_level).upper(), b.recommendation[:50] + "..."])
    print(tabulate(bus_table, headers=["Service", "Bus Factor", "Top Expert", "Share", "Risk Level", "Recommendation"], tablefmt="fancy_grid"))

    print_header("CORE LOOP DEMO COMPLETE — ALL 6 STAGES VERIFIED!")


if __name__ == "__main__":
    run_demo()
