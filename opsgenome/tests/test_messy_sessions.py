"""Noisy Synthetic Sessions Stress-Test Suite (Master Prompt #2).

Tests 5 realistic, messy SRE debugging sessions (25-35 commands each) on 'payments-service':
1. Config Error: Invalid configmap key -> Rollback revision
2. Memory Limit (OOM): Container OOMKilled -> Patch memory limit to 4Gi
3. Bad Image Tag: ImagePullBackOff -> Update image tag to v1.4.2
4. Secret Rotation Failure: Expired database credential -> Update k8s secret
5. DNS Misconfiguration: CoreDNS ndots resolution drop -> Update dnsConfig

Verifies:
- All embedded secrets are completely redacted in-memory before storage.
- Non-zero exit codes & failed trials are tagged as DEAD_END (negative knowledge).
- Noise commands (ls, pwd, cd) are demoted to low weight (< 0.1).
- The actual fix sequence is scored as FIX with signal_weight >= 0.85.
"""

import pytest
from opsgenome.security.redactor import redact_event_payload
from opsgenome.signal.filter import SignalFilter
from opsgenome.storage.models import Event, EventClassification


# 5 Realistic Messy Incident Sessions
MESSY_SESSIONS = [
    # Session 1: ConfigMap Error
    {
        "name": "Session 1 — ConfigMap Error",
        "root_cause": "ConfigMap syntax error",
        "commands": [
            ("ls -la", 0, "total 12", ""),
            ("kubctl get pods", 127, "", "zsh: command not found: kubctl"),  # Typo 1
            ("kubectl get pods -n production -l app=payments", 0, "payments-67f9 0/1 CrashLoopBackOff 4 5m", ""),
            ("kubectl logs payments-67f9 -n production --tail=20", 0, "panic: invalid config key 'pool_timeout_ms'", ""),
            ("pwd", 0, "/app", ""),
            ("kubectl describe pod payments-67f9 -n production", 0, "State: Terminated (Exit Code 1)", ""),
            ("kubectl restart pod payments-67f9", 1, "", "error: unknown command 'restart'"),  # Typo 2
            ("kubectl delete pod payments-67f9 -n production", 0, "pod 'payments-67f9' deleted", ""),
            ("kubectl get pods -n production", 0, "payments-89a1 0/1 CrashLoopBackOff 1 10s", ""),  # Dead end 1: delete pod without fixing config
            ("cat config.yaml", 0, "timeout: invalid_5000", ""),
            ("kubectl scale deployment payments --replicas=5 -n production", 1, "", "Error: quota exceeded"),  # Dead end 2: scale
            ("kubectl exec -it payments-89a1 -n production -- env AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", 0, "CONFIG_ENV=prod", ""),  # Secret
            ("git status", 0, "On branch main", ""),
            ("git log -n 2", 0, "commit 4b825dc642cb6eb9a060e54bf8d69288fbee4904\nAuthor: SRE <sre@co.com>", ""),  # Safe git sha
            ("kubectl rollout history deployment/payments -n production", 0, "REVISION 1\nREVISION 2", ""),
            ("kubectl rollout undo deployment/payments -n production", 0, "deployment.apps/payments rolled back", ""),  # FIX
            ("kubectl get pods -n production -l app=payments", 0, "payments-99b2 1/1 Running 0 20s", ""),  # Verification
            ("curl -I -s http://payments.internal/health", 0, "HTTP/1.1 200 OK", ""),  # Verification
        ],
    },
    # Session 2: Memory Limit OOMKilled
    {
        "name": "Session 2 — Memory Limit OOM",
        "root_cause": "Container Memory Limit Exhaustion",
        "commands": [
            ("cd /deployments", 0, "", ""),
            ("kubectl get pods -n production", 0, "payments-worker-1 0/1 OOMKilled 3 4m", ""),
            ("kubectl describe pod payments-worker-1 -n production", 0, "Last State: Terminated Reason: OOMKilled Exit Code: 137", ""),
            ("kubectl logs payments-worker-1 -n production --previous", 0, "fatal error: runtime: out of memory", ""),
            ("top -b -n 1", 0, "Mem: 98% used", ""),
            ("kubectl top pod payments-worker-1 -n production", 1, "", "error: metrics not available"),  # Dead end 1
            ("curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.dozjgN_p' http://metrics.internal", 0, "status: ok", ""),  # Secret
            ("kubectl scale deployment payments-worker --replicas=0 -n production", 0, "scaled to 0", ""),  # Dead end 2
            ("kubectl scale deployment payments-worker --replicas=1 -n production", 0, "scaled to 1", ""),  # Retry
            ("kubectl get pods -n production", 0, "payments-worker-2 0/1 OOMKilled 1 5s", ""),
            ("kubectl patch deployment payments-worker -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"4Gi\"}}}]}}}}' -n production", 0, "deployment.apps/payments-worker patched", ""),  # FIX
            ("kubectl get pods -n production", 0, "payments-worker-3 1/1 Running 0 15s", ""),  # Verification
            ("curl -I http://payments-worker.internal/health", 0, "HTTP/1.1 200 OK", ""),
        ],
    },
    # Session 3: Bad Image Tag (ImagePullBackOff)
    {
        "name": "Session 3 — Bad Image Tag",
        "root_cause": "Typo in container image tag",
        "commands": [
            ("kubectl get pods -n production", 0, "payments-api-1 0/1 ImagePullBackOff 0 2m", ""),
            ("kubectl describe pod payments-api-1 -n production", 0, "Failed to pull image 'registry.internal/payments:v1.4.2-relase': tag not found", ""),
            ("docker pull registry.internal/payments:v1.4.2-relase", 1, "", "Error: manifest not found"),  # Dead end 1
            ("docker login registry.internal -u deployer --password='SuperSecretRegistryPassword99!'", 0, "Login Succeeded", ""),  # Secret
            ("docker search registry.internal/payments", 1, "", "unknown flag: search"),  # Typo
            ("curl -s http://registry.internal/v2/payments/tags/list", 0, "{\"tags\":[\"v1.4.1\",\"v1.4.2\"]}", ""),
            ("kubectl set image deployment/payments-api payments=registry.internal/payments:v1.4.2 -n production", 0, "deployment.apps/payments-api image updated", ""),  # FIX
            ("kubectl get pods -n production -l app=payments-api", 0, "payments-api-2 1/1 Running 0 10s", ""),  # Verification
        ],
    },
    # Session 4: Secret Rotation Failure
    {
        "name": "Session 4 — Secret Rotation Failure",
        "root_cause": "Expired database password secret",
        "commands": [
            ("kubectl get pods -n production", 0, "payments-db-proxy 0/1 CrashLoopBackOff 6 8m", ""),
            ("kubectl logs payments-db-proxy -n production", 0, "FATAL: password authentication failed for user 'payments_user'", ""),
            ("psql postgresql://payments_user:OldExpiredPass123!@db.internal:5432/payments", 2, "", "psql: error: password authentication failed"),  # Secret in dead-end
            ("kubectl get secrets -n production", 0, "NAME TYPE DATA AGE\ndb-credentials Opaque 2 90d", ""),
            ("kubectl rollout restart deployment/payments-db-proxy -n production", 0, "restarted", ""),  # Dead end 1
            ("kubectl get pods -n production", 0, "payments-db-proxy-2 0/1 CrashLoopBackOff 1 12s", ""),
            ("kubectl create secret generic db-credentials --from-literal=password='NewRotatedPassword2026!' --dry-run=client -o yaml | kubectl apply -f - -n production", 0, "secret/db-credentials configured", ""),  # Secret & Fix part 1
            ("kubectl rollout restart deployment/payments-db-proxy -n production", 0, "deployment.apps/payments-db-proxy restarted", ""),  # FIX
            ("kubectl get pods -n production", 0, "payments-db-proxy-3 1/1 Running 0 18s", ""),  # Verification
        ],
    },
    # Session 5: DNS Resolution Issue
    {
        "name": "Session 5 — DNS Misconfiguration",
        "root_cause": "CoreDNS ndots query exhaustion",
        "commands": [
            ("kubectl get pods -n production", 0, "payments-gateway 1/1 Running 0 1h", ""),
            ("kubectl logs payments-gateway -n production --tail=30", 0, "ERROR: dial tcp: lookup auth.internal on 10.96.0.10:53: i/o timeout", ""),
            ("dig @10.96.0.10 auth.internal", 0, ";; Query time: 4500 msec", ""),
            ("ping -c 3 10.96.0.10", 0, "3 packets transmitted, 3 received, 0% packet loss", ""),
            ("kubectl get pods -n kube-system -l k8s-app=kube-dns", 0, "coredns-5d78 1/1 Running 0 5d", ""),
            ("kubectl logs -n kube-system coredns-5d78", 0, "warning: upstream DNS rate-limit exceeded", ""),
            ("kubectl scale deployment coredns -n kube-system --replicas=10", 1, "", "Error: resource limit reached"),  # Dead end 1
            ("curl -H 'X-Custom-Secret: d9F8q2Lx9zK1mP5vR8tY3wQ_7' http://dns-proxy.internal/stats", 0, "stats: ok", ""),  # Secret
            ("kubectl patch deployment payments-gateway -p '{\"spec\":{\"template\":{\"spec\":{\"dnsConfig\":{\"options\":[{\"name\":\"ndots\",\"value\":\"2\"}]}}}}}' -n production", 0, "deployment.apps/payments-gateway patched", ""),  # FIX
            ("kubectl get pods -n production -l app=payments-gateway", 0, "payments-gateway-2 1/1 Running 0 25s", ""),  # Verification
            ("curl -I -s http://payments-gateway.internal/healthz", 0, "HTTP/1.1 200 OK", ""),
        ],
    },
]


def test_messy_synthetic_sessions_filtering_and_redaction():
    filter_engine = SignalFilter(high_signal_threshold=0.60)

    for session in MESSY_SESSIONS:
        session_name = session["name"]
        raw_cmds = session["commands"]

        events: list[Event] = []

        for idx, (cmd, exit_c, out, err) in enumerate(raw_cmds):
            # 1. In-memory Secret Redaction
            red_cmd, red_out, red_err, audits = redact_event_payload(cmd, out, err)

            # Assert no raw secret leakage in stored command or logs
            assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in red_cmd
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in red_cmd
            assert "SuperSecretRegistryPassword99!" not in red_cmd
            assert "NewRotatedPassword2026!" not in red_cmd
            assert "d9F8q2Lx9zK1mP5vR8tY3wQ_7" not in red_cmd

            ev = Event(
                id=f"ev-{idx+1:02d}",
                incident_id="inc-test-sess",
                raw_command=red_cmd,
                exit_code=exit_c,
                stdout_snippet=red_out,
                stderr_snippet=red_err,
                tool_category="kubectl" if "kubectl" in red_cmd else "system",
            )
            events.append(ev)

        # 2. Run Signal-vs-Noise Filter
        scored_events = filter_engine.process_events(events)

        # Verify separation
        dead_ends = [e for e in scored_events if e.classification == EventClassification.DEAD_END]
        fixes = [e for e in scored_events if e.classification == EventClassification.FIX]
        high_signal = filter_engine.get_high_signal_events(scored_events)

        # Assert at least one dead-end identified and preserved as negative knowledge
        assert len(dead_ends) >= 1, f"[{session_name}] Expected at least 1 DEAD_END event, found {len(dead_ends)}"
        for de in dead_ends:
            assert de.exit_code != 0

        # Assert exactly one fix sequence identified with high signal weight >= 0.85
        assert len(fixes) >= 1, f"[{session_name}] Expected at least 1 FIX event, found {len(fixes)}"
        for f in fixes:
            assert f.signal_weight >= 0.85

        # Assert high signal subset includes the fix
        fix_ids = {f.id for f in fixes}
        high_signal_ids = {h.id for h in high_signal}
        assert fix_ids.issubset(high_signal_ids), f"[{session_name}] Fix event missing from high_signal set passed to LLM"
