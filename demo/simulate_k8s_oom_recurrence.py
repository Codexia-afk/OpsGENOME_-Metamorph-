"""Demo Simulation 2: Recurrence Alerting, Earned Confidence Escalation & Systemic Drift.

Simulates:
1. Multiple historical occurrences of the same root cause across different engineers.
2. Confidence score rising organically from 0% (cold start) to 88% (HIGH confidence) with full provenance.
3. A live repeat alert arriving via webhook, triggering instant recurrence detection (<50ms).
4. Systemic Drift Detection identifying chronic architectural defect.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.prevention.bus_factor import BusFactorAnalyzer
from opsgenome.prevention.drift import DriftDetectionEngine
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.signal.filter import SignalFilter
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    CapturedEvent,
    Incident,
    IncidentStatus,
    StateSnapshot,
    TriggerType,
)


def run_recurrence_and_drift_simulation(db_path: str | None = None) -> None:
    db = DatabaseManager(db_path=db_path)
    filter_engine = SignalFilter()
    gen = RunbookGenerator(db=db, signal_filter=filter_engine)

    print("\n" + "=" * 70)
    print("⚡ [SIMULATION 2] Recurrence Alerting, Earned Confidence & Drift Radar")
    print("=" * 70)

    # 1. Seed 6 historical incidents on payments-service across 3 engineers over the past month
    engineers = ["sarah_principal_sre", "sarah_principal_sre", "alex_sre", "sarah_principal_sre", "marcus_devops", "sarah_principal_sre"]
    now = datetime.now(timezone.utc)

    for i, eng in enumerate(engineers):
        past_time = now - timedelta(days=(28 - i * 4))
        inc = Incident(
            id=f"inc-pay-{200 + i}",
            title=f"Payments Service Timeout & Latency Surge (Cycle #{i+1})",
            service="payments-service",
            environment="production",
            severity="P1",
            trigger_type=TriggerType.WEBHOOK_PAGERDUTY,
            status=IncidentStatus.RESOLVED,
            started_at=past_time,
            resolved_at=past_time + timedelta(minutes=18),
            resolved_by=eng,
            symptoms=[
                "504 Gateway Timeout across /api/v1/charge",
                "Postgres connection pool exhausted",
                "Container memory usage near limit",
            ],
            root_cause_category="Upstream Service Timeout / Connection Latency",
            summary=f"Resolved connection saturation and bumped container memory limit to 2Gi by {eng}.",
        )
        db.create_incident(inc)

        # Seed events for each (use real K8s collector if reachable)
        try:
            from opsgenome.watcher.k8s import K8sStateCollector
            _collector = K8sStateCollector(namespace="payments")
            _collector.connect()
            b_snap = _collector.capture_snapshot(incident_id=inc.id)
            a_snap = _collector.capture_snapshot(incident_id=inc.id)
        except Exception:
            b_snap = StateSnapshot(incident_id=inc.id, status_summary="Degraded 504 Gateway Timeout", is_healthy=False)
            a_snap = StateSnapshot(incident_id=inc.id, status_summary="Healthy 200 OK (Latency: 35ms)", is_healthy=True)

        ev1 = CapturedEvent(incident_id=inc.id, sequence_idx=0, command_redacted="kubectl get pods -n prod -l app=payments-service", exit_code=0)
        ev2 = CapturedEvent(incident_id=inc.id, sequence_idx=1, command_redacted="kubectl patch configmap payments-config --type merge -p '{\"data\":{\"DB_POOL_MAX\":\"50\"}}'", exit_code=0)
        ev3 = CapturedEvent(incident_id=inc.id, sequence_idx=2, command_redacted="kubectl patch deployment payments-service -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"}}}]}}}}'", exit_code=0, before_snapshot=b_snap, after_snapshot=a_snap)
        ev4 = CapturedEvent(incident_id=inc.id, sequence_idx=3, command_redacted="curl -I http://payments.internal/healthz", exit_code=0)

        for e in [ev1, ev2, ev3, ev4]:
            db.save_event(e)

        # Update runbook with earned confidence
        gen.generate_runbook_for_incident(
            incident=inc,
            events=[ev1, ev2, ev3, ev4],
            historical_count=i + 1,
            success_count=i + 1,
            escalation_count=1 if i == 2 else 0,
            other_engineers=engineers[: i + 1],
        )

    # 2. Add an auth-service incident to demonstrate bus factor
    for j in range(3):
        auth_inc = Incident(
            id=f"inc-auth-{100 + j}",
            title=f"Auth Gateway Token Validation Failure #{j+1}",
            service="auth-gateway",
            environment="production",
            severity="P2",
            status=IncidentStatus.RESOLVED,
            started_at=now - timedelta(days=10 - j * 3),
            resolved_at=now - timedelta(days=10 - j * 3) + timedelta(minutes=12),
            resolved_by="dave_security_lead",
            symptoms=["JWT verification error", "OIDC discovery cache stale"],
            root_cause_category="TLS Certificate Expiration & Ingress Handshake Failure",
        )
        db.create_incident(auth_inc)

    print(f"✔ Seeded {len(engineers) + 3} production resolution records into OpsGenome intelligence store.")

    # 3. Simulate New Incoming Alert & Instant Recurrence Detection
    incoming_alert = Incident(
        id="inc-live-999",
        title="CRITICAL: payments-service experiencing 504 Gateway Timeout spike",
        service="payments-service",
        environment="production",
        severity="P1",
        trigger_type=TriggerType.WEBHOOK_PAGERDUTY,
        status=IncidentStatus.ACTIVE,
        symptoms=["504 Gateway Timeout on checkout", "database connection pool latency"],
    )
    db.create_incident(incoming_alert)

    rec_engine = RecurrenceAlertEngine(db=db)
    match = rec_engine.check_recurrence(incoming_alert)

    print("\n" + "-" * 70)
    print("⚡ LIVE RECURRENCE ALERT (Sub-50ms Trigger):")
    print(f"• Matched Similarity: {int(match['similarity_score'] * 100)}%")
    print(f"• Runbook Surfaced: '{match['matched_runbook_title']}'")
    print(f"• Earned Confidence: {int(match['confidence_score'] * 100)}% ({match['confidence_level'].upper()})")
    print(f"• Provenance Trail: {match['provenance_trail']}")
    print(f"• Instant Remediation Commands:")
    for cmd in match["top_commands"]:
        print(f"    $ {cmd}")
    print("-" * 70)

    # 4. Systemic Drift Detection
    drift_engine = DriftDetectionEngine(db=db, recurrence_threshold=2)
    drift_reports = drift_engine.analyze_drift()
    print(f"\n🔍 SYSTEMIC DRIFT RADAR: Detected {len(drift_reports)} chronic architectural defects:")
    for rep in drift_reports:
        print(f"  • [{rep.severity}] {rep.service} -> '{rep.root_cause_category}' ({rep.incident_count} recurrences)")
        print(f"    Recommendation: {rep.backlog_recommendation[:90]}...")

    # 5. Bus Factor Analysis
    bus_analyzer = BusFactorAnalyzer(db=db)
    bus_metrics = bus_analyzer.analyze_services()
    print(f"\n👥 BUS FACTOR & TRIBAL KNOWLEDGE MATRIX:")
    for b in bus_metrics:
        print(f"  • Service: {b.service.ljust(18)} | Bus Factor: {b.bus_factor_score} | Top Expert: {b.top_expert} ({int(b.top_expert_share * 100)}%) | Risk: {b.risk_level.value.upper()}")


if __name__ == "__main__":
    run_recurrence_and_drift_simulation()
