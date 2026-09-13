"""Stage A Streaming Deterministic Log Scanner & Triage Engine.

Processes tens to hundreds of thousands (and up to 1M+) of Kubernetes, CI/CD,
and application log lines in constant O(1) memory, extracting a bounded set of
high-signal candidate error windows without materializing the full log.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import heapq
import re
from typing import Any, Iterable, Iterator
import uuid

from opsgenome.signal.parsers.base import ParsedError
from opsgenome.signal.parsers.registry import parse_error


@dataclass
class LogLine:
    """Represents a single parsed log line with optional source provenance and timestamp."""
    raw_text: str
    line_number: int
    source_pod: str | None = None
    source_container: str | None = None
    timestamp: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            self.message = self.raw_text


@dataclass
class CandidateWindow:
    """A bounded context window around a high-signal candidate error line."""
    candidate_id: str
    score: float
    trigger_line: LogLine
    context_before: list[LogLine] = field(default_factory=list)
    context_after: list[LogLine] = field(default_factory=list)
    parsed_error: ParsedError | None = None
    full_window_text: str = ""
    signal_type: str = "generic_error"

    @property
    def line_count(self) -> int:
        return len(self.context_before) + 1 + len(self.context_after)


@dataclass
class StreamingScanResult:
    """Result of Stage A streaming scan."""
    candidates: list[CandidateWindow]
    total_lines_scanned: int
    high_confidence_signal_found: bool
    top_candidate: CandidateWindow | None
    wall_time_seconds: float
    peak_memory_bytes: int
    summary_message: str


# Regex for parsing Kubernetes logs with --prefix and/or --timestamps:
# e.g.: [pod/my-pod-abc/my-container] 2026-09-12T12:00:00.123456Z message
# e.g.: pod/my-pod-abc/my-container: 2026-09-12T12:00:00.123456Z message
# e.g.: 2026-09-12T12:00:00.123456Z message
K8S_PREFIX_PATTERN = re.compile(
    r"^(?:\[?(?:pod/)?([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\]?:?\s+)?"
    r"(?:(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+)?"
    r"(.*)$"
)

# ISO / RFC3339 Timestamp pattern
TIMESTAMP_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)


class StreamingLogScanner:
    """Streaming, constant-memory log scanner for Kubernetes, CI/CD, and application logs."""

    # Kubernetes critical failure states (Weight: 0.90 - 1.00)
    K8S_CRITICAL_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
        ("CrashLoopBackOff", re.compile(r"\bCrashLoopBackOff\b", re.IGNORECASE), 0.98),
        ("OOMKilled", re.compile(r"\bOOMKilled\b", re.IGNORECASE), 0.99),
        ("ImagePullBackOff", re.compile(r"\b(ImagePullBackOff|ErrImagePull)\b", re.IGNORECASE), 0.95),
        ("LivenessProbeFailed", re.compile(r"\bLiveness probe failed\b", re.IGNORECASE), 0.92),
        ("ReadinessProbeFailed", re.compile(r"\bReadiness probe failed\b", re.IGNORECASE), 0.88),
        ("BackoffRestart", re.compile(r"\bBack-off(?:\s+[0-9a-zA-Z_.-]+)?\s+restarting failed container\b", re.IGNORECASE), 0.94),
        ("ConnectionRefused", re.compile(r"\b(connection refused|dial tcp.*refused)\b", re.IGNORECASE), 0.90),
        ("ContextDeadlineExceeded", re.compile(r"\bcontext deadline exceeded\b", re.IGNORECASE), 0.89),
        ("PanicFatal", re.compile(r"\b(PANIC|FATAL|CRITICAL)(?::|\b)", re.IGNORECASE), 0.95),
        ("HTTP5xx", re.compile(r"\b(?:HTTP/\d\.\d[\"'\s]+|status(?:code)?[\s=:]+|code[\s=:]+|\"\s+)(500|502|503|504)\b|\b(?:500|502|503|504)\s+(?:Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)\b|\bInternal Server Error\b|\bBad Gateway\b", re.IGNORECASE), 0.85),
    ]

    # Traceback / Exception header indicators to trigger parser registry
    TRACEBACK_HEADER_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"(?:^|\s+)Traceback \(most recent call last\):"),
        re.compile(r"(?:^|\s+)[A-Z][a-zA-Z0-9_.]*(?:Error|Exception|Fault):\s+"),
        re.compile(r"(?:^|\s+)Exception in thread \"[^\"]+\" [a-zA-Z0-9_.$]+Exception:"),
        re.compile(r"(?:^|\s+)[a-zA-Z0-9_.$]+Exception:\s+"),
        re.compile(r"(?:^|\s+)Caused by:\s+[a-zA-Z0-9_.$]+(?:Exception|Error):"),
        re.compile(r"^\s*at [a-zA-Z0-9_.$]+\([a-zA-Z0-9_.]+\.java:\d+\)"),
        re.compile(r"(?:^|\s+)[A-Z][a-zA-Z0-9_.]*Error:\s+"),
        re.compile(r"^\s*at (?:async )?[a-zA-Z0-9_.$<> ]+\(.*:\d+:\d+\)"),
        re.compile(r"(?:^|\s+)Error:\s+(?:No value for required variable|Invalid |Missing )"),
    ]

    # Explicit noise suppressors (Score <= 0.10)
    NOISE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bGET /(?:healthz|ready|live|metrics|health)\b.*?(?:200|204)", re.IGNORECASE),
        re.compile(r"\bkube-probe/", re.IGNORECASE),
        re.compile(r"\b(?:heartbeat ok|worker ping|alive|healthy)\b", re.IGNORECASE),
        re.compile(r"\b(?:retry succeeded|retrying in.*succeeded|backoff.*succeeded)\b", re.IGNORECASE),
        re.compile(r"\"(?:GET|HEAD) /(?:healthz|readyz|metrics)\" 200", re.IGNORECASE),
        re.compile(r"\[INFO\].*?(?:pool refresh|heartbeat|sync completed|scheduled task)", re.IGNORECASE),
    ]

    # Fast substring triggers to avoid executing regexes on routine info lines
    FAST_KEYWORDS: tuple[str, ...] = (
        "error", "exception", "fatal", "panic", "critical", "failed", "refused", "crashloop",
        "oom", "backoff", "back-off", "traceback", "caused by", "500", "502",
        "503", "504", "deadline", "timed out", "timeout"
    )

    def __init__(
        self,
        min_signal_threshold: float = 0.60,
        max_candidates: int = 5,
        context_before_lines: int = 5,
        context_after_lines: int = 15,
        max_stage_b_lines: int = 50,
    ) -> None:
        self.min_signal_threshold = min_signal_threshold
        self.max_candidates = max_candidates
        self.context_before_lines = context_before_lines
        self.context_after_lines = context_after_lines
        self.max_stage_b_lines = max_stage_b_lines

    def parse_log_line(
        self,
        raw_text: str,
        line_number: int,
        default_pod: str | None = None,
        default_container: str | None = None,
    ) -> LogLine:
        """Parses prefix tags and timestamps from a raw log line, or applies defaults."""
        match = K8S_PREFIX_PATTERN.match(raw_text)
        if match:
            pod = match.group(1) or default_pod
            container = match.group(2) or default_container
            ts = match.group(3)
            msg = match.group(4) if match.group(4) is not None else raw_text
            return LogLine(
                raw_text=raw_text,
                line_number=line_number,
                source_pod=pod,
                source_container=container,
                timestamp=ts,
                message=msg,
            )
        return LogLine(
            raw_text=raw_text,
            line_number=line_number,
            source_pod=default_pod,
            source_container=default_container,
            timestamp=None,
            message=raw_text,
        )

    def score_line(self, line_text: str) -> tuple[float, str]:
        """Scores a single log line between 0.0 (pure noise) and 1.0 (critical root cause)."""
        line_lower = line_text.lower()

        # 1. Explicit Noise Check (Immediate suppression)
        for noise_pat in self.NOISE_PATTERNS:
            if noise_pat.search(line_text):
                return 0.05, "routine_noise"

        # 2. Fast Path Substring Check
        has_keyword = any(kw in line_lower for kw in self.FAST_KEYWORDS)
        if not has_keyword:
            # Routine informational log
            return 0.10, "routine_info"

        # 3. Traceback / Exception Structure Check (Highest Priority)
        for tb_pat in self.TRACEBACK_HEADER_PATTERNS:
            if tb_pat.search(line_text):
                return 0.98, "language_exception"

        # 4. Kubernetes Critical Patterns Check
        for sig_name, k8s_pat, weight in self.K8S_CRITICAL_PATTERNS:
            if k8s_pat.search(line_text):
                return weight, sig_name

        # 5. General Error / Warning Level Markers
        if "error" in line_lower or "err" in line_lower:
            return 0.70, "generic_error"
        if "warn" in line_lower:
            return 0.35, "warning"

        return 0.20, "unclassified"

    def scan_stream(
        self,
        stream: Iterable[str | LogLine],
        source_pod: str | None = None,
        source_container: str | None = None,
    ) -> StreamingScanResult:
        """Streaming Stage A pass over an unbounded iterable of lines in O(1) memory."""
        import time
        import tracemalloc

        tracemalloc.start()
        start_time = time.perf_counter()

        # Rolling ring buffer of preceding lines
        before_buffer: deque[LogLine] = deque(maxlen=self.context_before_lines)

        # Active windows collecting context_after
        # List of [CandidateWindow, lines_needed: int]
        active_windows: list[list[Any]] = []

        # Completed candidate heap: min-heap of (score, tiebreaker_idx, CandidateWindow)
        # Size capped to self.max_candidates
        top_heap: list[tuple[float, int, CandidateWindow]] = []
        tiebreaker_counter = 0

        total_lines = 0

        def finalize_window(cand: CandidateWindow) -> None:
            nonlocal tiebreaker_counter
            # Build full window text (raw with timestamps and pod tags)
            window_lines = [l.raw_text for l in cand.context_before] + [cand.trigger_line.raw_text] + [l.raw_text for l in cand.context_after]
            cand.full_window_text = "\n".join(window_lines)

            # Build clean window text (messages stripped of pod/timestamp prefixes for parser registry)
            clean_lines = [
                (l.message if getattr(l, "message", None) else l.raw_text)
                for l in cand.context_before
            ] + [
                (cand.trigger_line.message if getattr(cand.trigger_line, "message", None) else cand.trigger_line.raw_text)
            ] + [
                (l.message if getattr(l, "message", None) else l.raw_text)
                for l in cand.context_after
            ]
            clean_text = "\n".join(clean_lines)

            # Try parsing structured error via parser registry (clean text first, fallback to raw)
            try:
                cand.parsed_error = parse_error(clean_text) or parse_error(cand.full_window_text)
                if cand.parsed_error:
                    # Enrich with pod provenance
                    cand.parsed_error["source_pod"] = cand.trigger_line.source_pod
                    cand.parsed_error["source_container"] = cand.trigger_line.source_container
                    cand.parsed_error["line_offset"] = cand.trigger_line.line_number
                    cand.parsed_error["timestamp"] = cand.trigger_line.timestamp
                    # Boost score if a valid stack trace was parsed
                    cand.score = max(cand.score, 0.95)
            except Exception:
                cand.parsed_error = None

            # Push to bounded min-heap
            heap_entry = (cand.score, tiebreaker_counter, cand)
            tiebreaker_counter += 1

            if len(top_heap) < self.max_candidates:
                heapq.heappush(top_heap, heap_entry)
            else:
                # If this candidate has a strictly higher score than the lowest in top_heap
                if cand.score > top_heap[0][0]:
                    heapq.heapreplace(top_heap, heap_entry)

        # Stream line by line (O(1) memory)
        for raw_item in stream:
            total_lines += 1

            if isinstance(raw_item, LogLine):
                log_line = raw_item
            else:
                log_line = self.parse_log_line(
                    raw_item.rstrip("\r\n"),
                    line_number=total_lines,
                    default_pod=source_pod,
                    default_container=source_container,
                )

            # 1. Feed context_after to currently active candidate windows
            still_active: list[list[Any]] = []
            for active_item in active_windows:
                cand, needed = active_item[0], active_item[1]
                cand.context_after.append(log_line)
                needed -= 1
                if needed <= 0:
                    finalize_window(cand)
                else:
                    active_item[1] = needed
                    still_active.append(active_item)
            active_windows = still_active

            # 2. Score the current line
            score, signal_type = self.score_line(log_line.message or log_line.raw_text)

            # 3. If line passes minimum signal threshold, initiate new CandidateWindow
            if score >= self.min_signal_threshold:
                # Suppress duplicate overlapping window for the same pod/stream
                is_overlapping = any(
                    aw[0].trigger_line.source_pod == log_line.source_pod
                    for aw in active_windows
                )
                if not is_overlapping:
                    cand = CandidateWindow(
                        candidate_id=f"cand-{uuid.uuid4().hex[:8]}",
                        score=score,
                        trigger_line=log_line,
                        context_before=list(before_buffer),
                        context_after=[],
                        signal_type=signal_type,
                    )
                    if self.context_after_lines > 0:
                        active_windows.append([cand, self.context_after_lines])
                    else:
                        finalize_window(cand)

            # 4. Update rolling ring buffer
            before_buffer.append(log_line)

        # Finalize any remaining active windows at EOF
        for active_item in active_windows:
            finalize_window(active_item[0])
        active_windows.clear()

        # Extract sorted candidates (highest score first)
        candidates = [entry[2] for entry in sorted(top_heap, key=lambda x: (x[0], -x[1]), reverse=True)]

        # Filter candidates: must strictly meet threshold
        valid_candidates = [c for c in candidates if c.score >= self.min_signal_threshold]

        # Enforce Stage B line cap budget (<= max_stage_b_lines)
        capped_candidates = self._enforce_line_budget(valid_candidates, self.max_stage_b_lines)

        wall_time = time.perf_counter() - start_time
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        has_high_confidence = len(capped_candidates) > 0 and capped_candidates[0].score >= self.min_signal_threshold
        top_cand = capped_candidates[0] if has_high_confidence else None

        if has_high_confidence and top_cand:
            pod_info = f" in pod '{top_cand.trigger_line.source_pod}'" if top_cand.trigger_line.source_pod else ""
            line_info = f" at line {top_cand.trigger_line.line_number}"
            if top_cand.parsed_error:
                summary = (
                    f"Identified {top_cand.parsed_error.get('exception_type', 'Error')}{pod_info}{line_info} "
                    f"({top_cand.parsed_error.get('file', 'unknown')}:{top_cand.parsed_error.get('line', '?')})"
                )
            else:
                summary = f"Identified {top_cand.signal_type}{pod_info}{line_info}: {top_cand.trigger_line.raw_text.strip()[:100]}"
        else:
            summary = f"No clear root cause found in {total_lines:,} log lines (all signals below confidence threshold {self.min_signal_threshold})"

        return StreamingScanResult(
            candidates=capped_candidates,
            total_lines_scanned=total_lines,
            high_confidence_signal_found=has_high_confidence,
            top_candidate=top_cand,
            wall_time_seconds=wall_time,
            peak_memory_bytes=peak_memory,
            summary_message=summary,
        )

    def _enforce_line_budget(self, candidates: list[CandidateWindow], max_total_lines: int) -> list[CandidateWindow]:
        """Ensures that the total context lines across all candidates sent to Stage B does not exceed max_total_lines."""
        if not candidates:
            return []

        budget_remaining = max_total_lines
        capped: list[CandidateWindow] = []

        for cand in candidates:
            cand_lines = cand.line_count
            if cand_lines <= budget_remaining:
                capped.append(cand)
                budget_remaining -= cand_lines
            else:
                # If we still have at least 5 lines of budget, trim this candidate's context
                if budget_remaining >= 3:
                    # Keep trigger line, trim context_after first, then context_before
                    avail_after = max(0, min(len(cand.context_after), budget_remaining - 1 - min(2, len(cand.context_before))))
                    avail_before = max(0, min(len(cand.context_before), budget_remaining - 1 - avail_after))
                    cand.context_before = cand.context_before[-avail_before:] if avail_before > 0 else []
                    cand.context_after = cand.context_after[:avail_after]
                    cand.full_window_text = "\n".join(
                        [l.raw_text for l in cand.context_before] + [cand.trigger_line.raw_text] + [l.raw_text for l in cand.context_after]
                    )
                    capped.append(cand)
                break

        return capped


def extract_timestamp_sort_key(line: str | LogLine) -> str:
    """Extracts timestamp key for chronological stream merging."""
    if isinstance(line, LogLine) and line.timestamp:
        return line.timestamp
    raw = line.raw_text if isinstance(line, LogLine) else str(line)
    match = TIMESTAMP_PATTERN.search(raw)
    if match:
        return match.group(1)
    # If no timestamp, return empty string so it stably maintains stream order
    return "9999-99-99T99:99:99"


def merge_log_streams(
    streams: list[tuple[str, str, Iterable[str]]],
) -> Iterator[LogLine]:
    """Merges multiple log sources chronologically using heapq.merge in O(num_streams) memory.

    Each tuple in `streams` is: (pod_name, container_name, line_iterable).
    Yields LogLine instances tagged with source provenance and line number.
    """
    scanner = StreamingLogScanner()

    def stream_generator(pod: str, container: str, lines: Iterable[str]) -> Iterator[tuple[str, LogLine]]:
        line_idx = 0
        for raw in lines:
            line_idx += 1
            log_line = scanner.parse_log_line(raw.rstrip("\r\n"), line_number=line_idx, default_pod=pod, default_container=container)
            ts_key = log_line.timestamp or extract_timestamp_sort_key(log_line)
            yield (ts_key, log_line)

    tagged_generators = [
        stream_generator(pod, container, stream)
        for pod, container, stream in streams
    ]

    # heapq.merge lazily pulls from each generator in O(num_streams) memory
    merged_iter = heapq.merge(*tagged_generators, key=lambda item: item[0])

    global_line_counter = 0
    for _, log_line in merged_iter:
        global_line_counter += 1
        log_line.line_number = global_line_counter
        yield log_line
