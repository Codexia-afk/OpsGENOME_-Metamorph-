"""Parser Registry for technology-stack error diagnostics."""

from __future__ import annotations

from typing import Any
from opsgenome.signal.parsers.base import ErrorParser, ParsedError
from opsgenome.signal.parsers.java_parser import JavaErrorParser
from opsgenome.signal.parsers.javascript_parser import JavaScriptErrorParser
from opsgenome.signal.parsers.python_parser import PythonErrorParser
from opsgenome.signal.parsers.terraform_parser import TerraformErrorParser


class ParserRegistry:
    """Registry managing stack-specific error parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, ErrorParser] = {}
        # Register standard built-in parsers
        self.register(PythonErrorParser())
        self.register(JavaErrorParser())
        self.register(JavaScriptErrorParser())
        self.register(TerraformErrorParser())

    def register(self, parser: ErrorParser) -> None:
        """Register a parser for a given language."""
        self._parsers[parser.language.lower()] = parser

    def get_parser(self, language: str) -> ErrorParser | None:
        """Lookup parser by language name (case-insensitive)."""
        return self._parsers.get((language or "").lower())

    def parse_error(
        self,
        error_output: str,
        language: str | None = None,
    ) -> ParsedError | None:
        """Parse error output using specified language parser, or auto-detect across registered parsers."""
        if not error_output or not error_output.strip():
            return None

        # 1. If language is explicitly specified and known, try that parser first
        if language:
            lang_key = language.lower()
            # Map common aliases
            if lang_key in ("py", "python3", "pytest"):
                lang_key = "python"
            elif lang_key in ("node", "js", "ts", "typescript"):
                lang_key = "javascript"
            elif lang_key in ("tf", "tofu"):
                lang_key = "terraform"

            parser = self._parsers.get(lang_key)
            if parser:
                parsed = parser.parse(error_output)
                if parsed:
                    return parsed

        # 2. Auto-detection across registered parsers
        # Priority order: python, java, javascript, terraform
        for p in self._parsers.values():
            parsed = p.parse(error_output)
            if parsed:
                return parsed

        return None


# Global singleton registry instance
_default_registry = ParserRegistry()


def parse_error(error_output: str, language: str | None = None) -> ParsedError | None:
    """Convenience function to parse error output via default registry."""
    return _default_registry.parse_error(error_output, language=language)


def get_parser(language: str) -> ErrorParser | None:
    return _default_registry.get_parser(language)
