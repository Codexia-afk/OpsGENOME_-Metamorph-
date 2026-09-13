"""Structured Java Error & Stack Trace Parser."""

from __future__ import annotations

import re
from typing import Any
from opsgenome.signal.parsers.base import ParsedError, StackFrame


class JavaErrorParser:
    """Parses standard Java stack traces and nested Caused by: exception chains."""

    language = "java"

    # Matches an exception declaration line:
    # Exception in thread "main" java.lang.NullPointerException: Cannot invoke ...
    # or Caused by: java.lang.NullPointerException: Configuration key is null
    # or standalone java.lang.IllegalArgumentException: Invalid argument
    THREAD_EXCEPTION_PATTERN = re.compile(
        r'(?:Exception in thread "[^"]+"\s+)?([a-zA-Z0-9_\.]+(?:Exception|Error|Throwable|Fault))\s*(?::\s*(.*))?$'
    )

    CAUSED_BY_PATTERN = re.compile(
        r'Caused by:\s+([a-zA-Z0-9_\.]+(?:Exception|Error|Throwable|Fault))\s*(?::\s*(.*))?$'
    )

    # Matches Java stack trace frame:
    # at com.example.billing.Invoice.calculate(Invoice.java:42)
    # at java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
    # at com.example.Class.method(Unknown Source)
    FRAME_PATTERN = re.compile(
        r'^\s*at\s+([a-zA-Z0-9_\.\$/<>]+)\s*\((?:([a-zA-Z0-9_\-\.]+):(\d+)|([^\)]+))\)',
        re.MULTILINE,
    )

    def parse(self, error_output: str) -> ParsedError | None:
        if not error_output or not error_output.strip():
            return None

        lines = error_output.splitlines()

        # Data structure for exception chain segments
        # Each segment represents an exception block: (exception_type, message, frames)
        segments: list[dict[str, Any]] = []
        current_segment: dict[str, Any] | None = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check for "Caused by:" header
            caused_match = self.CAUSED_BY_PATTERN.search(line_str)
            if caused_match:
                if current_segment:
                    segments.append(current_segment)
                current_segment = {
                    "is_caused_by": True,
                    "exception_type": caused_match.group(1).strip(),
                    "message": (caused_match.group(2) or "").strip(),
                    "frames": [],
                }
                continue

            # Check for primary exception line (e.g. Exception in thread "main" ... or ClassNameException: ...)
            thread_match = self.THREAD_EXCEPTION_PATTERN.search(line_str)
            if thread_match and "at " not in line_str and not line_str.startswith("..."):
                if current_segment is None:
                    current_segment = {
                        "is_caused_by": False,
                        "exception_type": thread_match.group(1).strip(),
                        "message": (thread_match.group(2) or "").strip(),
                        "frames": [],
                    }
                    continue

            # Check for stack trace frame: at com.example...
            frame_match = self.FRAME_PATTERN.match(line)
            if frame_match and current_segment is not None:
                fn_name = frame_match.group(1).strip()
                file_name = frame_match.group(2)
                line_str = frame_match.group(3)
                special_location = frame_match.group(4)

                if file_name and line_str:
                    try:
                        line_no = int(line_str)
                    except ValueError:
                        line_no = None
                    file_val = file_name.strip()
                else:
                    file_val = (special_location or "Unknown Source").strip()
                    line_no = None

                current_segment["frames"].append(
                    {
                        "file": file_val,
                        "line": line_no,
                        "function": fn_name,
                    }
                )

        if current_segment:
            segments.append(current_segment)

        if not segments:
            # Fallback: check if any FRAME_PATTERN exists globally
            raw_frames = self.FRAME_PATTERN.findall(error_output)
            if not raw_frames:
                return None
            frames_list: list[StackFrame] = []
            for fn_name, f_name, l_num, special in raw_frames:
                line_val = int(l_num) if l_num and l_num.isdigit() else None
                file_val = f_name if f_name else (special or "Unknown Source")
                frames_list.append({"file": file_val.strip(), "line": line_val, "function": fn_name.strip()})
            first_frame = frames_list[0] if frames_list else {"file": "", "line": None, "function": ""}
            return {
                "language": self.language,
                "exception_type": "JavaException",
                "message": "",
                "file": first_frame["file"],
                "line": first_frame["line"],
                "stack_frames": frames_list,
            }

        # Java exceptions frequently wrap an original fault.
        # The ROOT cause (the deepest "Caused by:" block) represents the actual fault.
        # If there are Caused by: blocks, the LAST segment is the root cause!
        root_segment = segments[-1]
        outer_segment = segments[0]

        primary_type = root_segment["exception_type"]
        primary_message = root_segment["message"]

        # Find closest/fault frame from the root segment
        primary_file = ""
        primary_line: int | None = None

        if root_segment["frames"]:
            # In Java, the FIRST frame under an exception is the exact fault point (deepest in call stack)
            first_f = root_segment["frames"][0]
            primary_file = first_f["file"]
            primary_line = first_f["line"]
        elif outer_segment["frames"]:
            first_f = outer_segment["frames"][0]
            primary_file = first_f["file"]
            primary_line = first_f["line"]

        # Assemble all stack frames: deepest / most-relevant first
        # Root cause frames first, followed by outer wrapper frames
        ordered_frames: list[StackFrame] = []
        for seg in reversed(segments):
            for f in seg["frames"]:
                ordered_frames.append(f)

        return {
            "language": self.language,
            "exception_type": primary_type,
            "message": primary_message,
            "file": primary_file,
            "line": primary_line,
            "stack_frames": ordered_frames,
        }
