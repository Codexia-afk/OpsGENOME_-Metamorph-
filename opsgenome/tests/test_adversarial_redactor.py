"""Adversarial Secret Redaction Stress Test Suite (15 Real-World Snippets).

Stress-tests SecretRedactor against:
- 10 Realistic Secret Snippets (Stack traces, env dumps, curl traces, pod describes)
  Must be redacted (0% False Negatives).
- 5 Adversarial Near-Misses (40-char Git SHAs, UUIDs, Base64 non-secret config blobs,
  Kubernetes pod names, container image SHA256 hashes)
  Must NOT be redacted (0% False Positives).
"""

import pytest
from opsgenome.security.redactor import SecretRedactor


# 15 Realistic Snippets: (snippet_text, should_redact, expected_pattern_or_reason)
ADVERSARIAL_SNIPPETS = [
    # 1. AWS Access Key in Kubernetes pod environment dump
    (
        "KUBERNETES POD ENV DUMP:\nPATH=/usr/local/bin\nAWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nNODE_ENV=production\n",
        True,
        "AWS_ACCESS_KEY",
    ),
    # 2. AWS Secret Access Key in application stack trace
    (
        "Traceback (most recent call last):\n  File 's3_uploader.py', line 44, in upload\n    session = boto3.Session(aws_secret_access_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')\nClientError: SignatureDoesNotMatch\n",
        True,
        "AWS_SECRET_KEY",
    ),
    # 3. JWT Bearer Token in HTTP debug trace
    (
        "> POST /api/v1/checkout HTTP/1.1\n> Host: api.payments.internal\n> Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlByb2QgVXNlciJ9.dozjgN_pqW8k9X1m\n> Content-Type: application/json\n",
        True,
        "JWT_TOKEN / BEARER_AUTH",
    ),
    # 4. Database URI with embedded password in configuration log
    (
        "2026-09-06T00:15:22Z [INFO] Connecting to primary datastore at postgresql://postgres_admin:SuperSecureProdP@ssw0rd!@db-cluster.prod.internal:5432/payments_db",
        True,
        "URI_PASSWORD",
    ),
    # 5. CLI Command with --password flag
    (
        "mysqldump -h rds.cluster.internal -u db_root --password='ProdDatabaseRootSecret123!' --databases payments > backup.sql",
        True,
        "CLI_PASSWORD_FLAG",
    ),
    # 6. Unrecognized high-entropy API token in custom header (Shannon Entropy detection)
    (
        "curl -X POST https://billing.vendor.com/v1/charge -H 'X-Vendor-Token: d9F8q2Lx9zK1mP5vR8tY3wQ_7' -d 'amount=5000'",
        True,
        "SHANNON_ENTROPY",
    ),
    # 7. GitHub Personal Access Token in git clone error log
    (
        "fatal: could not read Username for 'https://github.com': remote error: invalid token ghp_k8X2mP9zL1vR4tY7wQ3nB6vC9xZ2mK5pL8q1",
        True,
        "GITHUB_TOKEN",
    ),
    # 8. GitLab Personal Access Token in CI runner stderr
    (
        "gitlab-runner[142]: ERROR: Job failed: authentication failed for glpat-8bF7q1Lx9zK2mP5vR3tY with status 401 Unauthorized",
        True,
        "GITLAB_TOKEN",
    ),
    # 9. Private RSA Key in SSH configuration dump
    (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y3X7vK8...fake...private...key...data...\n-----END RSA PRIVATE KEY-----",
        True,
        "PRIVATE_KEY",
    ),
    # 10. CLI Environment variable assignment with sensitive secret
    (
        "export STRIPE_API_KEY='sk_live_51OzK9mP2Lx8zK1mP5vR8tY3wQ7xZ2mK'",
        True,
        "ENV_CREDENTIAL",
    ),

    # --- 5 ADVERSARIAL NEAR-MISSES (MUST NOT BE REDACTED - 0% FALSE POSITIVES) ---

    # 11. 40-character Git Commit Hash in git log
    (
        "commit 4b825dc642cb6eb9a060e54bf8d69288fbee4904 (HEAD -> main, origin/main)\nAuthor: SRE Team <sre@company.com>\nDate:   Sun Sep 6 00:00:00 2026 +0000\n    Fix memory limits in deployment\n",
        False,
        "GIT_COMMIT_HASH (Non-secret)",
    ),
    # 12. Standard UUID in Kubernetes object metadata
    (
        "metadata:\n  name: payments-deploy-pod-67f9b8\n  namespace: production\n  uid: 123e4567-e89b-12d3-a456-426614174000\n  resourceVersion: '987654'\n",
        False,
        "UUID_METADATA (Non-secret)",
    ),
    # 13. Base64-encoded non-secret configuration blob in ConfigMap
    (
        "apiVersion: v1\nkind: ConfigMap\ndata:\n  app_config.json: dGVzdF9jb25maWdfZGF0YV9rZXk=\n",
        False,
        "BASE64_CONFIG_BLOB (Non-secret)",
    ),
    # 14. Standard Kubernetes resource identifier & pod path
    (
        "NAME                                  READY   STATUS    RESTARTS   AGE\npayments-deploy-67f9b8-worker-pod    1/1     Running   0          42m\nauth-gateway-54a2b1-ingress-router   1/1     Running   0          2h\n",
        False,
        "K8S_RESOURCE_NAME (Non-secret)",
    ),
    # 15. Container image SHA256 digest in docker inspect
    (
        "{\n  'Image': 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',\n  'Created': '2026-09-01T12:00:00Z'\n}\n",
        False,
        "IMAGE_DIGEST (Non-secret)",
    ),
]


def test_adversarial_15_snippets_stress_test():
    redactor = SecretRedactor(entropy_threshold=3.8, min_token_len=16)

    false_negatives: list[str] = []
    false_positives: list[str] = []

    for idx, (snippet, should_redact, label) in enumerate(ADVERSARIAL_SNIPPETS):
        redacted_text, audit_logs = redactor.redact(snippet)
        has_redaction = "[REDACTED" in redacted_text or len(audit_logs) > 0

        if should_redact and not has_redaction:
            false_negatives.append(f"Snippet #{idx+1} ({label}): Failed to redact sensitive secret!")
        elif not should_redact and has_redaction:
            false_positives.append(f"Snippet #{idx+1} ({label}): Falsely redacted non-secret text: {redacted_text}")

    # Verify 0% False Negatives and 0% False Positives
    assert len(false_negatives) == 0, f"False Negatives detected: {false_negatives}"
    assert len(false_positives) == 0, f"False Positives detected: {false_positives}"


def test_entropy_isolated_bare_secret_without_regex():
    """Verifies that an unrecognized, bare 32-character high-entropy secret with NO prefix/keywords
    is missed by all regex patterns but caught and redacted by the Shannon entropy scanner.
    """
    redactor = SecretRedactor(entropy_threshold=3.8, min_token_len=16)
    bare_secret = "d9F8q2Lx9zK1mP5vR8tY3wQ7aB4cD1eF"
    text = f"raw_data_output: {bare_secret}"

    # 1. Assert that NO regex patterns match this bare token
    for name, pattern, _ in redactor.PATTERNS:
        assert not pattern.search(text), f"Pattern {name} unexpectedly matched bare secret token"

    # 2. Assert that SecretRedactor's Shannon entropy detector catches and redacts it
    redacted_text, audit_logs = redactor.redact(text)
    assert bare_secret not in redacted_text
    assert "[REDACTED_ENTROPY_KEY_" in redacted_text
    assert any(log.get("detector") == "shannon_entropy" for log in audit_logs)

