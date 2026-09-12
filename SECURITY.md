# OpsGenome Security Architecture & Redaction Boundary

## Threat Model & Core Thesis

In modern site reliability engineering and DevOps, terminal capture during incident response presents a critical security dilemma:
**To learn how outages are fixed, capture engines observe high-velocity shell commands, environment variables, database URLs, and API tokens.**

If a capture system writes raw terminal commands to disk or ships unredacted payloads to a cloud LLM, it becomes a high-severity security vulnerability.

**OpsGenome's Core Security Guarantee:**
> **Fail-closed, client-side redaction boundary. Zero unredacted secrets ever touch disk, local SQLite storage, or LLM network payloads.**

---

## 1. Multi-Layer Redaction Pipeline

OpsGenome enforces an in-memory redaction pipeline before any event can be buffered, stored, or processed:

### Layer 1: Deterministic Pattern Scanning (Regex)
Pre-compiled regular expressions instantly scrub high-entropy key formats with zero overhead (<0.01ms):
- **AWS Credentials:** Access Keys (`AKIA...`), Secret Keys (`AWS_SECRET_ACCESS_KEY`), Session Tokens.
- **GitHub Tokens:** Personal Access Tokens (`ghp_...`), OAuth Tokens (`gho_...`), Fine-grained tokens (`github_pat_...`).
- **Slack Webhooks:** Incoming Webhook URLs (`hooks.slack.com/services/...`).
- **GCP / Google Cloud Keys:** API Keys (`AIza...`).
- **Database Connection URIs:** `postgres://user:pass@host:port/db`, `mysql://...`, `mongodb://...`, `redis://...`.
- **Private Keys & Certificates:** PEM headers (`-----BEGIN RSA PRIVATE KEY-----`), JWT tokens (`eyJ...`).
- **HTTP Authorization Headers:** Bearer tokens (`Bearer eyJ...`), Basic Auth headers (`Authorization: Basic ...`).

### Layer 2: Shannon Entropy Analysis
Deterministic regex cannot catch arbitrary high-entropy secrets (such as custom hex tokens, random base64 salts, or non-standard API keys).
OpsGenome computes the Shannon entropy for every space- or delimiter-separated token with length $\ge 16$:
$$H(X) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$
Tokens with Shannon entropy $H \ge 3.8$ are identified as cryptographic randomness and sanitized into `[REDACTED_HIGH_ENTROPY_SECRET]`.

### Layer 3: Strict Fail-Closed Error Boundary
If an unhandled exception or parsing failure occurs during redaction:
- The pipeline does **NOT** pass the raw event payload through.
- The pipeline immediately catches the exception and returns `[REDACTED_FAIL_CLOSED_ERROR]`.
- Failure in the security layer can never result in raw secret leakage.

### Layer 4: EventSanitizer & Pre-Persistence Invariant
Before any incident record, event telemetry, or state snapshot is written to SQLite or buffered in memory:
- `EventSanitizer.sanitize_event_in_memory` deep-traverses all string and dictionary fields (including nested metadata keys and values).
- `validate_clean` executes an assertion sweep. If any residual secret pattern is discovered, the pipeline raises `SecurityBoundaryViolation` and aborts the transaction immediately.

### Layer 5: Prompt Injection & LLM Telemetry Boundary
To prevent prompt injection attacks originating from compromised pod logs or malicious terminal output:
- All external operational telemetry sent to LLM reasoning prompts is strictly wrapped inside `<untrusted_operational_data>` XML tags.
- The system instructions explicitly enforce that data within `<untrusted_operational_data>` must be treated exclusively as inert operational telemetry, never as executable model instructions.

---

## 2. Field-Level Authenticated Encryption (Fernet: AES-128-CBC + HMAC-SHA256)

Sensitive operational fields (such as raw command strings) are cryptographically protected before persistence:
- **Algorithm:** Field-Level Authenticated Symmetric Encryption using Fernet (AES-128-CBC for confidentiality + HMAC-SHA256 for data authenticity).
- **Key Derivation:** 256-bit key derived via PBKDF2-HMAC-SHA256 (100,000 iterations) salted with local machine ID.
- **Database Storage:** Relational metadata is indexed in SQLite with strict POSIX `0600` file permissions; sensitive command strings are stored as encrypted blobs.
- **Tamper Resistance:** HMAC-SHA256 signature verification guarantees recorded command strings cannot be forged or tampered with out-of-band.

---

## 3. Evidence Grounding & Zero Hallucinations Policy

1. **AI Proposes, Evidence Verifies:** LLM models are never permitted to declare an incident resolved or invent provenance scores.
2. **Deterministic ID Cross-Referencing:** Every event ID cited in an assembled causal chain or Why/Why Not decision must exist in the cryptographic database record. If an LLM response cites a non-existent ID, it is rejected.
3. **State Transition Verification:** OpsGenome checks actual infrastructure diffs (e.g. Kubernetes replica health, connection pool capacity) rather than trusting shell exit code `0` alone.

---

## 4. Local-First & Air-Gapped Readiness

- OpsGenome runs 100% locally without mandatory cloud dependencies.
- If no Anthropic API key is provided, the engine runs its deterministic offline heuristic engine with 0ms network egress.
- Complete operational memory stays within your private VPC or local workstation.
