"""Unit and Integration Tests for Semantic Log Distiller and API Call Minimization.

Verifies:
1. Traceback recursive cycle compression (>85% compression on stack growth).
2. Kubernetes log stream deduplication, timestamp scrubbing, and hex pointer masking.
3. ANSI escape sequence removal.
4. In-memory idempotency cache preventing duplicate LLM API calls.
5. CodeFixEngine integration with telemetry distillation metrics.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from opsgenome.ai.code_fixer import CodeFixEngine
from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.signal.log_distiller import SemanticLogDistiller


def test_traceback_recursion_compression():
    """Verify that multi-thousand line recursive stack tracebacks are compressed by >85%."""
    frame = (
        '  File "/Users/dev/project/calc.py", line 15, in recurse\n'
        '    return recurse(n - 1) + recurse(n - 2)\n'
    )
    raw_traceback = (
        "Traceback (most recent call last):\n"
        + (frame * 500)
        + "RecursionError: maximum recursion depth exceeded in comparison\n"
    )

    result = SemanticLogDistiller.distill_traceback(raw_traceback)

    assert result.exception_type == "RecursionError"
    assert result.compression_percent > 85.0
    assert result.distilled_bytes < result.raw_bytes
    assert "CYCLIC_RECURSION" in result.distilled_text
    assert result.semantic_summary["recursion_detected"] is True
    assert result.semantic_summary["line_number"] == 15


def test_kubernetes_log_deduplication_and_noise_scrubbing():
    """Verify ISO timestamps, thread IDs, hex pointers, and duplicate lines are distilled."""
    raw_logs = """
\x1b[31m2026-09-12T18:31:01.001Z [pid: 4092, tid: 0x7fae12] ERROR: Connection refused to postgres:5432 at 0x7ffee23b\x1b[0m
\x1b[31m2026-09-12T18:31:02.002Z [pid: 4092, tid: 0x7fae12] ERROR: Connection refused to postgres:5432 at 0x7ffee23b\x1b[0m
\x1b[31m2026-09-12T18:31:03.003Z [pid: 4092, tid: 0x7fae12] ERROR: Connection refused to postgres:5432 at 0x7ffee23b\x1b[0m
\x1b[31m2026-09-12T18:31:04.004Z [pid: 4092, tid: 0x7fae12] ERROR: Connection refused to postgres:5432 at 0x7ffee23b\x1b[0m
\x1b[32m2026-09-12T18:31:05.005Z INFO: Retrying health probe\x1b[0m
\x1b[31m2026-09-12T18:31:06.006Z FATAL: CrashLoopBackOff container terminated\x1b[0m
"""
    result = SemanticLogDistiller.distill_log_stream(raw_logs)

    # 1. Verify ANSI color codes are gone
    assert "\x1b[" not in result.distilled_text
    # 2. Verify ISO timestamps are stripped
    assert "2026-09-12" not in result.distilled_text
    # 3. Verify hex pointers are masked
    assert "0x7ffee23b" not in result.distilled_text
    assert "[PTR]" in result.distilled_text
    # 4. Verify frequency deduplication (e.g. x4)
    assert "(x4)" in result.distilled_text
    assert "CrashLoopBackOff" in result.distilled_text
    assert result.compression_percent > 40.0


def test_idempotency_cache_prevents_duplicate_api_calls():
    """Verify that repeated failure signatures return cached fixes with 0 HTTP calls."""
    engine = AIReasoningEngine(provider="gemini", gemini_api_key="mock-key")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"symptom": "TestBug", "root_cause": "Typo", "fixed_code": "x = 1", "explanation": "fixed", "diff_summary": "fixed"}'
                        }
                    ]
                }
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        # First Call: Hits API
        res1 = engine.diagnose_and_fix_code(
            filename="app.py",
            code_content="x = 0",
            command="python3 app.py",
            error_output="AssertionError: 0 != 1",
            exit_code=1,
        )
        assert res1["cache_hit"] is False
        assert mock_post.call_count == 1

        # Second Call with identical signature: Hits Memory Cache (0 HTTP calls!)
        res2 = engine.diagnose_and_fix_code(
            filename="app.py",
            code_content="x = 0",
            command="python3 app.py",
            error_output="AssertionError: 0 != 1",
            exit_code=1,
        )
        assert res2["cache_hit"] is True
        assert res2["fixed_code"] == "x = 1"
        # mock_post must STILL be 1 (zero additional API calls!)
        assert mock_post.call_count == 1


def test_code_fixer_reports_compression_metrics():
    """Verify CodeFixEngine generates and populates distillation metrics."""
    fixer = CodeFixEngine()
    broken_code = (
        "def fib(n):\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "print(fib(5))\n"
    )

    # Mock failure context with verbose traceback
    from opsgenome.ai.code_fixer import FailureContext
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "fib.py"
        tmp_file.write_text(broken_code)

        failure = FailureContext(
            command=f"python3 {tmp_file}",
            target_file=str(tmp_file),
            exit_code=1,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                + ('  File "fib.py", line 2, in fib\n    return fib(n-1) + fib(n-2)\n' * 50)
                + "RecursionError: maximum recursion depth exceeded\n"
            ),
            cwd=tmpdir,
        )

        res = fixer.generate_fix(failure)
        assert res.raw_bytes > 0
        assert res.distilled_bytes > 0
        assert res.distilled_bytes < res.raw_bytes
        assert res.compression_percent > 50.0
