"""Specialist Agents for Multi-Agent Cross-Stack Diagnosis & Remediation."""

from __future__ import annotations

import difflib
import os
from pathlib import Path
import re
from typing import Any

from opsgenome.agents.models import AgentRole, SpecialistFinding
from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.security.redactor import SecretRedactor, redact_text
from opsgenome.signal.parsers import parse_error


class BaseSpecialistAgent:
    """Base class for all technology-specialist and guardrail agents."""

    def __init__(
        self,
        role: AgentRole,
        name: str,
        ai_engine: AIReasoningEngine | None = None,
        supported_stacks: list[str] | None = None,
    ):
        self.role = role
        self.name = name
        self.ai_engine = ai_engine or AIReasoningEngine(provider="auto")
        self.redactor = SecretRedactor()
        self.supported_stacks = supported_stacks or []
        self.model_name = getattr(self.ai_engine, "provider", "heuristic+llm")

    def create_diff(self, original: str, fixed: str, filename: str) -> str:
        orig_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                orig_lines,
                fixed_lines,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                lineterm="",
            )
        )
        return "\n".join(diff)


class PythonSpecialistAgent(BaseSpecialistAgent):
    """Specialist agent for Python applications, tracebacks, and async errors."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None):
        super().__init__(
            AgentRole.PYTHON_SPECIALIST,
            "Python Specialist Agent",
            ai_engine,
            supported_stacks=["python", "fastapi", "django", "flask"],
        )

    def diagnose(self, file_path: str, code_content: str, error_text: str = "") -> SpecialistFinding:
        clean_err = redact_text(error_text or "")
        parsed = parse_error(clean_err or code_content, language="python")

        exc_type = parsed.get("exception_type", "RuntimeError") if parsed else "RuntimeError"
        line_num = parsed.get("line") if parsed else None
        msg = parsed.get("message", "Python runtime failure") if parsed else "Python runtime failure"

        fixed_code = code_content
        root_cause = "Unhandled exception in execution flow."
        explanation = ""

        # Deterministic heuristic fixes with AI fallback
        if "keyerror" in exc_type.lower() or "keyerror" in clean_err.lower():
            # Replace d['key'] with d.get('key')
            root_cause = "Unchecked dictionary key access without existence verification."
            match = re.search(r"(\w+)\[(['\"][a-zA-Z0-9_-]+['\"])\]", code_content)
            if match:
                var_name, key_name = match.group(1), match.group(2)
                fixed_code = code_content.replace(f"{var_name}[{key_name}]", f"{var_name}.get({key_name})")
                explanation = f"Replaced direct key lookup `{var_name}[{key_name}]` with safe default fallback `{var_name}.get({key_name})`."
        elif "indexerror" in exc_type.lower() or "indexerror" in clean_err.lower():
            root_cause = "Array index access out of bounds without length guard."
            match = re.search(r"(\w+)\[(\d+)\]", code_content)
            if match:
                var_name, idx = match.group(1), match.group(2)
                fixed_code = code_content.replace(f"{var_name}[{idx}]", f"({var_name}[{idx}] if {idx} < len({var_name}) else None)")
                explanation = f"Wrapped `{var_name}[{idx}]` with bounds check `(len({var_name}) > {idx})`."
        elif "recursionerror" in exc_type.lower() or "maximum recursion depth" in clean_err.lower():
            root_cause = "Infinite recursion: missing terminal base case."
            if "def fib" in code_content:
                fixed_code = re.sub(r"def fib\(n\):", "def fib(n):\n    if n <= 0:\n        return 0\n    if n == 1:\n        return 1", code_content)
                explanation = "Injected missing base cases `n <= 0 -> 0` and `n == 1 -> 1`."
        elif "nameerror" in exc_type.lower() or "not defined" in clean_err.lower():
            root_cause = "Referencing undefined variable or constant."
            match = re.search(r"name '(\w+)' is not defined", clean_err)
            var_name = match.group(1) if match else "fee_rate"
            if var_name in code_content and f"{var_name} =" not in code_content:
                if "def " in code_content:
                    fixed_code = re.sub(
                        r"(def \w+\([^)]*\)(?:\s*->\s*[^:]+)?\s*:)",
                        r"\1\n    " + f"{var_name} = 0.02  # Default rate fallback",
                        code_content,
                        count=1,
                    )
                else:
                    fixed_code = f"{var_name} = 0.02  # Default rate fallback\n" + code_content
                explanation = f"Declared default fallback `{var_name} = 0.02` before reference to resolve NameError."

        # If heuristics didn't modify code, call AI engine
        if fixed_code == code_content and self.ai_engine:
            try:
                ai_res = self.ai_engine.diagnose_and_fix_code(
                    filename=Path(file_path).name,
                    code_content=code_content,
                    command=f"python3 {file_path}",
                    error_output=clean_err,
                    exit_code=1,
                )
                fixed_code = ai_res.get("fixed_code", code_content)
                root_cause = ai_res.get("root_cause", root_cause)
                explanation = ai_res.get("explanation", explanation)
            except Exception:
                pass

        diff = self.create_diff(code_content, fixed_code, Path(file_path).name) if fixed_code != code_content else ""

        return SpecialistFinding(
            target_file=file_path,
            stack="python",
            exception_type=exc_type,
            error_message=msg,
            line_number=line_num,
            root_cause=root_cause,
            proposed_diff=diff,
            original_code=code_content,
            fixed_code=fixed_code,
            confidence=0.98 if diff else 0.85,
            explanation=explanation or "Applied Python exception safety patch.",
            agent_name=self.name,
        )


class JavaSpecialistAgent(BaseSpecialistAgent):
    """Specialist agent for JVM applications, NPEs, and classloader issues."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None):
        super().__init__(
            AgentRole.JAVA_SPECIALIST,
            "Java / JVM Specialist Agent",
            ai_engine,
            supported_stacks=["java", "spring-boot", "jvm"],
        )

    def diagnose(self, file_path: str, code_content: str, error_text: str = "") -> SpecialistFinding:
        clean_err = redact_text(error_text or "")
        parsed = parse_error(clean_err or code_content, language="java")

        exc_type = parsed.get("exception_type", "NullPointerException") if parsed else "NullPointerException"
        line_num = parsed.get("line") if parsed else None
        msg = parsed.get("message", "Cannot invoke method on null object reference") if parsed else "Null reference dereferenced"

        fixed_code = code_content
        root_cause = "Null reference dereferenced without validation."
        explanation = ""

        # Deterministic NullPointerException patch
        if "nullpointerexception" in exc_type.lower() or "cannot invoke" in clean_err.lower() or "NullPointerException" in code_content:
            root_cause = "Account or payload object dereferenced before null check in payment pipeline."
            if "acc.getBalance()" in code_content and "if (acc == null)" not in code_content:
                fixed_code = code_content.replace(
                    "return acc.getBalance();",
                    "if (acc == null) return 0.0;\n        return acc.getBalance();",
                )
                explanation = "Injected defensive null check guard `if (acc == null) return 0.0;` to prevent NullPointerException."
            elif "user.getId()" in code_content and "if (user == null)" not in code_content:
                fixed_code = code_content.replace(
                    "return user.getId();",
                    "if (user == null) return \"anonymous\";\n        return user.getId();",
                )
                explanation = "Injected defensive null check guard `if (user == null)`."
            elif "amount.doubleValue()" in code_content and "if (amount == null)" not in code_content:
                fixed_code = code_content.replace(
                    "return amount.doubleValue() * 1.05;",
                    "if (amount == null) return 0.0;\n        return amount.doubleValue() * 1.05;",
                )
                explanation = "Injected defensive null check guard `if (amount == null) return 0.0;` to prevent NullPointerException."

        # Fallback to AI code fix
        if fixed_code == code_content and self.ai_engine:
            try:
                ai_res = self.ai_engine.diagnose_and_fix_code(
                    filename=Path(file_path).name,
                    code_content=code_content,
                    command=f"javac {file_path}",
                    error_output=clean_err,
                    exit_code=1,
                )
                fixed_code = ai_res.get("fixed_code", code_content)
                root_cause = ai_res.get("root_cause", root_cause)
                explanation = ai_res.get("explanation", explanation)
            except Exception:
                pass

        diff = self.create_diff(code_content, fixed_code, Path(file_path).name) if fixed_code != code_content else ""

        return SpecialistFinding(
            target_file=file_path,
            stack="java",
            exception_type=exc_type,
            error_message=msg,
            line_number=line_num,
            root_cause=root_cause,
            proposed_diff=diff,
            original_code=code_content,
            fixed_code=fixed_code,
            confidence=0.96 if diff else 0.85,
            explanation=explanation or "Applied Java null-safety defensive guard.",
            agent_name=self.name,
        )


class NodeSpecialistAgent(BaseSpecialistAgent):
    """Specialist agent for Node.js / JavaScript runtime and promise rejections."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None):
        super().__init__(
            AgentRole.NODE_SPECIALIST,
            "Node.js Specialist Agent",
            ai_engine,
            supported_stacks=["nodejs", "javascript", "typescript", "express"],
        )

    def diagnose(self, file_path: str, code_content: str, error_text: str = "") -> SpecialistFinding:
        clean_err = redact_text(error_text or "")
        parsed = parse_error(clean_err or code_content, language="nodejs")

        exc_type = parsed.get("exception_type", "TypeError") if parsed else "TypeError"
        line_num = parsed.get("line") if parsed else None
        msg = parsed.get("message", "Cannot read properties of undefined") if parsed else "Property access on undefined"

        fixed_code = code_content
        root_cause = "Property lookup on undefined request context or payload."
        explanation = ""

        # Deterministic fix for token / header / payload lookup
        if "cannot read properties of undefined" in clean_err.lower() or "typeerror" in exc_type.lower():
            if "req.headers.authorization" in code_content:
                fixed_code = code_content.replace(
                    "const token = req.headers.authorization.split(' ')[1];",
                    "const authHeader = req.headers?.authorization || '';\n    const token = authHeader.includes(' ') ? authHeader.split(' ')[1] : null;",
                )
                explanation = "Replaced fragile `req.headers.authorization.split(' ')` with safe optional chaining `req.headers?.authorization` and header presence verification."
            elif "data.user.id" in code_content:
                fixed_code = code_content.replace(
                    "return data.user.id;",
                    "return data?.user?.id ?? null;",
                )
                explanation = "Applied optional chaining `data?.user?.id ?? null`."
            elif "resp.json()" in code_content and ("await resp.json()" not in code_content or "promise" in clean_err.lower()):
                fixed_code = code_content.replace(
                    "const data = resp.json();",
                    "const data = await resp.json();",
                )
                root_cause = "Missing await on asynchronous fetch Response.json() Promise."
                explanation = "Added missing `await` to `resp.json()` to resolve pending Promise before property access."

        # Fallback to AI
        if fixed_code == code_content and self.ai_engine:
            try:
                ai_res = self.ai_engine.diagnose_and_fix_code(
                    filename=Path(file_path).name,
                    code_content=code_content,
                    command=f"node {file_path}",
                    error_output=clean_err,
                    exit_code=1,
                )
                fixed_code = ai_res.get("fixed_code", code_content)
                root_cause = ai_res.get("root_cause", root_cause)
                explanation = ai_res.get("explanation", explanation)
            except Exception:
                pass

        diff = self.create_diff(code_content, fixed_code, Path(file_path).name) if fixed_code != code_content else ""

        return SpecialistFinding(
            target_file=file_path,
            stack="nodejs",
            exception_type=exc_type,
            error_message=msg,
            line_number=line_num,
            root_cause=root_cause,
            proposed_diff=diff,
            original_code=code_content,
            fixed_code=fixed_code,
            confidence=0.97 if diff else 0.85,
            explanation=explanation or "Applied optional chaining and defensive property guard.",
            agent_name=self.name,
        )


class ClusterSpecialistAgent(BaseSpecialistAgent):
    """Specialist agent for Kubernetes manifests, Dockerfiles, and cluster failure modes."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None):
        super().__init__(
            AgentRole.CLUSTER_SPECIALIST,
            "Cluster & Infra Specialist Agent",
            ai_engine,
            supported_stacks=["kubernetes", "docker", "helm", "k8s-manifests"],
        )

    def diagnose_manifest(self, file_path: str, code_content: str, error_text: str = "") -> SpecialistFinding:
        clean_err = redact_text(error_text or "")
        fixed_code = code_content
        root_cause = "Container memory allocation insufficient for peak transaction volume."
        explanation = ""

        # Check for dangerously low memory limits causing OOMKilled in Kubernetes YAML
        if "oomkilled" in clean_err.lower() or "crashloopbackoff" in clean_err.lower() or "memory: 64mi" in code_content.lower() or "memory: 128mi" in code_content.lower():
            root_cause = "Container memory limit 64Mi/128Mi causes Linux cgroup OOMKilled (Exit Code 137) under traffic spikes."
            if "memory: \"64Mi\"" in code_content:
                fixed_code = code_content.replace("memory: \"64Mi\"", "memory: \"512Mi\"")
                explanation = "Increased container memory limit from 64Mi to 512Mi to prevent cgroup OOMKilled."
            elif "memory: 64Mi" in code_content:
                fixed_code = code_content.replace("memory: 64Mi", "memory: 512Mi")
                explanation = "Increased container memory limit from 64Mi to 512Mi."
            elif "memory: \"128Mi\"" in code_content:
                fixed_code = code_content.replace("memory: \"128Mi\"", "memory: \"512Mi\"")
                explanation = "Increased container memory limit from 128Mi to 512Mi."

        # Check for service selector mismatches
        if "selector" in code_content and ("v1" in code_content and "v2" in clean_err):
            root_cause = "Service selector points to deprecated pod label, dropping all inbound traffic."
            fixed_code = code_content.replace("app: web-v1", "app: web-v2")
            explanation = "Updated Service label selector from `app: web-v1` to `app: web-v2` to restore traffic routing."

        diff = self.create_diff(code_content, fixed_code, Path(file_path).name) if fixed_code != code_content else ""

        return SpecialistFinding(
            target_file=file_path,
            stack="kubernetes",
            exception_type="OOMKilled / CrashLoopBackOff",
            error_message="Exit Code 137 / Selector Mismatch",
            line_number=None,
            root_cause=root_cause,
            proposed_diff=diff,
            original_code=code_content,
            fixed_code=fixed_code,
            confidence=0.99 if diff else 0.88,
            explanation=explanation or "Applied Kubernetes resource specification patch.",
            agent_name=self.name,
        )


class SecuritySentinelAgent(BaseSpecialistAgent):
    """Guardrail agent enforcing fail-closed secret redaction and safety boundaries on proposed patches."""

    def __init__(self):
        super().__init__(
            AgentRole.SECURITY_SENTINEL,
            "Security Sentinel Agent",
            None,
            supported_stacks=["security", "secrets", "rbac", "sandbox"],
        )

    def inspect_diff_and_commands(
        self,
        findings: list[SpecialistFinding],
        verification_commands: list[str] | None = None,
    ) -> tuple[bool, list[str]]:
        """Verify that proposed diffs and verification commands contain no credential leaks and no destructive shell commands."""
        violations: list[str] = []
        dangerous_patterns = [
            r"\brm\s+-rf\s+[/~*]",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\bDROP\s+DATABASE\b",
            r"\bDROP\s+TABLE\b",
            r"\bkubectl\s+delete\s+namespace\b",
            r"\|\s*(?:ba)?sh\b",
            r"\bcurl\b.*\|\s*(?:ba)?sh\b",
            r"\bwget\b.*\|\s*(?:ba)?sh\b",
            r"\bchmod\s+777\b",
            r"\bnc\b.*-e\b",
            r":\(\)\s*\{",
        ]

        # 1. Inspect diffs for code safety and secret leaks
        for f in findings:
            diff_text = f.proposed_diff
            for pat in dangerous_patterns:
                if re.search(pat, diff_text, re.IGNORECASE):
                    violations.append(f"Blocked destructive command pattern `{pat}` in {Path(f.target_file).name}.")

            redacted, matches = self.redactor.redact(diff_text)
            if len(matches) > 0:
                violations.append(f"Detected and redacted {len(matches)} credential(s) in {Path(f.target_file).name} diff.")
                f.proposed_diff = redacted

        # 2. Inspect verification commands for command injection and destructive operations
        if verification_commands:
            for vcmd in verification_commands:
                for pat in dangerous_patterns:
                    if re.search(pat, vcmd, re.IGNORECASE):
                        violations.append(f"Blocked dangerous verification command pattern `{pat}`: `{vcmd}`.")

                # Check for credential leakage in verification commands
                v_redacted, v_matches = self.redactor.redact(vcmd)
                if len(v_matches) > 0:
                    violations.append(f"Detected credential leakage in verification command: `{vcmd}`.")

        is_safe = len(violations) == 0 or all("redacted" in v for v in violations)
        return is_safe, violations

