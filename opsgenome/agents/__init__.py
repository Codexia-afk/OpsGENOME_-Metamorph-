"""OpsGenome Multi-Agent Collaboration Subsystem.

Provides specialized autonomous agents for cross-stack incident diagnosis,
coordinated multi-file remediation, security vetting, and cluster health auditing.
"""

from opsgenome.agents.demo_scenarios import (
    DEMO_TARGET_SPECS,
    DemoTargetSpec,
    get_demo_cluster_events_log,
    get_demo_cluster_issues,
    get_demo_cross_stack_targets,
    get_demo_incident_log,
)
from opsgenome.agents.models import (
    AgentMessage,
    AgentRole,
    ClusterIssue,
    ClusterIssueReport,
    CoordinatedFixPlan,
    MessageType,
    SpecialistFinding,
)

__all__ = [
    "AgentMessage",
    "AgentRole",
    "ClusterIssue",
    "ClusterIssueReport",
    "CoordinatedFixPlan",
    "DEMO_TARGET_SPECS",
    "DemoTargetSpec",
    "MessageType",
    "SpecialistFinding",
    "get_demo_cluster_events_log",
    "get_demo_cluster_issues",
    "get_demo_cross_stack_targets",
    "get_demo_incident_log",
]

