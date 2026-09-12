"""Intelligence Graph Builder.

Constructs a directed semantic graph for an incident connecting:
Symptom -> Evidence -> Executed Commands -> State Deltas -> Outcome / Runbook.
"""

from __future__ import annotations

from opsgenome.storage.models import (
    CapturedEvent,
    CausalEdge,
    CausalNode,
    CausalStatus,
    Incident,
    IntelligenceGraph,
)


class IntelligenceGraphBuilder:
    """Builds interactive knowledge & causal graphs from captured telemetry and incident states."""

    @staticmethod
    def build_graph(incident: Incident, events: list[CapturedEvent]) -> IntelligenceGraph:
        nodes: list[CausalNode] = []
        edges: list[CausalEdge] = []

        # 1. Symptom / Intake Node
        symptom_id = f"symptom_{incident.id}"
        symptoms_str = ", ".join(incident.symptoms) if incident.symptoms else incident.title
        nodes.append(
            CausalNode(
                id=symptom_id,
                node_type="symptom",
                label=f"Alert: {incident.title}",
                subtitle=f"Service: {incident.service} | {symptoms_str}",
                score=1.0,
                status="warning",
                metadata={"severity": incident.severity, "trigger": incident.trigger_type.value},
            )
        )

        prev_node_id = symptom_id

        # 2. Add Commands & State Deltas
        for ev in events:
            cmd_node_id = f"cmd_{ev.id[:8]}"

            # Determine visual status
            if ev.status == CausalStatus.VERIFIED_FIX:
                status_str = "verified"
            elif ev.status == CausalStatus.DEAD_END or ev.exit_code != 0:
                status_str = "dead_end"
            elif ev.status == CausalStatus.NOISE:
                status_str = "normal"
            else:
                status_str = "investigative"

            label_text = ev.command_redacted if len(ev.command_redacted) <= 45 else ev.command_redacted[:42] + "..."
            subtitle_text = f"Exit: {ev.exit_code} | Score: {ev.causal_score:.2f}"

            nodes.append(
                CausalNode(
                    id=cmd_node_id,
                    node_type="command",
                    label=label_text,
                    subtitle=subtitle_text,
                    score=ev.causal_score,
                    status=status_str,
                    metadata={
                        "full_command": ev.command_redacted,
                        "exit_code": ev.exit_code,
                        "tool": ev.tool_category,
                        "duration_ms": ev.duration_ms,
                        "status": ev.status.value,
                    },
                )
            )

            # Edge from previous node to command
            relation = "leads_to"
            if ev.status == CausalStatus.DEAD_END:
                relation = "ruled_out"
            elif ev.status == CausalStatus.VERIFIED_FIX:
                relation = "verified_by"

            edges.append(CausalEdge(source=prev_node_id, target=cmd_node_id, relation=relation, weight=ev.causal_score))

            # If there was a meaningful state delta, add a state delta node
            if ev.state_delta_summary:
                delta_node_id = f"delta_{ev.id[:8]}"
                nodes.append(
                    CausalNode(
                        id=delta_node_id,
                        node_type="state_delta",
                        label="State Transition",
                        subtitle=ev.state_delta_summary[:45],
                        score=0.9,
                        status="success" if ev.after_snapshot and ev.after_snapshot.is_healthy else "warning",
                        metadata={"delta": ev.state_delta_summary},
                    )
                )
                edges.append(
                    CausalEdge(
                        source=cmd_node_id,
                        target=delta_node_id,
                        relation="caused_delta",
                        weight=1.0,
                    )
                )
                prev_node_id = delta_node_id
            else:
                # If command was a verified fix or investigative, advance the chain
                if ev.status != CausalStatus.DEAD_END:
                    prev_node_id = cmd_node_id

        # 3. Add Root Cause & Outcome Node
        outcome_id = f"outcome_{incident.id}"
        is_resolved = incident.status.value == "resolved"
        nodes.append(
            CausalNode(
                id=outcome_id,
                node_type="outcome",
                label=f"Root Cause: {incident.root_cause_category}",
                subtitle=f"Status: {incident.status.value.upper()} by {incident.resolved_by}",
                score=1.0,
                status="success" if is_resolved else "warning",
                metadata={
                    "root_cause": incident.root_cause_category,
                    "resolved_by": incident.resolved_by,
                    "summary": incident.summary,
                },
            )
        )

        edges.append(
            CausalEdge(
                source=prev_node_id,
                target=outcome_id,
                relation="resolved_with" if is_resolved else "leads_to",
                weight=1.0,
            )
        )

        summary_text = (
            f"Incident {incident.id} ({incident.service}) mapped with {len(nodes)} nodes "
            f"and {len(edges)} causal connections."
        )

        return IntelligenceGraph(
            incident_id=incident.id,
            nodes=nodes,
            edges=edges,
            summary=summary_text,
        )
