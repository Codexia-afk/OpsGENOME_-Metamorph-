"""Autonomous Code Diagnostics, Diff Generation, and Closed-Loop Verification Engine.

Supports diagnosing application code errors (e.g., Python RecursionError, IndexError,
ZeroDivisionError, syntax mistakes) using Google Gemini, Anthropic Claude, or offline
deterministic heuristics.

Enforces:
1. Fail-closed secret redaction before any code/telemetry is submitted to AI.
2. Safe file backup (.bak) creation before applying any patch.
3. Closed-loop execution verification to validate recovery on the live system.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.security.redactor import redact_text
from opsgenome.signal.log_distiller import SemanticLogDistiller
from opsgenome.storage.db import DatabaseManager


@dataclass
class FailureContext:
    command: str
    target_file: str
    exit_code: int
    stdout: str
    stderr: str
    cwd: str


@dataclass
class CodeFixResult:
    target_file: str
    command: str
    symptom: str
    root_cause: str
    diff: str
    original_code: str
    fixed_code: str
    explanation: str
    backup_path: str | None = None
    applied: bool = False
    verified: bool = False
    verification_exit_code: int | None = None
    verification_stdout: str = ""
    verification_stderr: str = ""
    error_message: str | None = None
    raw_bytes: int = 0
    distilled_bytes: int = 0
    compression_percent: float = 0.0
    cache_hit: bool = False


class CodeFixEngine:
    """End-to-end engine for diagnosing and auto-fixing application code errors."""

    def __init__(self, ai_engine: AIReasoningEngine | None = None, db: DatabaseManager | None = None):
        self.ai_engine = ai_engine or AIReasoningEngine()
        self.db = db

    def capture_failure(self, target: str | None = None, cwd: str | None = None) -> FailureContext:
        """Capture command execution failure, traceback, and offending target file."""
        work_dir = cwd or os.getcwd()

        # Case 1: Target is an existing script/file path
        if target and (Path(work_dir) / target).is_file():
            target_path = Path(work_dir) / target
            ext = target_path.suffix.lower()
            if ext == ".py":
                command = f"{sys.executable} {target}"
            elif ext in (".js", ".mjs"):
                command = f"node {target}"
            elif ext == ".sh":
                command = f"bash {target}"
            else:
                command = f"python3 {target}"
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=work_dir, timeout=15)
            return FailureContext(
                command=command,
                target_file=str(target_path.resolve()),
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                cwd=work_dir,
            )

        # Case 2: Target is an explicit command string
        if target:
            command = target
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=work_dir, timeout=15)
            target_file = self.extract_target_file(proc.stderr, command, work_dir)
            return FailureContext(
                command=command,
                target_file=target_file,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                cwd=work_dir,
            )

        # Case 3: Target is None; check database for most recent failure
        if self.db:
            try:
                active_inc = self.db.get_active_incident()
                if active_inc:
                    events = self.db.get_events_for_incident(active_inc.id)
                    failed_events = [e for e in events if e.exit_code != 0]
                    if failed_events:
                        latest = failed_events[-1]
                        cmd = latest.raw_command or latest.command_redacted
                        err = latest.stderr_snippet or ""
                        target_file = self.extract_target_file(err, cmd, work_dir)
                        return FailureContext(
                            command=cmd,
                            target_file=target_file,
                            exit_code=latest.exit_code,
                            stdout=latest.stdout_snippet or "",
                            stderr=err,
                            cwd=latest.cwd or work_dir,
                        )
            except Exception:
                pass

        raise ValueError("No target command or script specified, and no recent failure recorded in local database.")

    @staticmethod
    def extract_target_file(error_output: str, command: str, cwd: str) -> str:
        """Extract the offending project source file from a Python/Node traceback or command string."""
        # 1. Inspect Python traceback frames in reverse order (closest to site of error)
        traceback_matches = re.findall(r'File "([^"]+)", line \d+', error_output)
        for path_str in reversed(traceback_matches):
            p = Path(path_str)
            # Exclude standard library and third-party site-packages
            if "site-packages" in path_str or "lib/python" in path_str or path_str.startswith("<"):
                continue
            resolved = p if p.is_absolute() else (Path(cwd) / p).resolve()
            if resolved.is_file():
                return str(resolved)

        # 2. Inspect command string arguments for filename
        for token in command.split():
            clean_token = token.strip("\"'")
            candidate = (Path(cwd) / clean_token).resolve()
            if candidate.is_file() and candidate.suffix in (".py", ".js", ".sh", ".json", ".yaml", ".yml"):
                return str(candidate)

        # 3. Fallback to any matched traceback file
        if traceback_matches:
            return traceback_matches[-1]

        raise FileNotFoundError(f"Could not isolate target source file from command: `{command}` and traceback.")

    def generate_fix(self, failure: FailureContext) -> CodeFixResult:
        """Analyze failure context and synthesize patched code and unified diff."""
        file_path = Path(failure.target_file)
        if not file_path.is_file():
            raise FileNotFoundError(f"Target source file not found at: {failure.target_file}")

        original_code = file_path.read_text(encoding="utf-8")

        # Security Boundary: Redact any accidental tokens or credentials in code or traceback
        safe_code = redact_text(original_code)
        safe_error = redact_text(failure.stderr or failure.stdout)

        # Semantic Log Distillation: Compress noisy traceback frames into minimal semantic signature
        distilled = SemanticLogDistiller.distill_traceback(safe_error)

        diagnosis = self.ai_engine.diagnose_and_fix_code(
            filename=file_path.name,
            code_content=safe_code,
            command=failure.command,
            error_output=distilled.distilled_text or safe_error,
            exit_code=failure.exit_code,
        )

        fixed_code = diagnosis.get("fixed_code", original_code)
        diff_text = self.create_unified_diff(original_code, fixed_code, file_path.name)

        return CodeFixResult(
            target_file=str(file_path),
            command=failure.command,
            symptom=diagnosis.get("symptom", "Process execution failed"),
            root_cause=diagnosis.get("root_cause", "Unspecified code error"),
            diff=diff_text,
            original_code=original_code,
            fixed_code=fixed_code,
            explanation=diagnosis.get("explanation", ""),
            raw_bytes=distilled.raw_bytes,
            distilled_bytes=distilled.distilled_bytes,
            compression_percent=distilled.compression_percent,
            cache_hit=diagnosis.get("cache_hit", False),
        )

    @staticmethod
    def create_unified_diff(original: str, fixed: str, filename: str) -> str:
        """Generate standard unified diff formatted string."""
        orig_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                fixed_lines,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                lineterm="",
            )
        )
        return "\n".join(diff_lines)

    @staticmethod
    def apply_patch(result: CodeFixResult) -> str:
        """Backup target file and write corrected source code."""
        file_path = Path(result.target_file)
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copyfile(file_path, backup_path)
        file_path.write_text(result.fixed_code, encoding="utf-8")
        result.backup_path = str(backup_path)
        result.applied = True
        return str(backup_path)

    @staticmethod
    def rollback(result: CodeFixResult) -> None:
        """Restore target file from backup."""
        if result.backup_path and Path(result.backup_path).is_file():
            shutil.copyfile(result.backup_path, result.target_file)
            os.remove(result.backup_path)
            result.applied = False
            result.backup_path = None

    @staticmethod
    def verify_remediation(command: str, cwd: str | None = None, timeout: float = 15.0) -> tuple[int, str, str]:
        """Execute closed-loop verification command on live environment."""
        work_dir = cwd or os.getcwd()
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
