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

from dataclasses import dataclass, field
import difflib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.security.redactor import redact_text
from opsgenome.signal.log_distiller import SemanticLogDistiller
from opsgenome.storage.db import DatabaseManager


def safe_subprocess_run(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: float = 15.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute command safely without shell=True to prevent command injection."""
    if isinstance(cmd, str):
        tokens = shlex.split(cmd)
    else:
        tokens = list(cmd)

    if not tokens:
        return subprocess.CompletedProcess(args=tokens, returncode=1, stdout="", stderr="Error: Empty command string.")

    try:
        return subprocess.run(
            tokens,
            shell=False,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as err:
        return subprocess.CompletedProcess(
            args=tokens,
            returncode=127,
            stdout="",
            stderr=f"Executable not found: {err}",
        )
    except subprocess.TimeoutExpired as err:
        return subprocess.CompletedProcess(
            args=tokens,
            returncode=124,
            stdout=err.stdout or "" if isinstance(err.stdout, str) else "",
            stderr=f"Command timed out after {timeout} seconds.",
        )



@dataclass
class FailureContext:
    command: str
    target_file: str
    exit_code: int
    stdout: str
    stderr: str
    cwd: str
    call_stack_files: list[str] = field(default_factory=list)


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
                cmd_tokens = [sys.executable, str(target_path)]
            elif ext in (".js", ".mjs"):
                cmd_tokens = ["node", str(target_path)]
            elif ext == ".sh":
                cmd_tokens = ["bash", str(target_path)]
            else:
                cmd_tokens = [sys.executable, str(target_path)]
            command = " ".join(shlex.quote(t) for t in cmd_tokens)
            proc = safe_subprocess_run(cmd_tokens, cwd=work_dir, timeout=15)
            err_comb = proc.stderr + "\n" + proc.stdout
            stack_files = self.extract_traceback_chain(err_comb, work_dir)
            return FailureContext(
                command=command,
                target_file=str(target_path.resolve()),
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                cwd=work_dir,
                call_stack_files=stack_files,
            )

        # Case 2: Target is an explicit command string
        if target:
            command = target
            proc = safe_subprocess_run(command, cwd=work_dir, timeout=15)
            err_comb = proc.stderr + "\n" + proc.stdout
            stack_files = self.extract_traceback_chain(err_comb, work_dir)
            target_file = self.extract_target_file(err_comb, command, work_dir)
            return FailureContext(
                command=command,
                target_file=target_file,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                cwd=work_dir,
                call_stack_files=stack_files,
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
                        out = latest.stdout_snippet or ""
                        err_comb = err + "\n" + out
                        stack_files = self.extract_traceback_chain(err_comb, work_dir)
                        target_file = self.extract_target_file(err_comb, cmd, work_dir)
                        return FailureContext(
                            command=cmd,
                            target_file=target_file,
                            exit_code=latest.exit_code,
                            stdout=out,
                            stderr=err,
                            cwd=latest.cwd or work_dir,
                            call_stack_files=stack_files,
                        )
            except Exception:
                pass

        raise ValueError("No target command or script specified, and no recent failure recorded in local database.")

    @staticmethod
    def extract_traceback_chain(error_output: str, cwd: str) -> list[str]:
        """Extract all project-level source files in the traceback call chain."""
        candidates: list[str] = []

        # 1. Python frames: File "...", line X
        py_matches = re.findall(r'File "([^"]+)", line \d+', error_output)
        for path_str in py_matches:
            if "site-packages" in path_str or "lib/python" in path_str or path_str.startswith("<"):
                continue
            p = Path(path_str)
            resolved = p if p.is_absolute() else (Path(cwd) / p).resolve()
            if resolved.is_file() and str(resolved) not in candidates:
                candidates.append(str(resolved))

        # 2. Node.js / JavaScript frames: at ... (/path/to/file.js:12:34) or at /path/to/file.js:12:34
        node_matches = re.findall(r'(?:at\s+(?:[^\(\s]+\s+)?\(|\bat\s+)([a-zA-Z0-9_\-\./\\]+\.(?:js|mjs|cjs|ts)):\d+:\d+', error_output)
        for path_str in node_matches:
            if "node_modules" in path_str or path_str.startswith("node:"):
                continue
            p = Path(path_str)
            resolved = p if p.is_absolute() else (Path(cwd) / p).resolve()
            if resolved.is_file() and str(resolved) not in candidates:
                candidates.append(str(resolved))

        # 3. Shell script errors: script.sh: line X:
        sh_matches = re.findall(r'([a-zA-Z0-9_\-\./\\]+\.sh):\s*line\s+\d+:', error_output)
        for path_str in sh_matches:
            p = Path(path_str)
            resolved = p if p.is_absolute() else (Path(cwd) / p).resolve()
            if resolved.is_file() and str(resolved) not in candidates:
                candidates.append(str(resolved))

        # 4. Config files: in "config.yaml", line X
        cfg_matches = re.findall(r'(?:in\s+["\']|file\s+["\'])([a-zA-Z0-9_\-\./\\]+\.(?:ya?ml|json|toml))["\']', error_output, re.IGNORECASE)
        for path_str in cfg_matches:
            p = Path(path_str)
            resolved = p if p.is_absolute() else (Path(cwd) / p).resolve()
            if resolved.is_file() and str(resolved) not in candidates:
                candidates.append(str(resolved))

        return candidates

    @classmethod
    def extract_target_file(cls, error_output: str, command: str, cwd: str) -> str:
        """Extract the offending project source file from Python/Node/Shell tracebacks or command string."""
        chain = cls.extract_traceback_chain(error_output, cwd)
        if chain:
            return chain[-1]

        # Inspect command string arguments for filename
        for token in command.split():
            clean_token = token.strip("\"'")
            candidate = (Path(cwd) / clean_token).resolve()
            if candidate.is_file() and candidate.suffix in (".py", ".js", ".mjs", ".sh", ".json", ".yaml", ".yml", ".toml"):
                return str(candidate)

        # Fallback to any matched traceback file
        traceback_matches = re.findall(r'File "([^"]+)", line \d+', error_output)
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

        # Multi-file stack context
        stack_note = ""
        if len(failure.call_stack_files) > 1:
            rel_names = [Path(f).name for f in failure.call_stack_files]
            stack_note = f"\n[Multi-File Call Stack: {' -> '.join(rel_names)}]"

        error_to_send = (distilled.distilled_text or safe_error) + stack_note

        diagnosis = self.ai_engine.diagnose_and_fix_code(
            filename=file_path.name,
            code_content=safe_code,
            command=failure.command,
            error_output=error_to_send,
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
    def verify_remediation(command: str | list[str], cwd: str | None = None, timeout: float = 15.0) -> tuple[int, str, str]:
        """Execute closed-loop verification command on live environment safely without shell=True."""
        work_dir = cwd or os.getcwd()
        proc = safe_subprocess_run(command, cwd=work_dir, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
