"""Data models for Multi-Agent Collaboration and Cluster Health Auditing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AgentRole(str, Enum):
    ORCHESTRATOR = "Lead SRE Orchestrator"
    PYTHON_SPECIALIST = "Python Specialist"
    JAVA_SPECIALIST = "Java / JVM Specialist"
    NODE_SPECIALIST = "Node.js Specialist"
    CLUSTER_SPECIALIST = "Cluster & Infra Specialist"
    SECURITY_SENTINEL = "Security Sentinel"
    VERIFICATION_SENTINEL = "Verification Validator"


class MessageType(str, Enum):
    TASK_DISPATCH = "TASK_DISPATCH"
    DIAGNOSTIC_HYPOTHESIS = "DIAGNOSTIC_HYPOTHESIS"
    PROPOSED_PATCH = "PROPOSED_PATCH"
    SAFETY_CHECK = "SAFETY_CHECK"
    COORDINATED_PLAN = "COORDINATED_PLAN"
    STATUS_UPDATE = "STATUS_UPDATE"


@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sender: str = "Lead SRE Orchestrator"
    recipient: str = "All Specialists"
    role: str = AgentRole.ORCHESTRATOR.value
    message_type: str = MessageType.STATUS_UPDATE.value
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpecialistFinding:
    target_file: str
    stack: str
    exception_type: str
    error_message: str
    line_number: int | None
    root_cause: str
    proposed_diff: str = ""
    original_code: str = ""
    fixed_code: str = ""
    confidence: float = 0.95
    explanation: str = ""
    dependencies: list[str] = field(default_factory=list)
    agent_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SpecialistFinding:
        return cls(
            target_file=d.get("target_file", ""),
            stack=d.get("stack", "general"),
            exception_type=d.get("exception_type", "Error"),
            error_message=d.get("error_message", ""),
            line_number=d.get("line_number"),
            root_cause=d.get("root_cause", ""),
            proposed_diff=d.get("proposed_diff", ""),
            original_code=d.get("original_code", ""),
            fixed_code=d.get("fixed_code", ""),
            confidence=float(d.get("confidence", 0.9)),
            explanation=d.get("explanation", ""),
            dependencies=list(d.get("dependencies", [])),
            agent_name=d.get("agent_name", ""),
        )


@dataclass
class CoordinatedFixPlan:
    plan_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    findings: list[SpecialistFinding] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    cross_stack_summary: str = ""
    edge_explanations: list[str] = field(default_factory=list)
    rollback_plan: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    status: str = "PROPOSED"  # PROPOSED | APPLIED | VERIFIED_AND_COMMITTED | ROLLED_BACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "findings": [f.to_dict() for f in self.findings],
            "dependency_graph": self.dependency_graph,
            "execution_order": self.execution_order,
            "cross_stack_summary": self.cross_stack_summary,
            "edge_explanations": self.edge_explanations,
            "rollback_plan": self.rollback_plan,
            "verification_commands": self.verification_commands,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CoordinatedFixPlan:
        findings_data = [SpecialistFinding.from_dict(f) if isinstance(f, dict) else f for f in d.get("findings", [])]
        return cls(
            plan_id=d.get("plan_id", f"plan-{uuid.uuid4().hex[:8]}"),
            findings=findings_data,
            dependency_graph=dict(d.get("dependency_graph", {})),
            execution_order=list(d.get("execution_order", [])),
            cross_stack_summary=d.get("cross_stack_summary", ""),
            edge_explanations=list(d.get("edge_explanations", [])),
            rollback_plan=list(d.get("rollback_plan", [])),
            verification_commands=list(d.get("verification_commands", [])),
            status=d.get("status", "PROPOSED"),
        )


@dataclass
class ClusterIssue:
    id: str = field(default_factory=lambda: f"issue-{uuid.uuid4().hex[:6]}")
    severity: str = "HIGH"  # CRITICAL | HIGH | MEDIUM | LOW
    resource_type: str = "Pod"  # Pod | Deployment | Service | ConfigMap | Container
    resource_name: str = ""
    namespace: str = "default"
    issue_type: str = "CrashLoopBackOff"  # CrashLoopBackOff | OOMKilled | ImagePullBackOff | SelectorMismatch | ReadinessProbeFailed | PortConflict
    root_cause: str = ""
    impact: str = ""
    immediate_remediation_cmd: str = ""
    declarative_yaml_patch: str = ""
    verification_cmd: str = ""
    safety_tier: str = "AUTOMATED_SAFE"  # AUTOMATED_SAFE | ADMIN_CONFIRMATION_REQUIRED | MANUAL_ONLY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClusterIssueReport:
    cluster_id: str = "kubernetes-cluster-primary"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_issues_found: int = 0
    issues: list[ClusterIssue] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "timestamp": self.timestamp,
            "total_issues_found": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }
