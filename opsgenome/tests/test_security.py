"""Test Suite for Secret Redaction and AES-256 Cryptography."""

import pytest
from opsgenome.security.crypto import LocalCryptoManager
from opsgenome.security.redactor import SecretRedactor, redact_text


def test_regex_redaction_aws():
    text = "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE && export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    redacted = redact_text(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in redacted
    assert "[REDACTED_AWS_KEY]" in redacted
    assert "[REDACTED_AWS_SECRET]" in redacted


def test_regex_redaction_github_token():
    text = "curl -H 'Authorization: token ghp_123456789012345678901234567890123456' https://api.github.com"
    redacted = redact_text(text)
    assert "ghp_123456789012345678901234567890123456" not in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted


def test_regex_redaction_db_uri():
    text = "psql postgresql://app_user:SuperSecretP@ssw0rd!@db.internal:5432/production"
    redacted = redact_text(text)
    assert "SuperSecretP@ssw0rd!" not in redacted
    assert "[REDACTED_DB_PASSWORD]" in redacted


def test_shannon_entropy_scanner():
    redactor = SecretRedactor(entropy_threshold=3.6, min_entropy_len=18)
    # High-entropy random token
    high_entropy_token = "d9F8q2Lx9zK1mP5vR8tY3wQ"
    text = f"curl -H 'X-Custom-Key: {high_entropy_token}' https://internal.service"
    redacted, audits = redactor.redact(text)
    assert high_entropy_token not in redacted
    assert "REDACTED_ENTROPY_KEY" in redacted


def test_local_crypto_encryption_roundtrip(tmp_path):
    crypto = LocalCryptoManager(key_dir=str(tmp_path))
    plaintext = "kubectl exec -it payments-pod-xyz -- env"
    ciphertext = crypto.encrypt(plaintext)
    assert ciphertext != plaintext
    decrypted = crypto.decrypt(ciphertext)
    assert decrypted == plaintext
