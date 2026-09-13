"""Structured Node.js / JavaScript Error & Stack Trace Parser."""

from __future__ import annotations

import re
from typing import Any
from opsgenome.signal.parsers.base import ParsedError, StackFrame


class JavaScriptErrorParser:
    """Parses Node.js / V8 engine stack traces and unhandled exceptions."""

    language = "javascript"

    # Matches V8 exception line: TypeError: Cannot read properties of undefined (reading 'x')
    EXCEPTION_PATTERN = re.compile(
        r"^([a-zA-Z_$][a-zA-Z0-9_$]*(?:Error|Exception)|Error):\s*(.*)$",
        re.MULTILINE,
    )

    # Matches V8 stack frame:
    # at functionName (/path/to/file.js:35:15)
    # or at async functionName (/path/to/file.js:35:15)
    # or at /path/to/file.js:35:15
    FRAME_PATTERN = re.compile(
        r'^\s*at\s+(?:(?:async\s+)?([^\(\s]+)\s+\(([^:\(\)]+):(\d+):(\d+)\)|([^:\(\)\s]+):(\d+):(\d+))',
        re.MULTILINE,
    )

    def parse(self, error_output: str) -> ParsedError | None:
        if not error_output or not error_output.strip():
            return None

        # 1. Extract frames
        raw_frames = self.FRAME_PATTERN.finditer(error_output)
        stack_frames: list[StackFrame] = []

        for m in raw_frames:
            fn_name = m.group(1)
            file_1 = m.group(2)
            line_1 = m.group(3)

            file_2 = m.group(5)
            line_2 = m.group(6)

            file_val = file_1 if file_1 else (file_2 or "")
            line_str = line_1 if line_1 else (line_2 or "")
            func_val = fn_name.strip() if fn_name else "<anonymous>"

            line_no: int | None = None
            if line_str and line_str.isdigit():
                line_no = int(line_str)

            stack_frames.append(
                {
                    "file": file_val.strip(),
                    "line": line_no,
                    "function": func_val,
                }
            )

        # 2. Extract exception type and message
        exc_match = self.EXCEPTION_PATTERN.search(error_output)
        if not exc_match and not stack_frames:
            return None

        exception_type = "JavaScriptError"
        message = ""

        if exc_match:
            exception_type = exc_match.group(1).strip()
            message = (exc_match.group(2) or "").strip()
        else:
            # Fallback
            lines = [l.strip() for l in error_output.splitlines() if l.strip()]
            if lines:
                exception_type = "Error"
                message = lines[0]

        # In Node.js/V8, the FIRST stack frame is the point where the error was thrown (deepest in call stack)
        primary_file = ""
        primary_line: int | None = None

        if stack_frames:
            primary_file = stack_frames[0]["file"]
            primary_line = stack_frames[0]["line"]

        return {
            "language": self.language,
            "exception_type": exception_type,
            "message": message,
            "file": primary_file,
            "line": primary_line,
            "stack_frames": stack_frames,
        }
