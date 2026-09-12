"""Test Suite for Signal-vs-Noise Filtering and State Diffing."""

from datetime import datetime, timezone
import pytest
from opsgenome.signal.filter import SignalFilter
from opsgenome.signal.state_diff import StateSnapshotEngine, compute_state_delta
from opsgenome.storage.models import CapturedEvent, CausalStatus, Event, EventClassification, StateSnapshot


def test_state_delta_recovery():
    before = StateSnapshot(
        incident_id="inc-1",
        resource_type="k8s_pods",
        status_summary="payments-pod CrashLoopBackOff",
        is_healthy=False,
    )
    after = StateSnapshot(
        incident_id="inc-1",
        resource_type="k8s_pods",
        status_summary="payments-pod Running 1/1",
        is_healthy=True,
    )
    delta_str, is_recovery = compute_state_delta(before, after)
    assert is_recovery is True
    assert "RECOVERY" in delta_str
    assert "CrashLoopBackOff" in delta_str
    assert "Running" in delta_str


def test_signal_filter_scoring_pipeline():
    filter_engine = SignalFilter()

    before_fix_state = StateSnapshot(
        incident_id="inc-1", status_summary="CrashLoopBackOff", is_healthy=False
    )
    after_fix_state = StateSnapshot(
        incident_id="inc-1", status_summary="Running 1/1", is_healthy=True
    )

    events = [
        CapturedEvent(incident_id="inc-1", sequence_idx=0, command_redacted="ls -la", exit_code=0),
        CapturedEvent(incident_id="inc-1", sequence_idx=1, command_redacted="kubectl logs -n prod payments-service", exit_code=0),
        CapturedEvent(incident_id="inc-1", sequence_idx=2, command_redacted="kubectl apply -f bad_config.yaml", exit_code=1, stderr_summary="error: error parsing bad_config.yaml"),
        CapturedEvent(
            incident_id="inc-1",
            sequence_idx=3,
            command_redacted="kubectl patch deployment payments -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"}}}]}}}}'",
            exit_code=0,
            before_snapshot=before_fix_state,
            after_snapshot=after_fix_state,
        ),
        CapturedEvent(incident_id="inc-1", sequence_idx=4, command_redacted="curl -I http://payments.internal/health", exit_code=0),
    ]

    scored = filter_engine.process_events(events)

    # 1. Noise
    assert scored[0].status == CausalStatus.NOISE
    assert scored[0].causal_score <= 0.1

    # 2. Investigative
    assert scored[1].status == CausalStatus.INVESTIGATIVE

    # 3. Dead end (kept as negative knowledge!)
    assert scored[2].status == CausalStatus.DEAD_END
    assert scored[2].causal_score > 0.1

    # 4. Verified Fix
    assert scored[3].status == CausalStatus.VERIFIED_FIX
    assert scored[3].causal_score >= 0.85
    assert "RECOVERY" in scored[3].state_delta_summary


def test_recency_proximity_decay_variance():
    """Verifies that fix events closer to the final successful state check score higher (0.85 -> 0.93)."""
    filter_engine = SignalFilter()

    # Scenario A: Fix command is the LAST command (distance_from_end = 0)
    events_at_end = [
        Event(incident_id="inc-a", raw_command="kubectl describe pod", exit_code=0),
        Event(incident_id="inc-a", raw_command="kubectl logs app", exit_code=0),
        Event(incident_id="inc-a", raw_command="kubectl rollout undo deployment/app -n prod", exit_code=0),
    ]
    scored_a = filter_engine.process_events(events_at_end)
    fix_score_a = scored_a[2].signal_weight
    assert fix_score_a >= 0.90, f"Expected fix at resolution to score >= 0.90, got {fix_score_a}"

    # Scenario B: Fix command followed by 3 investigative/verification checks (distance_from_end = 3)
    events_earlier = [
        Event(incident_id="inc-b", raw_command="kubectl describe pod", exit_code=0),
        Event(incident_id="inc-b", raw_command="kubectl rollout undo deployment/app -n prod", exit_code=0),
        Event(incident_id="inc-b", raw_command="kubectl get pods", exit_code=0),
        Event(incident_id="inc-b", raw_command="kubectl logs app", exit_code=0),
        Event(incident_id="inc-b", raw_command="curl -I http://app/healthz", exit_code=0),
    ]
    scored_b = filter_engine.process_events(events_earlier)
    fix_score_b = scored_b[1].signal_weight

    # Assert variable output: Fix at final resolution scores higher than fix 3 steps earlier
    assert fix_score_a > fix_score_b, f"Expected fix_score_a ({fix_score_a}) > fix_score_b ({fix_score_b})"
    assert 0.85 <= fix_score_b <= fix_score_a <= 0.95
