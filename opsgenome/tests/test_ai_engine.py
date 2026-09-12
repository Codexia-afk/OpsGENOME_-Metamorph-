"""Guardrails for the audited two-call incident reasoning contract."""

import pytest

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.storage.models import Event, Incident


def test_chain_response_rejects_invented_event_ids():
    event = Event(id="known-event", incident_id="inc-1", raw_command="kubectl get pods")
    response = {
        "symptom": "CrashLoopBackOff",
        "hypothesis": "configuration issue",
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
