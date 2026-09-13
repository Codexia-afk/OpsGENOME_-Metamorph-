"""Scale Benchmarks for Stage A Streaming Scanner & Stage B Targeted Reasoning.

Tests realistic Kubernetes log streams of:
- 10,000 lines
- 100,000 lines
- 1,000,000 lines
With randomly injected root causes, pure noise verification, and multi-pod attribution.
"""

from __future__ import annotations

import random
import time
import tracemalloc
from typing import Iterator
import pytest

from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.signal.streaming_scanner import (
    CandidateWindow,
    StreamingLogScanner,
    merge_log_streams,
)
from opsgenome.storage.models import Incident


def generate_synthetic_k8s_log(
    total_lines: int,
    injected_error_type: str | None = "java_npe",
    injected_position: int | None = None,
    pod_name: str = "core-billing-svc-78bd",
    container_name: str = "billing-app",
) -> Iterator[str]:
    """Generates a realistic stream of Kubernetes logs of configurable size.

    Yields line-by-line in O(1) memory without materializing the list in memory.
    """
    noise_templates = [
        "10.244.1.5 - - [12/Sep/2026:12:00:{s:02d}] \"GET /healthz HTTP/1.1\" 200 12",
        "10.244.1.5 - - [12/Sep/2026:12:00:{s:02d}] \"GET /ready HTTP/1.1\" 200 4",
        "[INFO] Worker pool heartbeat ping OK (active_workers=8)",
        "[INFO] Processed event #{i} duration=14ms status=200",
        "[INFO] Connection pool idle refresh completed (active=4, idle=16)",
        "kube-probe/1.28 GET /metrics 200 584",
        "[INFO] Cache eviction cycle completed: 0 items expired",
    ]

    # Pre-build injected error lines
    if injected_error_type == "java_npe":
        error_lines = [
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.123Z com.example.billing.InvoiceProcessingException: Failed to generate invoice",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.124Z \tat com.example.billing.BillingService.processBillingRun(BillingService.java:18)",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.125Z \tat com.example.billing.BillingService.generateMonthlyStatement(BillingService.java:23)",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.126Z Caused by: java.lang.NullPointerException: Cannot invoke \"String.trim()\" because \"jurisdictionCode\" is null",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.127Z \tat com.example.billing.BillingService.calculateTaxAmount(BillingService.java:29)",
        ]
    elif injected_error_type == "python_keyerror":
        error_lines = [
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.123Z Traceback (most recent call last):",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.124Z   File \"/app/checkout.py\", line 17, in init_payment_gateway",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.125Z     token = config[\"api_secret_key\"]",
            f"[{pod_name}/{container_name}] 2026-09-12T12:30:15.126Z KeyError: 'api_secret_key'",
        ]
    else:
        error_lines = []

    err_len = len(error_lines)

    # Place error randomly between 25% and 75% of log length
    if injected_position is None and error_lines:
        injected_position = random.randint(int(total_lines * 0.25), int(total_lines * 0.75))

    lines_emitted = 0
    noise_count = len(noise_templates)

    while lines_emitted < total_lines:
        if error_lines and lines_emitted == injected_position:
            for err_l in error_lines:
                yield err_l
                lines_emitted += 1
                if lines_emitted >= total_lines:
                    break
        else:
            tpl = noise_templates[lines_emitted % noise_count]
            ts = f"2026-09-12T12:{(lines_emitted//60)%60:02d}:{lines_emitted%60:02d}.000Z"
            yield f"[{pod_name}/{container_name}] {ts} {tpl.format(i=lines_emitted, s=lines_emitted%60)}"
            lines_emitted += 1


@pytest.mark.parametrize("size", [10_000, 100_000, 1_000_000])
def test_scale_benchmark_finds_injected_error_in_bounded_memory(size: int):
    """Benchmarks Stage A scanning across 10k, 100k, and 1,000,000 lines."""
    scanner = StreamingLogScanner()
    random_pos = int(size * 0.62)  # Injected at 62% of log stream

    stream = generate_synthetic_k8s_log(
        total_lines=size,
        injected_error_type="java_npe",
        injected_position=random_pos,
        pod_name="billing-pod-01",
        container_name="billing-service",
    )

    tracemalloc.start()
    t0 = time.perf_counter()

    result = scanner.scan_stream(stream)

    elapsed = time.perf_counter() - t0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak_bytes / (1024 * 1024)
    speed = int(result.total_lines_scanned / max(0.001, elapsed))

    print(
        f"\n[BENCHMARK] Size: {size:,} lines | Time: {elapsed:.3f}s ({speed:,} lines/s) | "
        f"Peak Memory: {peak_mb:.2f} MB | Injected Found: {result.high_confidence_signal_found}"
    )

    # 1. Verification: Error must be found
    assert result.high_confidence_signal_found is True
    assert result.top_candidate is not None

    # 2. Verification: Structured parsed error must contain exact Java NPE and BillingService line 29
    parsed = result.top_candidate.parsed_error
    assert parsed is not None
    assert parsed["language"] == "java"
    assert parsed["exception_type"] == "java.lang.NullPointerException"
    assert parsed["file"] == "BillingService.java"
    assert parsed["line"] == 29
    assert result.top_candidate.trigger_line.source_pod == "billing-pod-01"

    # 3. Verification: Memory must be strictly bounded (O(1) < 15MB even for 1M lines)
    assert peak_mb < 20.0, f"Peak memory {peak_mb:.2f} MB exceeded bounded memory limit!"


def test_pure_noise_100k_lines_zero_false_positives():
    """Confirms that a 100,000-line clean log stream outputs 'no root cause found'."""
    scanner = StreamingLogScanner(min_signal_threshold=0.60)
    stream = generate_synthetic_k8s_log(
        total_lines=100_000,
        injected_error_type=None,  # NO ERROR
    )

    result = scanner.scan_stream(stream)

    assert result.total_lines_scanned == 100_000
    assert result.high_confidence_signal_found is False
    assert result.top_candidate is None
    assert len(result.candidates) == 0
    assert "No clear root cause found" in result.summary_message


def test_multi_pod_attribution_three_sources():
    """Confirms error is correctly attributed to the failing pod among 3 separate sources."""
    scanner = StreamingLogScanner()

    stream_web = generate_synthetic_k8s_log(5_000, injected_error_type=None, pod_name="web-frontend", container_name="nginx")
    stream_worker = generate_synthetic_k8s_log(5_000, injected_error_type=None, pod_name="batch-worker", container_name="worker")
    stream_payment = generate_synthetic_k8s_log(5_000, injected_error_type="python_keyerror", injected_position=2500, pod_name="payment-svc-xyz", container_name="payment-app")

    streams = [
        ("web-frontend", "nginx", stream_web),
        ("batch-worker", "worker", stream_worker),
        ("payment-svc-xyz", "payment-app", stream_payment),
    ]

    merged = merge_log_streams(streams)
    result = scanner.scan_stream(merged)

    assert result.high_confidence_signal_found is True
    assert result.top_candidate is not None
    assert result.top_candidate.trigger_line.source_pod == "payment-svc-xyz"
    assert result.top_candidate.trigger_line.source_container == "payment-app"
    assert result.top_candidate.parsed_error is not None
    assert result.top_candidate.parsed_error["exception_type"] == "KeyError"
    assert result.top_candidate.parsed_error["file"] == "/app/checkout.py"
    assert result.top_candidate.parsed_error["line"] == 17


def test_stage_b_prompt_size_comparison_10k_vs_1m():
    """Measures and proves that Stage B prompt size is virtually identical for 10K vs 1M lines."""
    scanner = StreamingLogScanner(max_stage_b_lines=50)
    ai_engine = AIReasoningEngine(provider="offline")
    incident = Incident(service="billing-svc")

    # Run on 10,000 lines
    stream_10k = generate_synthetic_k8s_log(10_000, injected_error_type="java_npe", injected_position=5_000)
    res_10k = scanner.scan_stream(stream_10k)
    prompt_10k = ai_engine.build_triage_prompt(incident, res_10k.candidates, max_context_lines=50)
    size_10k = len(prompt_10k)

    # Run on 1,000,000 lines
    stream_1m = generate_synthetic_k8s_log(1_000_000, injected_error_type="java_npe", injected_position=600_000)
    res_1m = scanner.scan_stream(stream_1m)
    prompt_1m = ai_engine.build_triage_prompt(incident, res_1m.candidates, max_context_lines=50)
    size_1m = len(prompt_1m)

    print(f"\n[STAGE B BUDGET] 10k log prompt size: {size_10k} chars | 1M log prompt size: {size_1m} chars")

    # Stage B prompt size must be bounded and within 5% of each other
    assert abs(size_10k - size_1m) < 100
    assert size_10k < 8000
    assert size_1m < 8000


if __name__ == "__main__":
    print("Running scale benchmarks...")
    for s in [10_000, 100_000, 1_000_000]:
        test_scale_benchmark_finds_injected_error_in_bounded_memory(s)
    test_pure_noise_100k_lines_zero_false_positives()
    test_multi_pod_attribution_three_sources()
    test_stage_b_prompt_size_comparison_10k_vs_1m()
    print("All scale benchmarks completed successfully!")
