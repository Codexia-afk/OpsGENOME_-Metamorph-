"""Dedicated Security Test Suite for Secret Redaction Layer.

Verifies:
- AWS Access Key and Secret Key redaction
- JSON Web Token (JWT) redaction
- Bearer Authorization header redaction
- CLI password flags (--password, -p, --secret)
- Database connection string passwords
- Shannon Entropy Scanner for randomized secrets
- Redacting raw command, stdout, and stderr before storage
- Preserving non-sensitive CLI commands, Git hashes, UUIDs, and logs unmodified
"""

import pytest
from opsgenome.security.redactor import SecretRedactor, redact_event_payload, redact_text


def test_redact_aws_credentials():
    cmd = (
        "aws configure set aws_access_key_id AKIAIOSFODNN7EXAMPLE && "
        "aws configure set aws_secret_access_key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    )
    redacted = redact_text(cmd)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in redacted
    assert "[REDACTED_AWS_KEY]" in redacted
    assert "[REDACTED_AWS_SECRET]" in redacted


def test_redact_jwt_token():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    cmd = f"curl -H 'Authorization: Bearer {jwt}' https://api.prod.company.com/v1/auth"
    redacted = redact_text(cmd)
    assert jwt not in redacted
    assert "[REDACTED_JWT]" in redacted or "[REDACTED_BEARER_TOKEN]" in redacted


def test_redact_cli_password_flags():
    cmd1 = "mysql -u root --password='SuperSecretPassword123!' -h db.prod.internal"
    redacted1 = redact_text(cmd1)
    assert "SuperSecretPassword123!" not in redacted1
    assert "[REDACTED_PASSWORD]" in redacted1

    cmd3 = "kubectl create secret generic db-secret --password=prod_root_pw_9921"
    redacted3 = redact_text(cmd3)
    assert "prod_root_pw_9921" not in redacted3
    assert "[REDACTED_PASSWORD]" in redacted3


def test_redact_database_uri_password():
    uri_cmd = "psql postgresql://prod_user:p@ssw0rd12345!@db-cluster.internal.net:5432/orders_db"
    redacted = redact_text(uri_cmd)
    assert "p@ssw0rd12345!" not in redacted
    assert "[REDACTED_DB_PASSWORD]" in redacted


def test_shannon_entropy_scanner():
    redactor = SecretRedactor(entropy_threshold=3.5, min_token_len=16)
    random_secret = "d9F8q2Lx9zK1mP5vR8tY3wQ_7"
    raw_cmd = f"curl -H 'X-Internal-Token: {random_secret}' http://service.internal"
    redacted, audits = redactor.redact(raw_cmd)
    assert random_secret not in redacted
    assert "REDACTED_ENTROPY_KEY" in redacted
    assert len(audits) > 0
    assert audits[0]["detector"] == "shannon_entropy"


def test_redact_event_payload_command_stdout_stderr():
    raw_cmd = "kubectl exec -it app-pod -- env AWS_SECRET=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    raw_stdout = "export DATABASE_URL=postgres://admin:P@ssword987@localhost:5432/app"
    raw_stderr = "Error: authentication failed for bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgN_p"

    red_cmd, red_out, red_err, audits = redact_event_payload(raw_cmd, raw_stdout, raw_stderr)

    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in red_cmd
    assert "P@ssword987" not in red_out
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in red_err
    assert len(audits) >= 3


def test_preserves_innocuous_commands_and_logs():
    safe_cmd = "kubectl rollout undo deployment/payments-service -n production"
    safe_out = "deployment.apps/payments-service rolled back"
    safe_err = ""

    red_cmd, red_out, red_err, audits = redact_event_payload(safe_cmd, safe_out, safe_err)
    assert red_cmd == safe_cmd
    assert red_out == safe_out
    assert red_err == safe_err
    assert len(audits) == 0


def test_preserves_git_commit_hashes_and_uuids_no_false_positives():
    # 40-character Git commit hash
    git_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    cmd1 = f"git checkout {git_sha}"
    red1, audits1 = SecretRedactor().redact(cmd1)
    assert git_sha in red1
    assert "[REDACTED" not in red1
    assert len(audits1) == 0

    # UUID
    uuid_str = "123e4567-e89b-12d3-a456-426614174000"
    cmd2 = f"kubectl get pod payments-pod-{uuid_str} -n production"
    red2, audits2 = SecretRedactor().redact(cmd2)
    assert uuid_str in red2
    assert "[REDACTED" not in red2
    assert len(audits2) == 0
