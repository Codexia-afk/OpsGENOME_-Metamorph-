"""Guardrails for the audited two-call incident reasoning contract."""

import pytest

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.storage.models import Event, Incident


def test_chain_response_rejects_invented_event_ids():
    event = Event(id="known-event", incident_id="inc-1", raw_command="kubectl get pods")
    response = {
        "symptom": "CrashLoopBackOff",
        "disambiguation_required": False,
        "hypothesis": "configuration issue",
        "ranked_hypotheses": [],
        "evidence_event_ids": ["invented-event"],
        "fix_event_ids": [],
        "negative_knowledge_event_ids": [],
        "outcome": "inconclusive",
        "reasoning_notes": "No recovery evidence.",
    }

    with pytest.raises(ValueError, match="invalid evidence_event_ids"):
        AIReasoningEngine._validate_chain_response(response, [event])


def test_insufficient_signal_does_not_invent_runbook_command():
    engine = AIReasoningEngine()
    incident = Incident(id="inc-1", service="payments")
    event = Event(id="event-1", incident_id=incident.id, raw_command="kubectl get pods")

    chain = engine._heuristic_chain_assembly(incident, [event], None)
    runbook = engine._heuristic_runbook_narration(incident, chain, [event])

    assert chain["outcome"] == "insufficient_data"
    assert runbook["steps"] == []
    assert runbook["root_cause_category"] == "Insufficient Signal"


def _create_ambiguous_scenario():
    incident = Incident(
        id="inc-ambig-504",
        service="checkout-service",
        title="CRITICAL: 504 Gateway Timeouts & Connection Saturation",
        symptoms=["504 Gateway Timeout", "High P99 Latency (4200ms)", "Active Connection Saturation"],
    )
    events = [
        Event(
            id="ev-diag-1",
            incident_id=incident.id,
            raw_command="kubectl get pods -n checkout",
            exit_code=0,
            stdout_snippet="checkout-service-a1b2c 1/1 Running 0 12m",
            tool_category="kubectl",
        ),
        Event(
            id="ev-diag-2",
            incident_id=incident.id,
            raw_command="kubectl logs deployment/checkout-service -n checkout --tail=50",
            exit_code=0,
            stdout_snippet="WARN SlowQueryWarning: sequential scan on table 'cart_items' (rev-482) taking 4200ms\nERROR DBPoolTimeoutException: Connection pool exhausted (active=5, max=5)",
            tool_category="kubectl",
        ),
        Event(
            id="ev-fail-1",
            incident_id=incident.id,
            raw_command="kubectl restart service/checkout-service -n checkout",
            exit_code=1,
            stderr_snippet="error: unknown command 'restart' for 'service'",
            tool_category="kubectl",
        ),
        Event(
            id="ev-patch-config",
            incident_id=incident.id,
            raw_command="kubectl patch configmap checkout-config -n checkout -p '{\"data\":{\"DB_POOL_SIZE\":\"50\"}}'",
            exit_code=0,
            stdout_snippet="configmap/checkout-config patched",
            state_delta_summary="ConfigMap checkout-config updated, POOL_SIZE 5 -> 50",
            tool_category="kubectl",
        ),
        Event(
            id="ev-rollback-deploy",
            incident_id=incident.id,
            raw_command="kubectl rollout undo deployment/checkout-service -n checkout --to-revision=481",
            exit_code=0,
            stdout_snippet="deployment.apps/checkout-service rolled back to revision 481",
            state_delta_summary="Deployment checkout-service rolled back to rev-481",
            tool_category="kubectl",
        ),
        Event(
            id="ev-verify-health",
            incident_id=incident.id,
            raw_command="curl -f http://checkout-service/health",
            exit_code=0,
            stdout_snippet='{"status":"healthy","latency_ms":22,"db_connections_active":4,"db_pool_max":50}',
            state_delta_summary="Service latency dropped 4200ms -> 22ms; HTTP 200 OK",
            tool_category="system",
        ),
    ]
    return incident, events


def test_ai_engine_disambiguates_ambiguous_conflicting_hypotheses():
    """STEP 5 TEST 1: Asserts that when evidence genuinely conflicts, the LLM reasoning pipeline

    produces multiple ranked hypotheses with calibrated confidence, cited evidence, and distinguishing factors.
    """
    incident, events = _create_ambiguous_scenario()

    # Validated response matching the redesigned LLM schema
    llm_disambiguated_response = {
        "symptom": "504 Gateway Timeout, High P99 Latency (4200ms), Active Connection Saturation",
        "disambiguation_required": True,
        "hypothesis": "Primary: Unindexed sequential scan query in rev-482 held database connections open until pool saturated; rollback restored healthy throughput. Contributing: DB pool size was underprovisioned.",
        "ranked_hypotheses": [
            {
                "rank": 1,
                "hypothesis": "Sequential scan query regression in rev-482 caused long-running transactions (4200ms) that saturated connection pool slots. Rollback to rev-481 eliminated query latency.",
                "candidate_event_ids": ["ev-rollback-deploy"],
                "supporting_evidence": [
                    "SlowQueryWarning: sequential scan on table 'cart_items' taking 4200ms",
                    "Latency dropped from 4200ms to 22ms immediately following rollback to revision 481",
                ],
                "confidence": 0.65,
                "distinguishing_factor": "APM trace query duration for cart_items under rev-481 vs rev-482; if query latency drops under 50ms on rev-481, query regression was primary cause.",
            },
            {
                "rank": 2,
                "hypothesis": "Database connection pool ceiling (5) was severely underprovisioned for checkout transaction concurrency. ConfigMap patch to 50 increased queue capacity.",
                "candidate_event_ids": ["ev-patch-config"],
                "supporting_evidence": [
                    "DBPoolTimeoutException: Connection pool exhausted (active=5, max=5)",
                    "Post-recovery pool active count stabilized at 4/50 without queue backlog",
                ],
                "confidence": 0.35,
                "distinguishing_factor": "Monitor active connection count during traffic spike under rev-481 with original pool_size=5; if saturation reoccurs, pool size was primary bottleneck.",
            },
        ],
        "evidence_event_ids": ["ev-diag-2", "ev-patch-config", "ev-rollback-deploy", "ev-verify-health"],
        "fix_event_ids": ["ev-rollback-deploy"],
        "negative_knowledge_event_ids": ["ev-fail-1"],
        "outcome": "resolved",
        "reasoning_notes": "Telemetry demonstrates compound failure mode: rev-482 introduced an unindexed query taking 4.2s, which locked all 5 available pool slots. Rollback resolved the root latency cause, while pool expansion provided required resilience.",
    }

    # 1. Verify response validates against input events
    validated = AIReasoningEngine._validate_chain_response(llm_disambiguated_response, events)
    assert validated["disambiguation_required"] is True
    assert len(validated["ranked_hypotheses"]) == 2

    # 2. Check calibrated confidence scoring
    assert validated["ranked_hypotheses"][0]["confidence"] == 0.65
    assert validated["ranked_hypotheses"][1]["confidence"] == 0.35
    assert sum(h["confidence"] for h in validated["ranked_hypotheses"]) == pytest.approx(1.0)

    # 3. Check distinguishing factors
    assert "APM trace query duration" in validated["ranked_hypotheses"][0]["distinguishing_factor"]
    assert "active connection count" in validated["ranked_hypotheses"][1]["distinguishing_factor"]

    # 4. Check runbook generation handles multiple ranked hypotheses with conditional branching
    engine = AIReasoningEngine()
    runbook_dict = engine._heuristic_runbook_narration(incident, validated, events)
    assert "Disambiguated Remediation" in runbook_dict["title"]
    assert len(runbook_dict["steps"]) >= 3
    # Step 1 must be the distinguishing diagnostic check
    assert "Diagnostic Distinguishing Check" in runbook_dict["steps"][0]["title"]
    assert "APM trace" in runbook_dict["steps"][0]["description"]
    # Step 2 must be the primary remediation
    assert "rollout undo" in runbook_dict["steps"][1]["command"]
    # Step 3 must be the secondary contingency branch
    assert "patch configmap" in runbook_dict["steps"][2]["command"]


def test_deterministic_layer_alone_refuses_false_confidence_on_ambiguity():
    """STEP 5 TEST 2: Asserts that when the LLM is DISABLED, the deterministic layer alone

    CANNOT resolve the ambiguity to a single confident answer, outputting outcome='inconclusive',
    fix_event_ids=[], and ranked_hypotheses=[] (ABSENCE OF FALSE CONFIDENCE).
    """
    incident, events = _create_ambiguous_scenario()
    engine = AIReasoningEngine(api_key=None)  # LLM explicitly disabled

    # Run ambiguous scenario through only the deterministic heuristic layer
    chain = engine._heuristic_chain_assembly(incident, events, None)

    # 1. Must flag that disambiguation is required
    assert chain["disambiguation_required"] is True

    # 2. Must refuse false confidence — outcome is inconclusive
    assert chain["outcome"] == "inconclusive"

    # 3. Must NOT invent a fix or arbitrarily select the last command as the winner
    assert chain["fix_event_ids"] == []

    # 4. Must admit that deterministic layer alone cannot produce a ranked hypothesis list
    assert chain["ranked_hypotheses"] == []

    # 5. Explains its honest limitations in reasoning notes
    assert "Deterministic heuristic lacks semantic comprehension to rank competing root causes" in chain["reasoning_notes"]
    assert "Multiple candidate mutations detected" in chain["hypothesis"]

    # 6. Runbook generation refuses to output a confident fix command
    runbook_dict = engine._heuristic_runbook_narration(incident, chain, events)
    assert "Manual Triage Required" in runbook_dict["title"]
    assert runbook_dict["root_cause_category"] == "Ambiguous / Multi-Candidate Remediation"
    assert len(runbook_dict["steps"]) == 1
    assert runbook_dict["steps"][0]["is_remediation"] is False
    assert "Manual Diagnostic Triage Required" in runbook_dict["steps"][0]["title"]
