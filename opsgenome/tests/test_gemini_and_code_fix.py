"""Unit and Integration Tests for Google Gemini Integration and Code Auto-Fix Engine.

Verifies:
1. Multi-provider AIReasoningEngine initialization & auto-selection (Gemini, Claude, Offline).
2. Gemini API request formatting and structured JSON candidate response parsing.
3. CodeFixEngine offline heuristic repair on broken Fibonacci code.
4. Fail-closed secret redaction on code and traceback before AI synthesis.
5. Safe backup creation and rollback mechanism.
6. Closed-loop verification re-execution.
7. opsgenome fix CLI command invocation via Click CliRunner.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from opsgenome.ai.code_fixer import CodeFixEngine, CodeFixResult, FailureContext
from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.cli.main import cli
from opsgenome.storage.models import Event, Incident


def test_ai_provider_auto_selection(monkeypatch):
    """Verify provider auto-selection based on environment variables."""
    # Case 1: GEMINI_API_KEY present -> selects Gemini
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine_gemini = AIReasoningEngine(provider="auto")
    assert engine_gemini.provider == "gemini"
    assert "gemini" in engine_gemini.model

    # Case 2: ANTHROPIC_API_KEY present (no Gemini) -> selects Anthropic
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-claude-key")
    engine_claude = AIReasoningEngine(provider="auto")
    assert engine_claude.provider == "anthropic"
    assert "claude" in engine_claude.model

    # Case 3: No keys -> selects Offline Heuristic
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine_offline = AIReasoningEngine(provider="auto")
    assert engine_offline.provider == "offline"
    assert engine_offline.model == "deterministic-offline"


def test_gemini_chain_assembly_mocked():
    """Verify Gemini structured JSON API call and candidate response parsing."""
    engine = AIReasoningEngine(provider="gemini", gemini_api_key="fake-gemini-key")

    incident = Incident(id="inc-k8s-1", service="payments", title="Pod CrashLoopBackOff")
    event = Event(id="ev-1", incident_id=incident.id, raw_command="kubectl rollout undo deployment/payments", exit_code=0, signal_weight=0.85)

    mock_response_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "symptom": "Pod CrashLoopBackOff",
                                "disambiguation_required": False,
                                "hypothesis": "Invalid ConfigMap syntax in deployment",
                                "ranked_hypotheses": [
                                    {
                                        "rank": 1,
                                        "hypothesis": "Invalid ConfigMap syntax",
                                        "candidate_event_ids": ["ev-1"],
                                        "supporting_evidence": ["Rollout undo resolved pod state"],
                                        "confidence": 0.95,
                                        "distinguishing_factor": "Rollout undo restored 1/1 Ready"
                                    }
                                ],
                                "evidence_event_ids": ["ev-1"],
                                "fix_event_ids": ["ev-1"],
                                "negative_knowledge_event_ids": [],
                                "outcome": "resolved",
                                "reasoning_notes": "Single mutation delta restored health."
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_json
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_resp):
        chain = engine.call_1_chain_assembly(incident, [event])
        assert chain["outcome"] == "resolved"
        assert chain["fix_event_ids"] == ["ev-1"]
        assert chain["ranked_hypotheses"][0]["confidence"] == 0.95


def test_gemini_code_fix_api_call_mocked():
    """Verify Gemini code fix call synthesizes corrected code structure."""
    engine = AIReasoningEngine(provider="gemini", gemini_api_key="fake-gemini-key")

    mock_response_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "symptom": "RecursionError: maximum recursion depth exceeded",
                                "root_cause": "Missing base cases in fibonacci function",
                                "fixed_code": "def fib(n):\n    if n <= 0: return 0\n    if n == 1: return 1\n    return fib(n-1) + fib(n-2)\n",
                                "explanation": "Added base cases to guarantee termination.",
                                "diff_summary": "Added base cases"
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_json
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_resp):
        res = engine.diagnose_and_fix_code(
            filename="fib.py",
            code_content="def fib(n):\n    return fib(n-1) + fib(n-2)\n",
            command="python3 fib.py",
            error_output="RecursionError: maximum recursion depth exceeded",
            exit_code=1,
        )
        assert "RecursionError" in res["symptom"]
        assert "if n <= 0" in res["fixed_code"]


def test_code_fixer_fibonacci_offline_heuristic():
    """Verify offline deterministic repair of recursive Fibonacci without base cases."""
    engine = CodeFixEngine()

    with tempfile.TemporaryDirectory() as tmpdir:
        broken_file = Path(tmpdir) / "broken_fib.py"
        broken_file.write_text(
            "def fib(n):\n"
            "    return fib(n - 1) + fib(n - 2)\n\n"
            "print([fib(i) for i in range(5)])\n"
        )

        failure = engine.capture_failure(str(broken_file))
        assert failure.exit_code != 0
        assert "RecursionError" in failure.stderr or "maximum recursion depth" in failure.stderr

        fix_res = engine.generate_fix(failure)
        assert "RecursionError" in fix_res.symptom
        assert "Missing recursive base termination cases" in fix_res.root_cause
        assert "+" in fix_res.diff
        assert "return 0" in fix_res.fixed_code

        # Apply patch and verify
        backup = engine.apply_patch(fix_res)
        assert Path(backup).is_file()

        retcode, stdout, _ = engine.verify_remediation(fix_res.command)
        assert retcode == 0
        assert "[0, 1, 1, 2, 3]" in stdout

        # Test Rollback
        engine.rollback(fix_res)
        assert not Path(backup).is_file()
        assert "return fib(n - 1) + fib(n - 2)" in broken_file.read_text()


def test_code_fixer_redaction_before_ai_call():
    """Verify embedded secrets in code or traceback are redacted before AI diagnosis."""
    engine = CodeFixEngine()

    with tempfile.TemporaryDirectory() as tmpdir:
        leak_file = Path(tmpdir) / "leak_script.py"
        leak_file.write_text(
            "# Config: AWS_KEY=AKIAIOSFODNN7EXAMPLE\n"
            "def fib(n):\n"
            "    return fib(n - 1) + fib(n - 2)\n\n"
            "print(fib(5))\n"
        )

        failure = engine.capture_failure(str(leak_file))
        
        # Intercept AI engine call to check redaction
        captured_prompts = []
        def mock_diagnose(filename, code_content, command, error_output, exit_code):
            captured_prompts.append(code_content)
            return {
                "symptom": "RecursionError",
                "root_cause": "Missing base case",
                "fixed_code": code_content,
                "explanation": "safe",
                "diff_summary": "",
            }

        engine.ai_engine.diagnose_and_fix_code = mock_diagnose
        engine.generate_fix(failure)

        assert len(captured_prompts) == 1
        # Raw secret MUST NOT be present in prompt sent to AI!
        assert "AKIAIOSFODNN7EXAMPLE" not in captured_prompts[0]
        assert "[REDACTED_AWS_KEY]" in captured_prompts[0]


def test_cli_fix_command_runner():
    """Verify opsgenome fix and opsgenome auto-fix CLI commands execute cleanly."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        script = Path(tmpdir) / "fib_test.py"
        script.write_text(
            "def fib(n):\n"
            "    return fib(n - 1) + fib(n - 2)\n\n"
            "print(fib(4))\n"
        )

        # Run with --auto-approve
        result = runner.invoke(cli, ["fix", str(script), "--auto-approve"])
        assert result.exit_code == 0
        assert "OpsGenome AI Autonomous Incident Fixer" in result.output
        assert "Proposed Remediation Patch" in result.output
        assert "VERIFICATION PASSED" in result.output

        # Verify auto-fix alias exists and exhibits identical help
        alias_res = runner.invoke(cli, ["auto-fix", "--help"])
        assert alias_res.exit_code == 0
        assert "Autonomous AI Code & Incident Fixer" in alias_res.output
