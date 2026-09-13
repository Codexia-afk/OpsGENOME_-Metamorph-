"""Demo Simulation 1: Payments Service Cascading Outage.

Simulates a real-world high-severity incident:
1. PagerDuty webhook fires (504 Gateway Timeouts on payments).
2. Engineer runs investigative commands (logs, pod inspection).
3. Engineer attempts a dead-end fix (restarting proxy without fixing DB connection pool).
4. Engineer discovers pool saturation and applies correct ConfigMap & memory limit patch.
5. Resource state transitions from degraded -> healthy.
6. OpsGenome generates causal graph, earned confidence, provenance trail, and structured runbook.
"""

from __future__ import annotations

from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.signal.filter import SignalFilter
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    CapturedEvent,
    Incident,
    IncidentStatus,
    StateSnapshot,
    TriggerType,
)


def run_payments_outage_simulation(db_path: str | None = None) -> Incident:
    db = DatabaseManager(db_path=db_path)
    filter_engine = SignalFilter()
    gen = RunbookGenerator(db=db, signal_filter=filter_engine)

    print("\n" + "=" * 70)
    print("🚀 [SIMULATION 1] Payments Service Outage (Initial Memory Creation)")
    print("=" * 70)

    # 1. Intake
    incident = Incident(
        id="inc-pay-101",
        title="CRITICAL: Payments Service 504 Gateway Timeouts & Pod CrashLoop",
        service="payments-service",
        environment="production",
        severity="P1",
        trigger_type=TriggerType.WEBHOOK_PAGERDUTY,
        status=IncidentStatus.ACTIVE,
        symptoms=[
            "504 Gateway Timeout across /api/v1/charge",
            "p99 latency spiked to 14.2s",
            "Postgres connection pool exhausted (active_connections=100/100)",
        ],
        metadata={"pagerduty_incident_id": "PD-98421", "urgency": "high"},
    )
    db.create_incident(incident)
    print(f"✔ Webhook Auto-Triggered: {incident.title} (ID: {incident.id})")

    # 2. Terminal activity sequence (query real K8s collector if cluster is reachable)
    try:
        from opsgenome.watcher.k8s import K8sStateCollector
        collector = K8sStateCollector(namespace="payments")
        collector.connect()
        unhealthy_state = collector.capture_snapshot(incident_id=incident.id)
        # Note: In real cluster, healthy state is captured following remediation
        healthy_state = collector.capture_snapshot(incident_id=incident.id)
    except Exception:
        unhealthy_state = StateSnapshot(
            incident_id=incident.id,
            resource_type="k8s_pods",
            status_summary="payments-service-7f4c 0/1 CrashLoopBackOff | HTTP 504 Gateway Timeout",
            is_healthy=False,
        )
        healthy_state = StateSnapshot(
            incident_id=incident.id,
            resource_type="k8s_pods",
            status_summary="payments-service-7f4c 1/1 Running | HTTP 200 OK (Latency: 42ms)",
            is_healthy=True,
        )

    commands_data = [
        # Step 0: Noise
        ("ls -la", 0, 10, "system", "", "", None, None),
        # Step 1: Investigation
        ("kubectl get pods -n prod -l app=payments-service", 0, 140, "kubectl", "NAME READY STATUS RESTARTS\npayments-7f4c 0/1 CrashLoopBackOff 4", "", None, None),
        # Step 2: Investigation (logs)
        ("kubectl logs -n prod -l app=payments-service --tail=50", 0, 210, "kubectl", "FATAL: remaining connection slots are reserved for non-replication superuser connections\nError: connection pool exhausted after 30000ms", "", None, None),
        # Step 3: Dead End 1 (Restarting without config change)
        ("kubectl rollout restart deployment/payments-service -n prod", 0, 1200, "kubectl", "deployment.apps/payments-service restarted", "", unhealthy_state, unhealthy_state),
        # Step 4: Dead End 2 (Trying invalid CPU scale)
        ("kubectl scale deployment payments-service --replicas=20 -n prod", 1, 80, "kubectl", "", "error: max cluster CPU quota exceeded (requested 20, limit 12)", None, None),
        # Step 5: Remediation Fix 1 (Patching connection pool in configmap)
        ("kubectl patch configmap payments-config -n prod --type merge -p '{\"data\":{\"DB_POOL_MAX\":\"50\",\"DB_TIMEOUT_MS\":\"5000\"}}'", 0, 320, "kubectl", "configmap/payments-config patched", "", None, None),
        # Step 6: Remediation Fix 2 (Increasing container memory limit to prevent OOM on connection surge)
        ("kubectl patch deployment payments-service -n prod -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"}}}]}}}}'", 0, 450, "kubectl", "deployment.apps/payments-service patched", "", unhealthy_state, healthy_state),
        # Step 7: Verification
        ("curl -I -s https://payments.internal.net/healthz", 0, 45, "network", "HTTP/1.1 200 OK\nX-Pool-Active: 18/50\nX-Response-Time: 38ms", "", None, healthy_state),
    ]

    events: list[CapturedEvent] = []
    for seq, (cmd, exit_c, dur, tool, stdout, stderr, b_snap, a_snap) in enumerate(commands_data):
        ev = CapturedEvent(
            incident_id=incident.id,
            sequence_idx=seq,
            command_raw=cmd,
            command_redacted=cmd,
            exit_code=exit_c,
            duration_ms=dur,
            tool_category=tool,
            stdout_summary=stdout,
            stderr_summary=stderr,
            before_snapshot=b_snap,
            after_snapshot=a_snap,
        )
        db.save_event(ev)
        events.append(ev)

    print(f"✔ Recorded {len(events)} terminal events with exit-codes, state snapshots & diffs.")

    # 3. Resolve & Synthesize Runbook
    incident.status = IncidentStatus.RESOLVED
    incident.resolved_by = "sarah_principal_sre"
    db.create_incident(incident)

    chain, runbook = gen.generate_runbook_for_incident(
        incident=incident,
        events=events,
        historical_count=1,
        success_count=1,
        escalation_count=0,
    )

    print(f"✔ Intelligence Graph Built: {len(events)} nodes mapped.")
    print(f"✔ Synthesized Runbook: '{runbook.title}' (v{runbook.version})")
    print(f"✔ Earned Confidence: {int(runbook.earned_confidence_score * 100)}% ({runbook.confidence_level.value.upper()})")
    print(f"✔ Provenance: {runbook.provenance.provenance_trail_text}")
    print(f"✔ Negative Knowledge Captured: {len(runbook.negative_knowledge_dead_ends)} dead-end branches.")

    return incident


if __name__ == "__main__":
    run_payments_outage_simulation()
