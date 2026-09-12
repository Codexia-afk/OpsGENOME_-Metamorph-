# OpsGenome Security Architecture & Redaction Boundary

## Threat Model & Core Thesis

In modern site reliability engineering and DevOps, terminal capture during incident response presents a critical security dilemma:
**To learn how outages are fixed, capture engines observe high-velocity shell commands, environment variables, database URLs, and API tokens.**

If a capture system writes raw terminal commands to disk or ships unredacted payloads to a cloud LLM, it becomes a high-severity security vulnerability.

**OpsGenome's Core Security Guarantee:**
> **Commands are redacted in-process on the client before transmission. The daemon communicates over a Unix domain socket restricted to the local user; no command data is ever exposed on a TCP port or network-visible loopback address.**

---

## 1. Multi-Layer Redaction Pipeline

OpsGenome enforces an in-process client-side redaction pipeline before any event can be serialized, transmitted over the socket, stored, or processed:

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

## 2. Field-Level Authenticated Encryption & Cryptographic Isolation

Sensitive operational fields and cryptographic keys are isolated client-side before persistence:
- **Algorithm:** Field-Level Authenticated Symmetric Encryption using Fernet (AES-128-CBC for confidentiality + HMAC-SHA256 for data authenticity).
- **Key Derivation:** 256-bit symmetric key generated via cryptography Fernet (`os.urandom`) and stored with POSIX `0600` file permissions in `~/.opsgenome/master.key`, or derived via SHA-256 for passphrase mode.
- **Database Storage:** Relational incident metadata and sanitized command strings are stored in local SQLite (WAL mode) with client-side secret redaction enforced before persistence; a Fernet authenticated encryption utility is included for field-level blob security.
- **Tamper Resistance:** HMAC-SHA256 verification guarantees that ciphertext payloads encrypted via the crypto utility cannot be forged or modified out-of-band.

---

## 3. Evidence Grounding & Verification Gate Policy

We do not trust the model's claims by default — every claim is verified against operational evidence, and claims that fail verification are caught and blocked before reaching the user:
1. **Dual Metric Honesty:** We measure both the *Model Hallucination Attempt Rate* (claims proposed by the model that failed grounding verification before any filtering, ~10.8% typical, 30% under adversarial stress) and the *Gate Enforcement Rate* (measured as $\text{successfully\_blocked} / \text{total\_failed}$; empirically 100% [3/3 blocked] in our adversarial test suite, actively tracking potential gate leaks per run).
2. **Deterministic ID Cross-Referencing:** Every event ID cited in an assembled causal chain or Why/Why Not decision must exist in the database record. If an LLM response cites a non-existent ID, it is blocked by the gate.
3. **Kubernetes Infrastructure State Transition Verification:** OpsGenome integrates a live Kubernetes State Collector (`opsgenome/watcher/k8s.py`) using the official Kubernetes API client. It directly inspects pod phases, container readiness (`0/1`), container restart counts, failure reasons (`CrashLoopBackOff`, `Error`, `OOMKilled`), and ConfigMap `resourceVersion` and SHA-256 checksums. If a command returns exit code `0` but pods remain degraded or ConfigMaps do not transition to the repaired version, the action is categorized as a Known Dead End rather than a fix. Collector connections fail visibly with specific typed exceptions (`K8sClusterUnreachableError`, `K8sNamespaceNotFoundError`, `K8sPermissionDeniedError`), never silently returning synthetic data. Shell hooks capture command strings, exit status, duration, and cwd; terminal stdout/stderr stream capture via a dedicated PTY wrapper is documented in `ROADMAP.md` as planned work.

---

## 4. Local-First & Air-Gapped Readiness

- OpsGenome runs 100% locally without mandatory cloud dependencies.
- If no Anthropic API key is provided, the engine runs its deterministic offline heuristic engine with 0ms network egress.
- Complete operational memory stays within your private VPC or local workstation.
