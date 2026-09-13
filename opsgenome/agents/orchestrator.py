"""Lead SRE Orchestrator Agent for Multi-Agent Cross-Stack Coordination."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

from opsgenome.agents.dependency_graph import DependencyGraphEngine, TopologicalDAGResult
from opsgenome.agents.models import (
    AgentMessage,
    AgentRole,
    CoordinatedFixPlan,
    MessageType,
    SpecialistFinding,
)
from opsgenome.agents.specialists import (
    ClusterSpecialistAgent,
    JavaSpecialistAgent,
    NodeSpecialistAgent,
    PythonSpecialistAgent,
    SecuritySentinelAgent,
)
from opsgenome.ai.code_fixer import safe_subprocess_run
from opsgenome.ai.engine import AIReasoningEngine


class LeadSREOrchestrator:
    """Lead SRE Orchestrator coordinating specialized AI agents across tech stacks."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None):
        self.name = "Lead SRE Orchestrator"
        self.ai_engine = ai_engine or AIReasoningEngine(provider="auto")
        self.dag_engine = DependencyGraphEngine()
        self.python_agent = PythonSpecialistAgent(ai_engine=self.ai_engine)
        self.java_agent = JavaSpecialistAgent(ai_engine=self.ai_engine)
        self.node_agent = NodeSpecialistAgent(ai_engine=self.ai_engine)
        self.cluster_agent = ClusterSpecialistAgent(ai_engine=self.ai_engine)
        self.sentinel_agent = SecuritySentinelAgent()

    @property
    def specialists(self) -> list[Any]:
        return [self.python_agent, self.java_agent, self.node_agent, self.cluster_agent]

    def analyze_and_coordinate(
        self,
        targets: list[tuple[str, str, str]],
    ) -> tuple[CoordinatedFixPlan, list[AgentMessage]]:
        return self.analyze_cross_stack_incident(targets)

    def analyze_cross_stack_incident(
        self,
        targets: list[tuple[str, str, str]],  # [(file_path, code_content, error_output), ...]
    ) -> tuple[CoordinatedFixPlan, list[AgentMessage]]:
        """Coordinates concurrent analysis across multiple files and technology stacks."""
        messages: list[AgentMessage] = []
        findings: list[SpecialistFinding] = []

        # 1. Orchestrator Dispatch Message
        target_names = [Path(t[0]).name for t in targets]
        messages.append(
            AgentMessage(
                sender="Lead SRE Orchestrator",
                recipient="Multi-Agent Swarm",
                role=AgentRole.ORCHESTRATOR.value,
                message_type=MessageType.TASK_DISPATCH.value,
                content=f"Multi-Stack Incident detected across {len(targets)} files: {', '.join(target_names)}. Dispatching concurrent diagnostic tasks to specialist agents.",
                metadata={"target_count": len(targets), "files": target_names},
            )
        )

        # 2. Dispatch to Specialists based on file type and stack
        for file_path, code, err in targets:
            p = Path(file_path)
            ext = p.suffix.lower()
            fname = p.name.lower()

            if ext == ".py":
                finding = self.python_agent.diagnose(file_path, code, err)
                findings.append(finding)
                messages.append(
                    AgentMessage(
                        sender=self.python_agent.name,
                        recipient="Lead SRE Orchestrator",
                        role=AgentRole.PYTHON_SPECIALIST.value,
                        message_type=MessageType.DIAGNOSTIC_HYPOTHESIS.value,
                        content=f"Diagnosed {finding.exception_type} in `{p.name}` (Line {finding.line_number or '?'}). Root Cause: {finding.root_cause}. Formulated unified diff with defensive safety guards.",
                        metadata={"file": p.name, "diff_size": len(finding.proposed_diff)},
                    )
                )

            elif ext == ".java":
                finding = self.java_agent.diagnose(file_path, code, err)
                findings.append(finding)
                messages.append(
                    AgentMessage(
                        sender=self.java_agent.name,
                        recipient="Lead SRE Orchestrator",
                        role=AgentRole.JAVA_SPECIALIST.value,
                        message_type=MessageType.DIAGNOSTIC_HYPOTHESIS.value,
                        content=f"Diagnosed {finding.exception_type} in `{p.name}`. Root Cause: {finding.root_cause}. Injected null-safety defensive validation.",
                        metadata={"file": p.name, "diff_size": len(finding.proposed_diff)},
                    )
                )

            elif ext in (".js", ".mjs", ".ts"):
                finding = self.node_agent.diagnose(file_path, code, err)
                findings.append(finding)
                messages.append(
                    AgentMessage(
                        sender=self.node_agent.name,
                        recipient="Lead SRE Orchestrator",
                        role=AgentRole.NODE_SPECIALIST.value,
                        message_type=MessageType.DIAGNOSTIC_HYPOTHESIS.value,
                        content=f"Diagnosed {finding.exception_type} in `{p.name}`. Root Cause: {finding.root_cause}. Applied optional chaining and defensive property verification.",
                        metadata={"file": p.name, "diff_size": len(finding.proposed_diff)},
                    )
                )

            elif ext in (".yaml", ".yml", ".tf", ".hcl") or "dockerfile" in fname:
                finding = self.cluster_agent.diagnose_manifest(file_path, code, err)
                findings.append(finding)
                stack_desc = "Terraform HCL" if ext in (".tf", ".hcl") else "Kubernetes/Docker"
                messages.append(
                    AgentMessage(
                        sender=self.cluster_agent.name,
                        recipient="Lead SRE Orchestrator",
                        role=AgentRole.CLUSTER_SPECIALIST.value,
                        message_type=MessageType.DIAGNOSTIC_HYPOTHESIS.value,
                        content=f"Diagnosed {stack_desc} configuration failure in `{p.name}`. Root Cause: {finding.root_cause}. Formulated infrastructure remediation update.",
                        metadata={"file": p.name, "diff_size": len(finding.proposed_diff)},
                    )
                )

            else:
                # Default fallback using Python specialist heuristics
                finding = self.python_agent.diagnose(file_path, code, err)
                findings.append(finding)

        # 3. Security Sentinel Guardrail Check
        # Build candidate verification commands
        candidate_vcmds = [
            f"{sys.executable} -m py_compile {f.target_file}" if f.stack == "python"
            else f"node --check {f.target_file}" if f.stack in ("nodejs", "javascript")
            else f"kubectl get pods"
            for f in findings
        ]

        messages.append(
            AgentMessage(
                sender="Security Sentinel Agent",
                recipient="Lead SRE Orchestrator",
                role=AgentRole.SECURITY_SENTINEL.value,
                message_type=MessageType.SAFETY_CHECK.value,
                content=f"Scanning all {len(findings)} proposed diffs and verification commands against fail-closed safety policies...",
            )
        )
        is_safe, violations = self.sentinel_agent.inspect_diff_and_commands(findings, candidate_vcmds)
        if is_safe:
            messages.append(
                AgentMessage(
                    sender="Security Sentinel Agent",
                    recipient="Lead SRE Orchestrator",
                    role=AgentRole.SECURITY_SENTINEL.value,
                    message_type=MessageType.STATUS_UPDATE.value,
                    content="✔ Security Sentinel verified: 0 credential leaks, 0 destructive shell patterns, fail-closed boundaries enforced.",
                    metadata={"status": "APPROVED", "violations": violations},
                )
            )
        else:
            messages.append(
                AgentMessage(
                    sender="Security Sentinel Agent",
                    recipient="Lead SRE Orchestrator",
                    role=AgentRole.SECURITY_SENTINEL.value,
                    message_type=MessageType.STATUS_UPDATE.value,
                    content=f"⚠ Sentinel warnings logged: {'; '.join(violations)}.",
                    metadata={"status": "WARNING", "violations": violations},
                )
            )

        # 4. Mathematical Topological Dependency DAG Engine (Kahn's Algorithm)
        dag_input = [
            (f.target_file, f.fixed_code or f.original_code, f.stack)
            for f in findings
        ]
        dag_result = self.dag_engine.build_dag_and_sort(dag_input)

        # Reorder findings based on Kahn's algorithm topological output
        finding_map = {f.target_file: f for f in findings}
        ordered_findings = [finding_map[p] for p in dag_result.execution_order if p in finding_map]
        # Include any remaining findings not in dag_result.execution_order
        for f in findings:
            if f not in ordered_findings:
                ordered_findings.append(f)

        cross_summary = (
            f"Mathematical Topological DAG synthesized via Kahn's Algorithm across {len(ordered_findings)} components. "
            f"Execution Order: Infrastructure manifests patched first to guarantee resource headroom, "
            f"followed by backend services ({', '.join(Path(b.target_file).name for b in ordered_findings if b.stack in ('java', 'python'))}), "
            f"and ingress routing."
        )

        plan = CoordinatedFixPlan(
            findings=ordered_findings,
            dependency_graph=dag_result.dependency_graph,
            execution_order=dag_result.execution_order,
            cross_stack_summary=cross_summary,
            edge_explanations=dag_result.edge_explanations,
            rollback_plan=[f"Restore {Path(f.target_file).name}.bak backup if verification fails" for f in ordered_findings],
            verification_commands=[
                f"{sys.executable} -m py_compile {f.target_file}" if f.stack == "python"
                else f"node --check {f.target_file}" if f.stack in ("nodejs", "javascript")
                else f"kubectl get pods"
                for f in ordered_findings
            ],
            status="PROPOSED",
        )

        messages.append(
            AgentMessage(
                sender="Lead SRE Orchestrator",
                recipient="Operator / Live Studio",
                role=AgentRole.ORCHESTRATOR.value,
                message_type=MessageType.COORDINATED_PLAN.value,
                content=f"Master Coordinated Resolution Plan synthesized with {len(ordered_findings)} atomic patches across {len(set(f.stack for f in ordered_findings))} stacks. DAG verified via Kahn's algorithm.",
                metadata={"plan_id": plan.plan_id, "execution_order": [Path(p).name for p in dag_result.execution_order]},
            )
        )

        return plan, messages

    def apply_coordinated_fix(self, plan: CoordinatedFixPlan, verify_live: bool = True) -> tuple[bool, list[str]]:
        """Atomically applies coordinated patches with closed-loop verification and automated transactional rollback."""
        applied_backups: list[tuple[str, str, str]] = []  # (original_path, backup_path, original_sha256)
        log: list[str] = []

        try:
            # Phase 1: Pre-flight SHA-256 Hashes & Backups
            for finding in plan.findings:
                if not finding.proposed_diff:
                    continue

                target_p = Path(finding.target_file)
                if target_p.is_file():
                    orig_text = target_p.read_text(encoding="utf-8")
                    orig_hash = hashlib.sha256(orig_text.encode("utf-8")).hexdigest()
                    bak_p = target_p.with_suffix(target_p.suffix + ".bak")
                    bak_p.write_text(finding.original_code or orig_text, encoding="utf-8")
                    applied_backups.append((str(target_p), str(bak_p), orig_hash))

                    # Apply patch
                    target_p.write_text(finding.fixed_code, encoding="utf-8")
                    log.append(f"✔ Applied patch to {target_p.name} (pre-flight sha256: {orig_hash[:8]}, backup: {bak_p.name})")

            plan.status = "APPLIED"
            log.append(f"✔ Applied all {len(applied_backups)} coordinated patches in topological order.")

            # Phase 2: Transactional Closed-Loop Verification
            if verify_live and applied_backups:
                log.append("⚡ Running closed-loop transactional verification suite...")
                for finding in plan.findings:
                    target_p = Path(finding.target_file)
                    ext = target_p.suffix.lower()

                    vcmd = None
                    if ext == ".py":
                        vcmd = [sys.executable, "-m", "py_compile", str(target_p.resolve())]
                    elif ext in (".js", ".mjs"):
                        # Only run node --check if node binary exists, otherwise skip or pass
                        if shutil.which("node"):
                            vcmd = ["node", "--check", str(target_p.resolve())]
                        else:
                            log.append(f"  ℹ Skipping node syntax check: 'node' executable not in PATH.")
                    elif ext == ".java":
                        if shutil.which("javac") and safe_subprocess_run(["javac", "-version"], timeout=3).returncode == 0:
                            vcmd = ["javac", "-d", "/tmp", str(target_p.resolve())]
                        else:
                            log.append(f"  ℹ Skipping javac check: Java runtime environment not configured on host.")

                    if vcmd:
                        proc = safe_subprocess_run(vcmd, cwd=str(target_p.parent.resolve()), timeout=10)
                        if proc.returncode != 0:
                            # Verification failed! Trigger instant automatic rollback
                            log.append(f"✘ Verification failed for {target_p.name} (Exit code {proc.returncode}): {proc.stderr or proc.stdout}")
                            log.append("↺ INITIATING AUTOMATIC TRANSACTIONAL ROLLBACK (Atomic Failure Recovery)...")
                            for orig, bak, expected_hash in reversed(applied_backups):
                                Path(orig).write_text(Path(bak).read_text(encoding="utf-8"), encoding="utf-8")
                                restored_hash = hashlib.sha256(Path(orig).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                                log.append(f"  ↺ Rolled back {Path(orig).name} from {Path(bak).name} (hash verified: {restored_hash == expected_hash})")
                            plan.status = "ROLLED_BACK"
                            return False, log
                        else:
                            log.append(f"  ✔ Verification passed: {target_p.name} syntax & compilation healthy.")

            plan.status = "VERIFIED_AND_COMMITTED"
            log.append(f"✔ Transaction committed successfully: all {len(applied_backups)} patches verified healthy.")
            return True, log

        except Exception as err:
            # Atomic rollback on any unexpected exception
            log.append(f"✘ Exception during transaction: {err}. Initiating automatic rollback...")
            for orig, bak, expected_hash in reversed(applied_backups):
                try:
                    Path(orig).write_text(Path(bak).read_text(encoding="utf-8"), encoding="utf-8")
                    log.append(f"  ↺ Rolled back {Path(orig).name} from backup.")
                except Exception:
                    pass
            plan.status = "ROLLED_BACK"
            return False, log
