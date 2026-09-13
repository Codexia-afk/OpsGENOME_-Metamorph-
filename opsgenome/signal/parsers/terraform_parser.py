"""Structured Terraform CLI Error Parser."""

from __future__ import annotations

import re
from typing import Any
from opsgenome.signal.parsers.base import ParsedError, StackFrame


class TerraformErrorParser:
    """Parses Terraform plan/apply diagnostics and syntax/configuration errors."""

    language = "terraform"

    # Matches Terraform error headers:
    # Error: Missing required argument
    # Error: Reference to undeclared input variable
    # Error: No value for required variable
    ERROR_HEADER_PATTERN = re.compile(
        r"^Error:\s*(.+)$",
        re.MULTILINE,
    )

    # Matches location indicator:
    # on main.tf line 14, in resource "aws_vpc" "primary":
    # or on variables.tf line 5:
    LOCATION_PATTERN = re.compile(
        r'^\s*on\s+([a-zA-Z0-9_\-\./\\]+\.tf)(?:\s+line\s+(\d+))?(?:,\s+in\s+([^\n\r:]+))?:?',
        re.MULTILINE,
    )

    def parse(self, error_output: str) -> ParsedError | None:
        if not error_output or not error_output.strip():
            return None

        # Check if output contains Terraform error indicators
        if "Error:" not in error_output and "terraform" not in error_output.lower():
            return None

        header_match = self.ERROR_HEADER_PATTERN.search(error_output)
        loc_match = self.LOCATION_PATTERN.search(error_output)

        if not header_match and not loc_match:
            return None

        exception_type = header_match.group(1).strip() if header_match else "TerraformError"

        file_name = ""
        line_no: int | None = None
        target_resource = ""

        if loc_match:
            file_name = (loc_match.group(1) or "").strip()
            line_str = loc_match.group(2)
            if line_str and line_str.isdigit():
                line_no = int(line_str)
            else:
                line_no = None
            target_resource = (loc_match.group(3) or "").strip()
        else:
            # Terraform error without explicit on <file> line <N>
            line_no = None

        # Extract human readable explanation (lines after the location block)
        lines = error_output.splitlines()
        message_lines: list[str] = []
        capture = False

        for l in lines:
            stripped = l.strip()
            if not stripped:
                continue
            if stripped.startswith("Error:"):
                capture = True
                continue
            if stripped.startswith("on ") and ".tf" in stripped:
                continue
            # Skip code snippet line e.g. "14:   cidr_block = var.vpc_cidr"
            if re.match(r'^\d+:\s+', stripped):
                continue
            if capture:
                message_lines.append(stripped)

        message = " ".join(message_lines).strip()
        if not message and header_match:
            message = header_match.group(1).strip()

        stack_frames: list[StackFrame] = []
        if file_name or line_no is not None or target_resource:
            stack_frames.append(
                {
                    "file": file_name,
                    "line": line_no,
                    "function": target_resource or "module",
                }
            )

        return {
            "language": self.language,
            "exception_type": exception_type,
            "message": message,
            "file": file_name,
            "line": line_no,
            "stack_frames": stack_frames,
        }
