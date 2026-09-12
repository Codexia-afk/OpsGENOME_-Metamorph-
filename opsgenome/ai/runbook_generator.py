"""Runbook Synthesis & Causal Chain Pipeline.

Coordinates:
1. Signal filter to extract high-signal events (weight >= 0.6)
2. AI Reasoning Call 1: Structured Causal Chain Assembly
3. AI Reasoning Call 2: Human-Readable Runbook Narration
4. Computed Confidence Score: success_count / (success_count + failure_count)
   with enforced "Not enough data yet" when N < 3.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any
import uuid
from opsgenome.ai.confidence import ConfidenceEngine
from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.signal.causal_chain import CausalChainExtractor
from opsgenome.signal.filter import SignalFilter
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import (
    CausalChain,
    ChainOutcome,
    DeadEndStep,
    Event,
    EventClassification,
    Evidence,
    Incident,
    KnowledgeStatus,
    RecurrenceSignature,
    Runbook,
    RunbookStep,
    StateSnapshot,
    WhyWhyNot,
)


class RunbookGenerator:
    """Coordinates causal chain extraction and runbook synthesis."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        ai_engine: AIReasoningEngine | None = None,
        signal_filter: SignalFilter | None = None,
    ):
        self.db = db or DatabaseManager()
        self.ai = ai_engine or AIReasoningEngine()
        self.signal_filter = signal_filter or SignalFilter(high_signal_threshold=0.60)

    def generate_runbook_for_incident(
        self,
        incident: Incident,
        events: list[Event] | None = None,
        snapshots: list[StateSnapshot] | None = None,
        is_success: bool = True,
        historical_count: int | None = None,
        success_count: int | None = None,
        escalation_count: int = 0,
        other_engineers: list[str] | None = None,
        **kwargs: Any,
    ) -> tuple[CausalChain, Runbook]:
        """Runs the 2-call pipeline, stores causal chain, computes earned confidence, and saves runbook."""
        if events is None:
            events = self.db.get_events_for_incident(incident.id)
        if snapshots is None:
            snapshots = self.db.get_snapshots_for_incident(incident.id)

        # 1. Pre-filter signal vs noise
        scored_events = self.signal_filter.process_events(events, snapshots)
        for ev in scored_events:
            self.db.save_event(ev)

        # Filter high-signal events for the LLM
        high_signal_events = self.signal_filter.get_high_signal_events(scored_events)

        # 2. Extract Deterministic Evidence & Why/Why Not
        extracted = CausalChainExtractor.extract(scored_events, snapshots)
        for ev_item in extracted["evidence_items"]:
            self.db.save_evidence(ev_item)

        # 3. AI Call 1: Chain Assembly (Structured JSON)
        chain_dict = self.ai.call_1_chain_assembly(incident, high_signal_events, snapshots)

        # Compute recovery time in seconds
        recovery_time = 0
        if incident.ended_at and incident.started_at:
            recovery_time = int((incident.ended_at - incident.started_at).total_seconds())

        chain_id = str(uuid.uuid4())[:8]
        # The LLM's public response distinguishes insufficient signal from an
        # unresolved investigation. Persistence uses the existing enum, so both
        # safely map to INCONCLUSIVE while the full distinction stays in the
        # runbook narration path.
        chain_outcome = chain_dict.get("outcome", "inconclusive")
        persisted_outcome = "success" if chain_outcome == "resolved" else "inconclusive"
        causal_chain = CausalChain(
            id=chain_id,
            incident_id=incident.id,
            symptom=chain_dict.get("symptom", " ".join(incident.symptoms) or incident.title),
            hypothesis=chain_dict.get("hypothesis", "Configuration/deployment issue"),
            evidence_event_ids=chain_dict.get("evidence_event_ids", []),
            fix_event_ids=chain_dict.get("fix_event_ids", []),
            outcome=ChainOutcome(persisted_outcome),
            confidence_score=0.0,
            recovery_time_seconds=max(0, recovery_time),
            evidence_items=extracted["evidence_items"],
            why_why_not=extracted["why_why_not"],
        )
        self.db.save_causal_chain(causal_chain)

        # 4. AI Call 2: Runbook Narration
        narration_dict = self.ai.call_2_runbook_narration(incident, chain_dict, high_signal_events)
        root_cause = narration_dict.get("root_cause_category", "Unknown Root Cause")
        title = narration_dict.get("title", f"Runbook: {root_cause}")
        raw_steps = narration_dict.get("steps", [])

        runbook_steps: list[RunbookStep] = []
        for s in raw_steps:
            runbook_steps.append(
                RunbookStep(
                    step_number=s.get("step_number", len(runbook_steps) + 1),
                    title=s.get("title", "Remediation Step"),
                    command=s.get("command", ""),
                    description=s.get("description", ""),
                    expected_output=s.get("expected_output", ""),
                    rationale=s.get("rationale", ""),
                    is_remediation=s.get("is_remediation", True),
                )
            )

        dead_ends: list[DeadEndStep] = extracted["dead_ends"]

        # 5. Compute Earned Confidence Score & Knowledge Status
        existing_runbooks = self.db.list_runbooks(service=incident.service)
        existing = next((r for r in existing_runbooks if r.root_cause_category == root_cause), None)

        if historical_count is not None:
            succ = success_count if success_count is not None else historical_count
            fail = escalation_count
            version = existing.version + 1 if existing else 1
            runbook_id = existing.id if existing else str(uuid.uuid4())[:8]
        elif existing:
            runbook_id = existing.id
            version = existing.version + 1
            succ = existing.success_count + (1 if is_success else 0)
            fail = existing.failure_count + (0 if is_success else 1)
        else:
            runbook_id = str(uuid.uuid4())[:8]
            version = 1
            succ = 1 if is_success else 0
            fail = 0 if is_success else 1

        total_uses = succ + fail
        conf_score = succ / total_uses if total_uses > 0 else 0.0

        # Provenance record computation
        eng_list = [incident.resolved_by]
        if other_engineers:
            eng_list.extend(other_engineers)

        earned_score, conf_level, prov_record = ConfidenceEngine.calculate_confidence(
            total_incidents=total_uses,
            successful_resolutions=succ,
            escalations=fail,
            engineers=eng_list,
        )

        knowledge_status = ConfidenceEngine.calculate_knowledge_status(
            total_incidents=total_uses,
            successful_resolutions=succ,
            escalations=fail,
            last_matched_at=existing.last_matched_at if existing else None,
        )

        if total_uses < 3:
            conf_display = f"Not enough data yet (N={total_uses})"
        else:
            conf_display = f"{int(conf_score * 100)}% — {succ} of {total_uses} uses"

        causal_chain.confidence_score = round(conf_score, 2)
        self.db.save_causal_chain(causal_chain)

        # 6. Assemble and save versioned runbook
        symptom_str = " ".join(incident.symptoms) if incident.symptoms else incident.title
        runbook = Runbook(
            id=runbook_id,
            causal_chain_id=causal_chain.id,
            title=title,
            root_cause_category=root_cause,
            steps=runbook_steps,
            success_count=succ,
            failure_count=fail,
            confidence_score=round(conf_score, 2),
            earned_confidence_score=round(earned_score, 2),
            confidence_level=conf_level,
            knowledge_status=knowledge_status,
            provenance=prov_record,
            version=version,
            last_matched_at=datetime.now(timezone.utc),
            service=incident.service,
            symptom_signature=symptom_str,
            known_dead_ends=dead_ends,
            negative_knowledge_dead_ends=dead_ends,
            verification_commands=[s.command for s in runbook_steps if "curl" in s.command or "get" in s.command or "status" in s.command],
            why_why_not=extracted["why_why_not"],
            evidence_citations=[e.id for e in extracted["evidence_items"]],
            confidence_display=conf_display,
        )
        self.db.save_runbook(runbook)

        # 7. Save Recurrence Signature
        sig_hash = hashlib.sha256(f"{incident.service}:{root_cause}:{symptom_str}".encode()).hexdigest()[:16]
        self.db.save_signature(
            RecurrenceSignature(
                incident_id=incident.id,
                service=incident.service,
                error_patterns=incident.symptoms,
                symptom_tokens=symptom_str.lower().split(),
                signature_hash=sig_hash,
            )
        )

        incident.root_cause_category = root_cause
        incident.summary = f"Remediated via {title}."
        self.db.create_incident(incident)

        return causal_chain, runbook
