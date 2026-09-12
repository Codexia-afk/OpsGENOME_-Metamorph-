"""Test Suite for Deterministic Why/Why Not Engine and Evidence Extraction."""

import pytest
from opsgenome.signal.causal_chain import CausalChainExtractor
from opsgenome.storage.models import CapturedEvent, CausalStatus, StateSnapshot


def test_causal_chain_extractor_evidence_and_why_why_not():
    events = [
        CapturedEvent(
            incident_id="inc-test-1",
            raw_command="kubectl logs deployment/payments-worker -n payments",
            exit_code=0,
            stdout_snippet="ERROR 504: Database pool saturated with 100 active connections",
            status=CausalStatus.INVESTIGATIVE,
            signal_weight=0.65,
        ),
        CapturedEvent(
            incident_id="inc-test-1",
            raw_command="kubectl rollout restart deployment/payments-worker -n payments",
            exit_code=1,
            stderr_snippet="CrashLoopBackOff: pool exhaustion reoccurred immediately",
            status=CausalStatus.DEAD_END,
            signal_weight=0.75,
        ),
        CapturedEvent(
            incident_id="inc-test-1",
            raw_command="kubectl scale deployment/postgres-bouncer --replicas=3 -n payments",
            exit_code=0,
            stdout_snippet="deployment.apps/postgres-bouncer scaled",
            status=CausalStatus.VERIFIED_FIX,
            signal_weight=0.92,
            state_delta_summary="Replicas scaled 1 -> 3, connection pool capacity +200%",
        ),
        CapturedEvent(
            incident_id="inc-test-1",
            raw_command="curl -s http://payments.internal/health",
            exit_code=0,
            stdout_snippet='{"status": "ok", "latency_ms": 14}',
            status=CausalStatus.INVESTIGATIVE,
            causal_score=0.90,
            signal_weight=0.85,
        ),
    ]

    snapshots = [
        StateSnapshot(
            incident_id="inc-test-1",
            resource_type="k8s_deployment",
            before_state={"replicas": 1, "healthy": 0},
            after_state={"replicas": 3, "healthy": 3},
            diff_summary="Replicas: 1 -> 3 (all healthy)",
            is_healthy=True,
        )
    ]

    result = CausalChainExtractor.extract(events, snapshots)

    # 1. Verification of extracted parts
    assert len(result["remediation_steps"]) == 1
    assert "postgres-bouncer" in result["remediation_steps"][0].command

    assert len(result["dead_ends"]) == 1
    assert "rollout restart" in result["dead_ends"][0].command

    assert len(result["verification_steps"]) == 1
    assert "curl" in result["verification_steps"][0]

    # 2. Evidence extraction verification
    evidence_items = result["evidence_items"]
    assert len(evidence_items) >= 4
    # Check that failed command produced negative evidence
    fail_ev = [e for e in evidence_items if not e.verified]
    assert len(fail_ev) == 1
    assert "CrashLoopBackOff" in fail_ev[0].summary

    # Check that state snapshot diff was recorded
    snap_ev = [e for e in evidence_items if e.evidence_type == "state_diff" and "k8s_deployment" in e.summary]
    assert len(snap_ev) == 1

    # 3. Why / Why Not decision model verification
    wwn = result["why_why_not"]
    assert wwn is not None
    assert "scale deployment/postgres-bouncer" in wwn.recommended_action
    assert len(wwn.why_not_alternatives) == 1
    assert "rollout restart" in wwn.why_not_alternatives[0]["action"]
    assert "CrashLoopBackOff" in wwn.why_not_alternatives[0]["reason_rejected"]
    assert len(wwn.evidence_ids) == len(evidence_items)
