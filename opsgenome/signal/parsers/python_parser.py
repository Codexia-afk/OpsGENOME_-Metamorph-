"""Structured Python Error & Traceback Parser."""

from __future__ import annotations

import re
from typing import Any
from opsgenome.signal.parsers.base import ParsedError, StackFrame


class PythonErrorParser:
    """Parses standard Python tracebacks and unhandled exceptions into structured errors."""

    language = "python"

    # Matches standard traceback frame: File "/path/to/file.py", line 42, in function_name
    FRAME_PATTERN = re.compile(
        r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([^\n\r]+))?',
        re.MULTILINE,
    )

    # Matches standard Python exception line: KeyError: 'missing_key' or ZeroDivisionError: division by zero
    # or standalone SystemExit or RecursionError
    EXCEPTION_PATTERN = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_\.]*(?:Error|Exception|Exit|Interrupt|Warning|Fault|Break|StopIteration)|[A-Z][a-zA-Z0-9_]*Error|[A-Z][a-zA-Z0-9_]*Exception)"
        r"(?::\s*(.*))?$",
        re.MULTILINE,
    )

    def parse(self, error_output: str) -> ParsedError | None:
        if not error_output or not error_output.strip():
            return None

        # 1. Extract all stack frames
        raw_frames = self.FRAME_PATTERN.findall(error_output)
        stack_frames: list[StackFrame] = []
        for file_path, line_str, fn_name in raw_frames:
            try:
                line_no = int(line_str)
            except ValueError:
                line_no = None
            stack_frames.append(
                {
                    "file": file_path.strip(),
                    "line": line_no,
                    "function": (fn_name or "<module>").strip(),
                }
            )

        # 2. Extract exception type and message
        # In Python tracebacks, the exception is usually printed at the end
        matches = list(self.EXCEPTION_PATTERN.finditer(error_output))
        if not matches and not stack_frames:
            return None

        # Guard: If no Python stack frames were found, but Java stack trace markers exist,
        # do not misclassify Java exceptions as Python errors.
        if not stack_frames and ("\tat " in error_output or "  at " in error_output or "Caused by:" in error_output):
            return None

        exception_type = "PythonError"
        message = ""

        if matches:
            last_match = matches[-1]
            exception_type = last_match.group(1).strip()
            message = (last_match.group(2) or "").strip()
        elif stack_frames:
            # Fallback if no explicit Exception class line matched: find last non-empty line
            lines = [line.strip() for line in error_output.strip().splitlines() if line.strip()]
            if lines:
                last_line = lines[-1]
                if ":" in last_line:
                    parts = last_line.split(":", 1)
                    exception_type = parts[0].strip()
                    message = parts[1].strip()
                else:
                    message = last_line

        # 3. Determine primary file and line
        # The last frame in the traceback is the deepest/closest frame to the actual fault
        primary_file = ""
        primary_line: int | None = None

        if stack_frames:
            # Primary is the deepest frame (the last one recorded in chronological execution)
            primary_file = stack_frames[-1]["file"]
            primary_line = stack_frames[-1]["line"]
            # Ordered deepest/most-relevant first
            ordered_frames = list(reversed(stack_frames))
        else:
            ordered_frames = []

        return {
            "language": self.language,
            "exception_type": exception_type,
            "message": message,
            "file": primary_file,
            "line": primary_line,
            "stack_frames": ordered_frames,
        }
