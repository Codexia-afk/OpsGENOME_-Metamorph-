"""Secret Redaction Engine for OpsGenome.

CRITICAL SECURITY LAYER: Runs in-memory BEFORE any captured command,
stdout, or stderr touches disk or is sent anywhere.

Protects against:
- False Negatives: Catches AWS keys, JWTs, DB passwords, Bearer tokens,
  CLI --password flags, and high-entropy API tokens.
- False Positives: Accurately preserves safe debugging identifiers including:
  Git commit hashes, UUIDs, Kubernetes pod names, base64 non-secret config blobs,
  and container image digests.
"""

from __future__ import annotations

import base64
import math
import re
from typing import Any


class SecretRedactor:
    """In-memory secret redactor applied before any data touches persistent storage."""

    # Regex patterns for sensitive credentials
    PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
        # AWS Access Key ID
        ("AWS_ACCESS_KEY", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
        # AWS Secret Access Key
        (
            "AWS_SECRET_KEY",
            re.compile(r"(?i)(aws_secret_access_key|aws_session_token)[\s=:]+['\"]?([A-Za-z0-9/+=]{30,60})['\"]?"),
            r"\1=[REDACTED_AWS_SECRET]",
        ),
        # JSON Web Tokens (JWT)
        (
            "JWT_TOKEN",
            re.compile(r"\beyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]+\b"),
            "[REDACTED_JWT]",
        ),
        # Bearer Authorization tokens
        (
            "BEARER_AUTH",
            re.compile(r"(?i)(bearer\s+)([a-zA-Z0-9\-_\.=]{16,})"),
            r"\1[REDACTED_BEARER_TOKEN]",
        ),
        # GitHub Personal Access Tokens
        (
            "GITHUB_TOKEN",
            re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b"),
            "[REDACTED_GITHUB_TOKEN]",
        ),
        # GitLab Personal Access Tokens
        (
            "GITLAB_TOKEN",
            re.compile(r"\b(glpat-[0-9a-zA-Z\-_]{20,})\b"),
            "[REDACTED_GITLAB_TOKEN]",
        ),
        # Private Keys (RSA, EC, OpenSSH, PGP)
        (
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
                re.MULTILINE,
            ),
            "[REDACTED_PRIVATE_KEY]",
        ),
        # Passwords in Database connection strings
        (
            "URI_PASSWORD",
            re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]+://[^:]+:)([^@]+)(@)"),
            r"\1[REDACTED_DB_PASSWORD]\3",
        ),
        # Passwords in common CLI flags (--password, -p, --passwd, --secret, --token, --api-key)
        (
            "CLI_PASSWORD_FLAG",
            re.compile(
                r"(?i)(--?(?:password|passwd|secret|api[-_]?key|token|auth[-_]?token)[=\s]+)(['\"]?(?!\[REDACTED_)[^\s'\"]{4,}['\"]?)"
            ),
            r"\1[REDACTED_PASSWORD]",
        ),
        # Environment variable assignments (PASSWORD=xyz, SECRET=xyz)
        (
            "ENV_CREDENTIAL",
            re.compile(
                r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|AUTH_KEY)[A-Z0-9_]*)=(['\"]?(?!\[REDACTED_)[^\s'\"]{4,}['\"]?)"
            ),
            r"\1=[REDACTED_SECRET]",
        ),
        # Slack Webhook URLs
        (
            "SLACK_WEBHOOK",
            re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"),
            "[REDACTED_SLACK_WEBHOOK]",
        ),
        # Google Cloud API Keys (AIza...)
        (
            "GCP_API_KEY",
            re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
            "[REDACTED_GCP_KEY]",
        ),
        # Google Cloud Service Account Private Key ID & JSON fields
        (
            "GCP_SERVICE_ACCOUNT",
            re.compile(r'(?i)"(?:private_key_id|client_email|client_id|private_key)"\s*:\s*["\']([^"\']+)["\']'),
            r'"\1": "[REDACTED_GCP_SERVICE_ACCOUNT]"',
        ),
        # Basic Auth Headers
        (
            "BASIC_AUTH",
            re.compile(r"(?i)(authorization:\s*basic\s+)[A-Za-z0-9+/=]{10,}"),
            r"\1[REDACTED_BASIC_AUTH]",
        ),
    ]

    # Non-secret patterns to explicitly exclude from entropy redaction (prevents False Positives)
    GIT_COMMIT_HASH = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)
    UUID_PATTERN = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)

    def __init__(
        self,
        entropy_threshold: float = 3.8,
        min_token_len: int = 16,
        min_entropy_len: int | None = None,
    ):
        self.entropy_threshold = entropy_threshold
        self.min_token_len = min_entropy_len if min_entropy_len is not None else min_token_len

    @staticmethod
    def calculate_shannon_entropy(token: str) -> float:
        """Calculate Shannon entropy for a given string token."""
        if not token:
            return 0.0
        length = len(token)
        char_counts: dict[str, int] = {}
        for c in token:
            char_counts[c] = char_counts.get(c, 0) + 1
        entropy = 0.0
        for count in char_counts.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    def _is_safe_non_secret(self, token: str) -> bool:
        """Exempts known safe non-secret structures like Git commit hashes, UUIDs, and readable base64 blobs."""
        if self.GIT_COMMIT_HASH.fullmatch(token):
            return True
        if self.UUID_PATTERN.fullmatch(token):
            return True
        # Pure lowercase hex strings (e.g. git short SHA or sha256 digests)
        if re.fullmatch(r"[0-9a-f]{16,64}", token):
            return True

        # Check if base64 encoded payload is ordinary readable ASCII text/config
        if re.fullmatch(r"[A-Za-z0-9+/=]{16,}", token) and len(token) % 4 == 0:
            try:
                decoded_bytes = base64.b64decode(token, validate=True)
                decoded_text = decoded_bytes.decode("utf-8")
                # Printable ASCII characters
                if all(32 <= ord(c) <= 126 or c in "\n\r\t" for c in decoded_text):
                    dec_entropy = self.calculate_shannon_entropy(decoded_text)
                    if dec_entropy < 3.8 and not any(p[1].search(decoded_text) for p in self.PATTERNS):
                        return True
            except Exception:
                pass

        return False

    @staticmethod
    def _is_candidate_secret_token(token: str) -> bool:
        """True if token contains mixed character classes typical of cryptographic secrets."""
        has_upper = any(c.isupper() for c in token)
        has_lower = any(c.islower() for c in token)
        has_digit = any(c.isdigit() for c in token)
        classes = sum([has_upper, has_lower, has_digit])
        return classes >= 2

    def redact(self, text: str | None) -> tuple[str, list[dict[str, Any]]]:
        if not text:
            return "", []

        try:
            redacted = str(text)
            audit_log: list[dict[str, Any]] = []

            # 1. Regex Rule Pass
            for name, pattern, replacement in self.PATTERNS:
                matches = list(pattern.finditer(redacted))
                if matches:
                    audit_log.append({
                        "detector": "regex",
                        "pattern": name,
                        "count": len(matches),
                    })
                    redacted = pattern.sub(replacement, redacted)

            # 2. Shannon Entropy Pass for unrecognized high-entropy strings
            candidate_tokens = re.findall(r"[A-Za-z0-9+/=_\-]{16,}", redacted)
            for token in set(candidate_tokens):
                if token.startswith("[REDACTED_") or token.endswith("]"):
                    continue
                if self._is_safe_non_secret(token):
                    continue
                subparts = re.split(r"[/\\.\-]", token)
                for part in subparts:
                    if len(part) >= self.min_token_len and not self._is_safe_non_secret(part) and self._is_candidate_secret_token(part):
                        entropy = self.calculate_shannon_entropy(part)
                        if entropy >= self.entropy_threshold:
                            mask = f"[REDACTED_ENTROPY_KEY_{hash(part) % 10000:04d}]"
                            redacted = redacted.replace(part, mask)
                            audit_log.append({
                                "detector": "shannon_entropy",
                                "entropy": round(entropy, 2),
                                "length": len(part),
                                "masked_as": mask,
                            })

            return redacted, audit_log
        except Exception as e:
            # FAIL-CLOSED: never leak unredacted data if sanitizer encounters an internal error
            return "[REDACTED_FAIL_CLOSED_ERROR]", [{
                "detector": "fail_closed_fallback",
                "error": str(e),
            }]

    def validate_clean(self, text: str) -> bool:
        """Post-sanitization check to guarantee no known raw secrets remain."""
        if not text:
            return True
        for name, pattern, _ in self.PATTERNS:
            # If the pattern matches and does NOT contain a [REDACTED_...] tag
            for match in pattern.finditer(text):
                matched_str = match.group(0)
                if "[REDACTED_" not in matched_str:
                    return False
        return True


_default_redactor = SecretRedactor()


def redact_text(text: str | None) -> str:
    try:
        redacted, _ = _default_redactor.redact(text)
        return redacted
    except Exception:
        return "[REDACTED_FAIL_CLOSED_ERROR]"


def redact_event_payload(
    command: str,
    stdout: str | None = None,
    stderr: str | None = None,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    try:
        redacted_cmd, audits_cmd = _default_redactor.redact(command)
        redacted_out, audits_out = _default_redactor.redact(stdout or "")
        redacted_err, audits_err = _default_redactor.redact(stderr or "")
        all_audits = audits_cmd + audits_out + audits_err
        return redacted_cmd, redacted_out, redacted_err, all_audits
    except Exception as e:
        return (
            "[REDACTED_FAIL_CLOSED_ERROR]",
            "[REDACTED_FAIL_CLOSED_ERROR]",
            "[REDACTED_FAIL_CLOSED_ERROR]",
            [{"detector": "fail_closed_fallback", "error": str(e)}],
        )


def redact_structure(value: Any, *, max_depth: int = 8) -> tuple[Any, list[dict[str, Any]]]:
    """Redact every string and dictionary key in untrusted structured telemetry before persistence.

    State snapshots and webhook payloads often contain annotations, URLs, and
    environment fragments. Treating only terminal text as sensitive creates a
    bypass around the capture boundary.
    """
    audits: list[dict[str, Any]] = []

    def visit(item: Any, depth: int) -> Any:
        try:
            if depth > max_depth:
                return "[TRUNCATED_NESTED_DATA]"
            if isinstance(item, str):
                clean, findings = _default_redactor.redact(item)
                audits.extend(findings)
                return clean
            if isinstance(item, list):
                return [visit(child, depth + 1) for child in item[:200]]
            if isinstance(item, dict):
                clean_dict: dict[str, Any] = {}
                for key, child in list(item.items())[:200]:
                    clean_key, key_findings = _default_redactor.redact(str(key)[:128])
                    audits.extend(key_findings)
                    clean_dict[clean_key] = visit(child, depth + 1)
                return clean_dict
            return item
        except Exception:
            return "[REDACTED_FAIL_CLOSED_ERROR]"

    try:
        return visit(value, 0), audits
    except Exception as e:
        return "[REDACTED_FAIL_CLOSED_ERROR]", [{"detector": "fail_closed_fallback", "error": str(e)}]


class SecurityBoundaryViolation(Exception):
    """Raised when an unredacted secret breaches or fails the security boundary."""
    pass


class EventSanitizer:
    """Architectural Security Gate: enforces in-memory sanitization before storage or AI."""

    def __init__(self, redactor: SecretRedactor | None = None):
        self.redactor = redactor or _default_redactor

    def sanitize_event(self, event: Any) -> Any:
        """Sanitizes an Event or CapturedEvent in-memory.

        Fails closed: if sanitization fails or residual unredacted secrets are found,
        raises SecurityBoundaryViolation to prevent persistence.
        """
        try:
            # 1. Sanitize command
            raw_cmd = getattr(event, "raw_command", None) or getattr(event, "command", "")
            clean_cmd, _ = self.redactor.redact(raw_cmd)

            # 2. Sanitize stdout / stderr
            raw_out = getattr(event, "stdout_snippet", None) or getattr(event, "stdout_summary", None) or getattr(event, "stdout", "")
            clean_out, _ = self.redactor.redact(raw_out)

            raw_err = getattr(event, "stderr_snippet", None) or getattr(event, "stderr_summary", None) or getattr(event, "stderr", "")
            clean_err, _ = self.redactor.redact(raw_err)

            # 3. Sanitize CWD
            raw_cwd = getattr(event, "cwd", "")
            clean_cwd, _ = self.redactor.redact(raw_cwd)

            # 4. Sanitize snapshots if attached
            before_snap = getattr(event, "before_snapshot", None)
            if before_snap and hasattr(before_snap, "raw_state") and before_snap.raw_state:
                clean_before, _ = redact_structure(before_snap.raw_state)
                before_snap.raw_state = clean_before

            after_snap = getattr(event, "after_snapshot", None)
            if after_snap and hasattr(after_snap, "raw_state") and after_snap.raw_state:
                clean_after, _ = redact_structure(after_snap.raw_state)
                after_snap.raw_state = clean_after

            # Set sanitized fields back
            if hasattr(event, "raw_command"):
                event.raw_command = clean_cmd
            if hasattr(event, "command_redacted"):
                event.command_redacted = clean_cmd
            if hasattr(event, "stdout_snippet"):
                event.stdout_snippet = clean_out
            if hasattr(event, "stdout_summary"):
                event.stdout_summary = clean_out
            if hasattr(event, "stderr_snippet"):
                event.stderr_snippet = clean_err
            if hasattr(event, "stderr_summary"):
                event.stderr_summary = clean_err
            if hasattr(event, "cwd"):
                event.cwd = clean_cwd

            # 5. Security Post-Validation: Fail-closed if residual patterns found
            if not self.redactor.validate_clean(clean_cmd) or not self.redactor.validate_clean(clean_out) or not self.redactor.validate_clean(clean_err):
                raise SecurityBoundaryViolation("Sanitization post-validation failed: residual secret detected.")

            return event
        except Exception as e:
            raise SecurityBoundaryViolation(f"Sanitizer fail-closed: {e}") from e

