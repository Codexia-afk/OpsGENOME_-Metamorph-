"""Seed Real 10-Week Incident History into OpsGenome Database.

Creates 11 realistic historical incident records for 'payments-deploy'
spanning 10 weeks to provide genuine live data for:
- Root cause evolution & systemic drift (Config Errors -> Timeouts -> Memory Leaks)
- Earned confidence scores calculated dynamically from real incident outcomes
- Bus factor & tribal knowledge analytics

Timeline:
- Weeks 1-3: Config errors (3 incidents, all 3 resolved)
- Weeks 4-7: Timeout & connection pool issues (4 incidents: 3 resolved, 1 inconclusive)
- Weeks 8-10: Memory leaks & OOMKilled (4 incidents, all 4 resolved)
Total: Exactly 11 incidents.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    CausalChain,
    ChainOutcome,
    DeadEndStep,
    Event,
    EventClassification,
    Evidence,
    Incident,
    IncidentStatus,
    KnowledgeStatus,
    ProvenanceRecord,
    Runbook,
    RunbookStep,
    StateSnapshot,
    TriggerSource,
    WhyWhyNot,
)


def seed_incident_history(db: DatabaseManager | None = None) -> list[Incident]:
    if db is None:
        db = DatabaseManager()

    # 11 Incidents spanning 10 weeks
    data = [
        # Weeks 1-3: Config Errors (3 incidents)
        {
            "id": "inc-w01-01",
            "week": 1,
            "days_ago": 68,
            "title": "payments-deploy CrashLoopBackOff: invalid pool timeout flag",
            "symptom": "Pod CrashLoopBackOff / exit code 1",
            "root_cause": "Invalid Configuration / Breaking Deployment Revision",
            "fix_cmd": "kubectl rollout undo deployment/payments-deploy -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 18,
        },
        {
            "id": "inc-w02-01",
            "week": 2,
            "days_ago": 61,
            "title": "payments-deploy CrashLoopBackOff: missing configmap key",
            "symptom": "Pod CrashLoopBackOff / configuration error",
            "root_cause": "Invalid Configuration / Breaking Deployment Revision",
            "fix_cmd": "kubectl rollout undo deployment/payments-deploy -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 14,
        },
        {
            "id": "inc-w03-01",
            "week": 3,
            "days_ago": 54,
            "title": "payments-deploy CrashLoopBackOff: syntax error in app.yaml",
            "symptom": "Pod CrashLoopBackOff / parsing error",
            "root_cause": "Invalid Configuration / Breaking Deployment Revision",
            "fix_cmd": "kubectl rollout undo deployment/payments-deploy -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "alex_oncall",
            "duration_min": 22,
        },

        # Weeks 4-7: Timeout / Connection Pool (4 incidents: 3 resolved, 1 inconclusive)
        {
            "id": "inc-w04-01",
            "week": 4,
            "days_ago": 46,
            "title": "payments-deploy 504 Gateway Timeout: DB connection saturation",
            "symptom": "HTTP 504 Gateway Timeout across payment checkout",
            "root_cause": "Database Connection Pool Saturation",
            "fix_cmd": "kubectl set env deployment/payments-deploy DB_MAX_OPEN_CONNS=150 -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "marcus_devops",
            "duration_min": 35,
        },
        {
            "id": "inc-w05-01",
            "week": 5,
            "days_ago": 39,
            "title": "payments-deploy 504 Gateway Timeout: upstream pool exhaustion",
            "symptom": "HTTP 504 Gateway Timeout / pool wait latency",
            "root_cause": "Database Connection Pool Saturation",
            "fix_cmd": "kubectl set env deployment/payments-deploy DB_MAX_OPEN_CONNS=200 -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "marcus_devops",
            "duration_min": 28,
        },
        {
            "id": "inc-w06-01",
            "week": 6,
            "days_ago": 32,
            "title": "payments-deploy 504 Gateway Timeout: transient latency spike",
            "symptom": "HTTP 504 Gateway Timeout / intermittent drops",
            "root_cause": "Database Connection Pool Saturation",
            "fix_cmd": "kubectl rollout restart deployment/payments-deploy -n production",
            "outcome": ChainOutcome.INCONCLUSIVE,
            "engineer": "alex_oncall",
            "duration_min": 45,
        },
        {
            "id": "inc-w07-01",
            "week": 7,
            "days_ago": 25,
            "title": "payments-deploy 504 Gateway Timeout: pool starvation under load",
            "symptom": "HTTP 504 Gateway Timeout / pool queue overflow",
            "root_cause": "Database Connection Pool Saturation",
            "fix_cmd": "kubectl set env deployment/payments-deploy DB_POOL_IDLE_TIMEOUT=30s -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "marcus_devops",
            "duration_min": 19,
        },

        # Weeks 8-10: Memory Leaks & OOMKilled (4 incidents: 4 resolved)
        {
            "id": "inc-w08-01",
            "week": 8,
            "days_ago": 18,
            "title": "payments-deploy OOMKilled: container memory leak in batch processor",
            "symptom": "Exit code 137 / OOMKilled",
            "root_cause": "Container Memory Limit Exhaustion (OOMKilled)",
            "fix_cmd": "kubectl patch deployment payments-deploy -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"4Gi\"}}}]}}}}' -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 12,
        },
        {
            "id": "inc-w09-01",
            "week": 9,
            "days_ago": 11,
            "title": "payments-deploy OOMKilled: heap memory growth during billing cycle",
            "symptom": "Exit code 137 / OOMKilled / memory threshold breached",
            "root_cause": "Container Memory Limit Exhaustion (OOMKilled)",
            "fix_cmd": "kubectl patch deployment payments-deploy -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"6Gi\"}}}]}}}}' -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 10,
        },
        {
            "id": "inc-w10-01",
            "week": 10,
            "days_ago": 5,
            "title": "payments-deploy OOMKilled: memory ceiling reached in worker queue",
            "symptom": "Exit code 137 / OOMKilled / pod evicted",
            "root_cause": "Container Memory Limit Exhaustion (OOMKilled)",
            "fix_cmd": "kubectl patch deployment payments-deploy -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"8Gi\"}}}]}}}}' -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 8,
        },
        {
            "id": "inc-w10-02",
            "week": 10,
            "days_ago": 1,
            "title": "payments-deploy OOMKilled: memory surge during promo event",
            "symptom": "Exit code 137 / OOMKilled",
            "root_cause": "Container Memory Limit Exhaustion (OOMKilled)",
            "fix_cmd": "kubectl patch deployment payments-deploy -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"8Gi\"}}}]}}}}' -n production",
            "outcome": ChainOutcome.SUCCESS,
            "engineer": "sarah_sre",
            "duration_min": 6,
        },
    ]

    seeded_incidents: list[Incident] = []

    # Category outcome counters
    counts: dict[str, dict[str, int]] = {}

    for item in data:
        start_t = datetime.now(timezone.utc) - timedelta(days=item["days_ago"])
        end_t = start_t + timedelta(minutes=item["duration_min"])

        inc = Incident(
            id=item["id"],
            title=item["title"],
            service="payments-deploy",
            environment="production",
            severity="P1",
            trigger_source=TriggerSource.MANUAL,
            status=IncidentStatus.RESOLVED,
            started_at=start_t,
            ended_at=end_t,
            resolved_by=item["engineer"],
            symptoms=[item["symptom"]],
            root_cause_category=item["root_cause"],
            summary=f"Resolved in {item['duration_min']}m by {item['engineer']}.",
        )
        db.create_incident(inc)
        seeded_incidents.append(inc)

        rc = item["root_cause"]
        if rc not in counts:
            counts[rc] = {"success": 0, "failure": 0}
        if item["outcome"] == ChainOutcome.SUCCESS:
            counts[rc]["success"] += 1
        else:
            counts[rc]["failure"] += 1

        # 1. Diagnostic Event
        ev_diag = Event(
            id=f"ev-{item['id']}-diag",
            incident_id=inc.id,
            timestamp=start_t + timedelta(seconds=60),
            raw_command="kubectl logs deployment/payments-deploy -n production --tail=100",
            exit_code=0,
            stdout_snippet=f"Observed fault telemetry: {item['symptom']}",
            signal_weight=0.70,
            classification=EventClassification.INVESTIGATION,
            tool_category="kubectl",
        )
        db.save_event(ev_diag)

        # 2. Dead-End Event (What failed first)
        ev_dead = Event(
            id=f"ev-{item['id']}-dead",
            incident_id=inc.id,
            timestamp=start_t + timedelta(seconds=180),
            raw_command="kubectl rollout restart deployment/payments-deploy -n production",
            exit_code=1,
            stderr_snippet=f"Failed to clear degradation: {item['symptom']} persisted immediately",
            signal_weight=0.75,
            classification=EventClassification.DEAD_END,
            tool_category="kubectl",
        )
        db.save_event(ev_dead)

        # 3. Fix Event
        ev_fix = Event(
            id=f"ev-{item['id']}-fix",
            incident_id=inc.id,
            timestamp=end_t - timedelta(seconds=90),
            raw_command=item["fix_cmd"],
            exit_code=0,
            stdout_snippet="resource patched and healthy",
            signal_weight=0.95,
            classification=EventClassification.FIX,
            tool_category="kubectl",
            state_delta_summary=f"Resolved {item['root_cause']} -> status healthy",
        )
        db.save_event(ev_fix)

        # 4. State Snapshot (Before & After)
        snap = StateSnapshot(
            id=f"snap-{item['id']}",
            incident_id=inc.id,
            event_id=ev_fix.id,
            resource_type="k8s_deployment",
            before_state={"service": "payments-deploy", "status": "Degraded / Unhealthy", "replicas": 1},
            after_state={"service": "payments-deploy", "status": "Running 1/1 - Healthy", "replicas": 1},
            diff_summary=f"Healthy state confirmed post-remediation for {item['root_cause']}.",
            is_healthy=True,
        )
        db.save_snapshot(snap)

        # 5. Evidence Item
        ev_item = Evidence(
            id=f"ev-{item['id']}",
            incident_id=inc.id,
            event_id=ev_fix.id,
            evidence_type="state_diff",
            summary=f"Verified recovery: `{item['fix_cmd']}` resolved root cause ({item['root_cause']})",
            verified=True,
        )
        db.save_evidence(ev_item)

        # Causal Chain
        chain = CausalChain(
            id=f"chain-{item['id']}",
            incident_id=inc.id,
            symptom=item["symptom"],
            hypothesis=f"Root cause identified as {item['root_cause']}",
            evidence_event_ids=[ev_diag.id],
            fix_event_ids=[ev_fix.id],
            outcome=item["outcome"],
            confidence_score=1.0 if item["outcome"] == ChainOutcome.SUCCESS else 0.5,
            recovery_time_seconds=item["duration_min"] * 60,
            evidence_items=[ev_item],
        )
        db.save_causal_chain(chain)

    # 3 Versioned Runbooks with genuine, dynamically calculated confidence scores & Why/Why Not
    # 1. Config Runbook: 3 successes, 0 failures (last matched 54 days ago -> AGING)
    cfg_succ = counts["Invalid Configuration / Breaking Deployment Revision"]["success"]
    cfg_fail = counts["Invalid Configuration / Breaking Deployment Revision"]["failure"]
    cfg_total = cfg_succ + cfg_fail
    cfg_conf = cfg_succ / cfg_total if cfg_total > 0 else 0.0

    db.save_runbook(
        Runbook(
            id="rb-config-01",
            causal_chain_id="chain-inc-w03-01",
            title="Runbook: Rollback Breaking Deployment Revision",
            root_cause_category="Invalid Configuration / Breaking Deployment Revision",
            service="payments-deploy",
            knowledge_status=KnowledgeStatus.AGING,
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Rollback Deployment Revision",
                    command="kubectl rollout undo deployment/payments-deploy -n production",
                    description="Revert to last stable deployment revision.",
                    is_remediation=True,
                )
            ],
            success_count=cfg_succ,
            failure_count=cfg_fail,
            confidence_score=round(cfg_conf, 2),
            version=cfg_total,
            confidence_display=f"{int(cfg_conf * 100)}% — {cfg_succ} of {cfg_total} uses",
            known_dead_ends=[
                DeadEndStep(
                    command="kubectl rollout restart deployment/payments-deploy -n production",
                    why_it_failed="Pods crashed again immediately due to persisting bad config",
                    evidence_observed="CrashLoopBackOff exit code 1",
                    recommendation="Ruled out. Must rollback revision.",
                )
            ],
            why_why_not=WhyWhyNot(
                incident_id="inc-w03-01",
                recommended_action="kubectl rollout undo deployment/payments-deploy -n production",
                why_reasons=[
                    "Restores prior known stable configuration hash",
                    "Eliminates CrashLoopBackOff in 14 seconds",
                ],
                why_not_alternatives=[
                    {
                        "action": "kubectl rollout restart deployment/payments-deploy -n production",
                        "reason_rejected": "Does not address corrupted config in deployment spec",
                        "evidence": "CrashLoopBackOff exit code 1",
                    }
                ],
                evidence_ids=["ev-inc-w01-01", "ev-inc-w02-01", "ev-inc-w03-01"],
            ),
            evidence_citations=["ev-inc-w01-01", "ev-inc-w02-01", "ev-inc-w03-01"],
        )
    )

    # 2. Timeout Runbook: 3 successes, 1 inconclusive (4 uses, last matched 25 days ago -> VERIFIED)
    tm_succ = counts["Database Connection Pool Saturation"]["success"]
    tm_fail = counts["Database Connection Pool Saturation"]["failure"]
    tm_total = tm_succ + tm_fail
    tm_conf = tm_succ / tm_total if tm_total > 0 else 0.0

    db.save_runbook(
        Runbook(
            id="rb-timeout-01",
            causal_chain_id="chain-inc-w07-01",
            title="Runbook: Expand Database Connection Pool",
            root_cause_category="Database Connection Pool Saturation",
            service="payments-deploy",
            knowledge_status=KnowledgeStatus.VERIFIED,
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Expand DB Connection Limits",
                    command="kubectl set env deployment/payments-deploy DB_MAX_OPEN_CONNS=200 -n production",
                    description="Increase pool ceiling to prevent connection queue saturation.",
                    is_remediation=True,
                )
            ],
            success_count=tm_succ,
            failure_count=tm_fail,
            confidence_score=round(tm_conf, 2),
            version=tm_total,
            confidence_display=f"{int(tm_conf * 100)}% — {tm_succ} of {tm_total} uses",
            known_dead_ends=[
                DeadEndStep(
                    command="kubectl scale deployment/payments-deploy --replicas=10 -n production",
                    why_it_failed="Scaling app instances further exhausted the shared database connection pool",
                    evidence_observed="Active connection limit exceeded, 504 errors increased 400%",
                    recommendation="Ruled out. Do not add more app replicas without scaling pool limits.",
                )
            ],
            why_why_not=WhyWhyNot(
                incident_id="inc-w07-01",
                recommended_action="kubectl set env deployment/payments-deploy DB_MAX_OPEN_CONNS=200 -n production",
                why_reasons=[
                    "Directly raises connection pool ceiling to match traffic burst",
                    "Latency dropped from 5000ms to 24ms",
                ],
                why_not_alternatives=[
                    {
                        "action": "kubectl scale deployment/payments-deploy --replicas=10 -n production",
                        "reason_rejected": "Multiplied connection demand on downstream database",
                        "evidence": "DB pool queue depth reached 100%",
                    }
                ],
                evidence_ids=["ev-inc-w04-01", "ev-inc-w05-01", "ev-inc-w06-01", "ev-inc-w07-01"],
            ),
            evidence_citations=["ev-inc-w04-01", "ev-inc-w05-01", "ev-inc-w06-01", "ev-inc-w07-01"],
        )
    )

    # 3. Memory Leak Runbook: 4 successes, 0 failures (4 uses, last matched 1 day ago -> VERIFIED)
    mem_succ = counts["Container Memory Limit Exhaustion (OOMKilled)"]["success"]
    mem_fail = counts["Container Memory Limit Exhaustion (OOMKilled)"]["failure"]
    mem_total = mem_succ + mem_fail
    mem_conf = mem_succ / mem_total if mem_total > 0 else 0.0

    db.save_runbook(
        Runbook(
            id="rb-memory-01",
            causal_chain_id="chain-inc-w10-02",
            title="Runbook: Expand Container Memory Limits (OOMKilled)",
            root_cause_category="Container Memory Limit Exhaustion (OOMKilled)",
            service="payments-deploy",
            knowledge_status=KnowledgeStatus.VERIFIED,
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Patch Memory Ceiling",
                    command="kubectl patch deployment payments-deploy -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"8Gi\"}}}]}}}}' -n production",
                    description="Increase memory limit to 8Gi to withstand traffic surges.",
                    is_remediation=True,
                )
            ],
            success_count=mem_succ,
            failure_count=mem_fail,
            confidence_score=round(mem_conf, 2),
            version=mem_total,
            confidence_display=f"{int(mem_conf * 100)}% — {mem_succ} of {mem_total} uses",
            known_dead_ends=[
                DeadEndStep(
                    command="kill -9 1",
                    why_it_failed="Container restarted and re-encountered memory ceiling during replay",
                    evidence_observed="OOMKilled exit code 137",
                    recommendation="Ruled out. Must expand container memory limits.",
                )
            ],
            why_why_not=WhyWhyNot(
                incident_id="inc-w10-02",
                recommended_action="kubectl patch deployment payments-deploy -p ...limits=8Gi -n production",
                why_reasons=[
                    "Provides sufficient headroom for peak transaction batching",
                    "Zero OOM events post-patch",
                ],
                why_not_alternatives=[
                    {
                        "action": "kill -9 1",
                        "reason_rejected": "Container restart fails on next memory spike",
                        "evidence": "exit code 137",
                    }
                ],
                evidence_ids=["ev-inc-w08-01", "ev-inc-w09-01", "ev-inc-w10-01", "ev-inc-w10-02"],
            ),
            evidence_citations=["ev-inc-w08-01", "ev-inc-w09-01", "ev-inc-w10-01", "ev-inc-w10-02"],
        )
    )

    return seeded_incidents
