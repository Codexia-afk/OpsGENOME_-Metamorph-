"""Unit tests for Stage A Streaming Log Scanner, Redaction, and Multi-Source Aggregation."""

from __future__ import annotations

import collections.abc
import io
import pytest

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.security.redactor import EventSanitizer, SecurityBoundaryViolation
from opsgenome.signal.streaming_scanner import (
    CandidateWindow,
    LogLine,
    StreamingLogScanner,
    merge_log_streams,
)
from opsgenome.storage.models import Incident


def test_k8s_critical_patterns_scored_high():
    scanner = StreamingLogScanner()

    # Verify key Kubernetes error signals score >= 0.85
    k8s_errors = [
        "Back-off 5m0s restarting failed container=api-server pod=core-svc-abc",
        "Pod core-payment-service is CrashLoopBackOff",
        "Process in container worker-1 was OOMKilled (exit code 137)",
        "Failed to pull image 'redis:7.0': ImagePullBackOff",
        "Liveness probe failed: HTTP probe failed with statuscode: 500",
        "Readiness probe failed: connection refused on port 8080",
        "dial tcp 10.96.0.1:443: connect: connection refused",
        "context deadline exceeded while waiting for database lock",
        "CRITICAL: Unhandled worker panic occurred during batch process",
        'HTTP/1.1 "POST /checkout" 500 Internal Server Error',
    ]

    for err_line in k8s_errors:
        score, sig_type = scanner.score_line(err_line)
        assert score >= 0.85, f"Expected high score for '{err_line}', got {score} ({sig_type})"


def test_noise_patterns_suppressed():
    scanner = StreamingLogScanner()

    noise_lines = [
        '10.244.0.1 - - [12/Sep/2026:12:00:00] "GET /healthz HTTP/1.1" 200 12',
        '10.244.0.1 - - [12/Sep/2026:12:00:01] "GET /ready HTTP/1.1" 200 4',
        "kube-probe/1.28 GET /metrics 200",
        "[INFO] Worker 4 heartbeat ok, pool healthy",
        "[INFO] Database retry succeeded after 1 attempt",
        "[INFO] Background sync completed in 14ms",
        "Routine info line with no issues",
    ]

    for line in noise_lines:
        score, sig_type = scanner.score_line(line)
        assert score < 0.25, f"Expected low noise score for '{line}', got {score} ({sig_type})"


def test_streaming_window_captures_context_and_parses_traceback():
    scanner = StreamingLogScanner(context_before_lines=3, context_after_lines=4)

    # 10 lines: 3 before, 1 trigger, 4 after, 2 trailing
    stream = [
        "2026-09-12T10:00:01Z [INFO] Service starting up",
        "2026-09-12T10:00:02Z [INFO] Initializing payment connection",
        "2026-09-12T10:00:03Z [INFO] Received order payload #402",
        "2026-09-12T10:00:04Z Traceback (most recent call last):",
        '  File "/app/checkout.py", line 17, in init_payment_gateway',
        '    token = config["api_secret_key"]',
        "KeyError: 'api_secret_key'",
        "2026-09-12T10:00:05Z [INFO] Shutdown signal handled",
        "2026-09-12T10:00:06Z [INFO] Server stopped",
    ]

    result = scanner.scan_stream(stream, source_pod="pod-checkout-89", source_container="checkout-app")

    assert result.total_lines_scanned == 9
    assert result.high_confidence_signal_found is True
    assert result.top_candidate is not None

    top = result.top_candidate
    assert top.trigger_line.line_number == 4
    assert "Traceback" in top.trigger_line.raw_text
    assert len(top.context_before) == 3
    assert len(top.context_after) == 4
    assert top.trigger_line.source_pod == "pod-checkout-89"

    # Verify structured error parsing via parser registry integration
    assert top.parsed_error is not None
    assert top.parsed_error["language"] == "python"
    assert top.parsed_error["exception_type"] == "KeyError"
    assert top.parsed_error["line"] == 17
    assert top.parsed_error["source_pod"] == "pod-checkout-89"


def test_generator_input_consumed_lazily_without_materializing_list():
    scanner = StreamingLogScanner()

    consumed_count = 0

    def lazy_log_generator():
        nonlocal consumed_count
        for i in range(100):
            consumed_count += 1
            if i == 50:
                yield "2026-09-12T10:00:00Z FATAL: Database host unreachable (CrashLoopBackOff)"
            else:
                yield f"2026-09-12T10:00:00Z [INFO] Request {i} handled 200 OK"

    gen = lazy_log_generator()
    assert isinstance(gen, collections.abc.Iterator)

    result = scanner.scan_stream(gen)
    assert consumed_count == 100
    assert result.total_lines_scanned == 100
    assert result.high_confidence_signal_found is True
    assert result.top_candidate is not None
    assert result.top_candidate.trigger_line.line_number == 51


def test_pure_noise_log_reports_no_clear_root_cause():
    scanner = StreamingLogScanner(min_signal_threshold=0.60)

    noise_stream = [
        f"2026-09-12T10:00:{i%60:02d}Z [INFO] GET /healthz 200 OK duration=2ms"
        for i in range(500)
    ]

    result = scanner.scan_stream(noise_stream)

    assert result.total_lines_scanned == 500
    assert result.high_confidence_signal_found is False
    assert result.top_candidate is None
    assert len(result.candidates) == 0
    assert "No clear root cause found" in result.summary_message


def test_multi_source_log_merging_preserves_provenance_and_chronology():
    # 2 separate pod streams with interleaving timestamps
    stream_a = [
        "2026-09-12T10:00:01Z [INFO] Pod A initialized",
        "2026-09-12T10:00:03Z [INFO] Pod A processing batch 1",
        "2026-09-12T10:00:06Z [INFO] Pod A finished batch 1",
    ]
    stream_b = [
        "2026-09-12T10:00:02Z [INFO] Pod B starting worker",
        "2026-09-12T10:00:04Z ERROR: Pod B connection refused to redis",
        "2026-09-12T10:00:05Z [INFO] Pod B retrying",
    ]

    streams = [
        ("pod-a", "main-app", stream_a),
        ("pod-b", "worker", stream_b),
    ]

    merged = list(merge_log_streams(streams))

    assert len(merged) == 6
    # Verify strict chronological ordering by timestamp
    timestamps = [l.timestamp for l in merged]
    assert timestamps == sorted(timestamps)

    # Verify line 4 is the error in pod-b
    err_line = [l for l in merged if "connection refused" in l.raw_text][0]
    assert err_line.source_pod == "pod-b"
    assert err_line.source_container == "worker"
    assert err_line.line_number == 4


def test_candidate_window_redaction_fails_closed():
    sanitizer = EventSanitizer()

    # Candidate with leaked AWS key and Bearer token in log window
    trigger = LogLine(
        raw_text="2026-09-12T10:00:00Z ERROR: Failed authentication with AWS key AKIAIOSFODNN7EXAMPLE",
        line_number=42,
        source_pod="pod-auth",
        source_container="auth-app",
    )
    cand = CandidateWindow(
        candidate_id="cand-test-1",
        score=0.90,
        trigger_line=trigger,
        context_before=[LogLine("Bearer eyJhbGciOi.eyJzdWIi.XYZ12345678901234567890", 41)],
        context_after=[LogLine("Process terminated", 43)],
        full_window_text=(
            "Bearer eyJhbGciOi.eyJzdWIi.XYZ12345678901234567890\n"
            "2026-09-12T10:00:00Z ERROR: Failed authentication with AWS key AKIAIOSFODNN7EXAMPLE\n"
            "Process terminated"
        ),
    )

    sanitized = sanitizer.sanitize_candidate_window(cand)

    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized.trigger_line.raw_text
    assert "[REDACTED_AWS_KEY]" in sanitized.trigger_line.raw_text
    assert "[REDACTED_JWT]" in sanitized.context_before[0].raw_text or "[REDACTED_BEARER_TOKEN]" in sanitized.context_before[0].raw_text
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized.full_window_text


def test_stage_b_prompt_budget_invariance():
    """Verify that Stage B prompt size does NOT grow with log size."""
    scanner = StreamingLogScanner(max_stage_b_lines=50)
    ai_engine = AIReasoningEngine(provider="offline")
    incident = Incident(service="checkout-service")

    # Candidate extracted from a 10-line log
    trigger = LogLine("Traceback (most recent call last):", line_number=5, source_pod="pod-1")
    cand = CandidateWindow(
        candidate_id="cand-1",
        score=0.95,
        trigger_line=trigger,
        context_before=[LogLine(f"Context before {i}", i) for i in range(1, 5)],
        context_after=[LogLine(f"Context after {i}", i) for i in range(6, 12)],
        signal_type="language_exception",
    )

    prompt = ai_engine.build_triage_prompt(incident, [cand], max_context_lines=50)

    # Prompt size should be strictly bounded (under 2,000 characters)
    assert len(prompt) < 2000
    assert "Traceback (most recent call last):" in prompt
    assert "<untrusted_operational_data>" in prompt
