"""Base types and schema for structured error parsers across technology stacks."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class StackFrame(TypedDict):
    file: str
    line: int | None
    function: str


class ParsedError(TypedDict, total=False):
    language: str
    exception_type: str
    message: str
    file: str
    line: int | None
    stack_frames: list[StackFrame]
    source_pod: str | None
    source_container: str | None
    line_offset: int | None
    timestamp: str | None


class ErrorParser(Protocol):
    """Protocol that all stack-specific error parsers must implement."""

    language: str

    def parse(self, error_output: str) -> ParsedError | None:
        """Parse error output into normalized ParsedError structure.

        Returns None if output does not contain a recognizable error for this language.
        """
        ...
