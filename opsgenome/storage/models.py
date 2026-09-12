"""Pydantic data models matching the exact OpsGenome schema specification.

Tables:
- incidents (id, started_at, ended_at, trigger_source, status)
- events (id, incident_id, timestamp, raw_command, exit_code, stdout_snippet, stderr_snippet, signal_weight, classification)
- state_snapshots (id, incident_id, event_id, resource_type, before_state, after_state, diff_summary)
- causal_chains (id, incident_id, symptom, hypothesis, evidence_event_ids, fix_event_ids, outcome, confidence_score, recovery_time_seconds)
- runbooks (id, causal_chain_id, title, root_cause_category, steps, success_count, failure_count, confidence_score, version, last_matched_at)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class TriggerSource(str, Enum):
    MANUAL = "manual"
    WEBHOOK = "webhook"
    ANOMALY = "anomaly"
    WEBHOOK_PAGERDUTY = "webhook_pagerduty"
    WEBHOOK_OPSGENIE = "webhook_opsgenie"
    WEBHOOK_SLACK = "webhook_slack"
    BURST_ANOMALY = "burst_anomaly"


# Backward compatibility alias
TriggerType = TriggerSource


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACTIVE = "open"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"
    DISCARDED = "abandoned"


class EventClassification(str, Enum):
    FIX = "fix"
    RETRY = "retry"
    DEAD_END = "dead_end"
    INVESTIGATION = "investigation"
    UNKNOWN = "unknown"
    VERIFIED_FIX = "fix"
    NOISE = "unknown"
    INVESTIGATIVE = "investigation"


# Backward compatibility alias
CausalStatus = EventClassification


class ChainOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ESCALATED = "escalated"
    INCONCLUSIVE = "inconclusive"


class ConfidenceLevel(str, Enum):
    COLD_START = "cold_start"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class KnowledgeStatus(str, Enum):
    VERIFIED = "verified"
    AGING = "aging"
    STALE = "stale"
    CONTRADICTED = "contradicted"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    HEALTHY = "healthy"


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: f"ev-{str(uuid.uuid4())[:8]}")
    incident_id: str
    event_id: str | None = None
    evidence_type: str = "metric_verification"  # state_diff | log_snippet | metric_verification | command_output
    summary: str
    verified: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class WhyWhyNot(BaseModel):
    incident_id: str = ""
    recommended_action: str
    why_reasons: list[str] = Field(default_factory=list)
    why_not_alternatives: list[dict[str, Any]] = Field(default_factory=list)  # [{"action": "...", "reason_rejected": "...", "evidence": "..."}]
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.95


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    trigger_source: TriggerSource = TriggerSource.MANUAL
    trigger_type: TriggerSource | None = None  # alias
    status: IncidentStatus = IncidentStatus.OPEN
    # Extra metadata helper fields for UX
    title: str = "Production Incident"
    service: str = "core-service"
    environment: str = "production"
    severity: str = "P1"
    resolved_by: str = "local_engineer"
    symptoms: list[str] = Field(default_factory=list)
    root_cause_category: str = "Unknown"
    summary: str = ""
    candidate_discard_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.trigger_type:
            self.trigger_source = self.trigger_type
        else:
            self.trigger_type = self.trigger_source


class Event(BaseModel):
    # Increment only for breaking changes. Capture agents can use this to keep
    # local queues compatible with a newer daemon.
    schema_version: str = "1.0"
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    incident_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_command: str = ""  # POST-REDACTION ONLY
    command_redacted: str = ""  # alias
    # Kept only as a compatibility input alias. It is never populated by the
    # capture service; persisted commands are always redacted.
    command_raw: str = ""
    exit_code: int = 0
    stdout_snippet: str = ""
    stderr_snippet: str = ""
    stdout_summary: str = ""  # alias
    stderr_summary: str = ""  # alias
    signal_weight: float = 0.5  # 0.0 - 1.0
    causal_score: float = 0.5  # alias
    classification: EventClassification = EventClassification.UNKNOWN
    status: EventClassification | None = None  # alias
    # Telemetry metadata
    duration_ms: int = 0
    cwd: str = ""
    tool_category: str = "system"
    sequence_idx: int = 0
    state_delta_summary: str = ""
    before_snapshot: Any | None = None
    after_snapshot: Any | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.command_redacted and not self.raw_command:
            self.raw_command = self.command_redacted
        elif self.raw_command and not self.command_redacted:
            self.command_redacted = self.raw_command
        if self.causal_score and self.signal_weight == 0.5:
            self.signal_weight = self.causal_score
        elif self.signal_weight and self.causal_score == 0.5:
            self.causal_score = self.signal_weight
        if self.status:
            self.classification = self.status
        else:
            self.status = self.classification


CapturedEvent = Event


class StateSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    incident_id: str
    event_id: str | None = None
    resource_type: str = "k8s_pod"  # k8s_pod | terraform_state | aws_resource | other
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    raw_state: dict[str, Any] = Field(default_factory=dict)
    diff_summary: str = ""
    is_healthy: bool = True
    status_summary: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CausalChain(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    incident_id: str
    symptom: str
    hypothesis: str
    evidence_event_ids: list[str] = Field(default_factory=list)
    fix_event_ids: list[str] = Field(default_factory=list)
    outcome: ChainOutcome = ChainOutcome.SUCCESS
    confidence_score: float = 0.0  # COMPUTED
    recovery_time_seconds: int = 0
    evidence_items: list[Evidence] = Field(default_factory=list)
    why_why_not: WhyWhyNot | None = None


class CausalNode(BaseModel):
    id: str
    node_type: str
    label: str
    subtitle: str = ""
    score: float = 1.0
    status: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CausalEdge(BaseModel):
    source: str
    target: str
    relation: str
    weight: float = 1.0


class IntelligenceGraph(BaseModel):
    incident_id: str
    nodes: list[CausalNode] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)
    summary: str = ""


class RunbookStep(BaseModel):
    step_number: int
    title: str
    command: str
    description: str = ""
    expected_output: str = ""
    rationale: str = ""
    is_remediation: bool = True
    estimated_seconds: int = 30


class DeadEndStep(BaseModel):
    command: str
    why_it_failed: str
    evidence_observed: str = ""
    recommendation: str = "Ruled out. Do not execute."


class ProvenanceRecord(BaseModel):
    total_incidents_recorded: int = 1
    successful_resolutions: int = 1
    historical_success_rate: float = 1.0  # How often did this action work before?
    current_evidence_confidence: float = 0.0  # How strongly does evidence support this today?
    escalations_required: int = 0
    verification_rate: float = 1.0
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    contributing_engineers: list[str] = Field(default_factory=lambda: ["local_engineer"])
    provenance_trail_text: str = ""


class Runbook(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    causal_chain_id: str = ""  # origin
    title: str
    root_cause_category: str
    steps: list[RunbookStep] = Field(default_factory=list)
    success_count: int = 1
    failure_count: int = 0
    confidence_score: float = 0.0  # Computed as success_count / (success_count + failure_count)
    earned_confidence_score: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.COLD_START
    knowledge_status: KnowledgeStatus = KnowledgeStatus.VERIFIED
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    version: int = 1
    last_matched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Rich UI extensions
    service: str = "core-service"
    symptom_signature: str = ""
    known_dead_ends: list[DeadEndStep] = Field(default_factory=list)
    negative_knowledge_dead_ends: list[DeadEndStep] = Field(default_factory=list)
    rollback_steps: list[RunbookStep] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)
    why_why_not: WhyWhyNot | None = None
    evidence_citations: list[str] = Field(default_factory=list)
    confidence_display: str = "Not enough data yet (N=1)"

    def model_post_init(self, __context: Any) -> None:
        if self.confidence_score and not self.earned_confidence_score:
            self.earned_confidence_score = self.confidence_score
        elif self.earned_confidence_score and not self.confidence_score:
            self.confidence_score = self.earned_confidence_score
        if self.known_dead_ends and not self.negative_knowledge_dead_ends:
            self.negative_knowledge_dead_ends = self.known_dead_ends
        elif self.negative_knowledge_dead_ends and not self.known_dead_ends:
            self.known_dead_ends = self.negative_knowledge_dead_ends


class RecurrenceSignature(BaseModel):
    incident_id: str
    service: str
    error_patterns: list[str] = Field(default_factory=list)
    symptom_tokens: list[str] = Field(default_factory=list)
    signature_hash: str = ""


class BusFactorMetric(BaseModel):
    service: str
    domain: str = "Core Services"
    total_incidents: int
    engineers: dict[str, int] = Field(default_factory=dict)
    bus_factor_score: int = 1
    top_expert: str = ""
    top_expert_share: float = 1.0
    risk_level: RiskLevel | str = RiskLevel.CRITICAL
    recommendation: str = ""


class SystemicDriftReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    service: str
    root_cause_category: str
    incident_count: int
    timeline_dates: list[str] = Field(default_factory=list)
    drift_summary: str
    backlog_recommendation: str
    severity: str = "P1"
