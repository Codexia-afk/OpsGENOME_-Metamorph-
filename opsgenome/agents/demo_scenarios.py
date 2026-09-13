"""Canonical Demo Incident Scenarios, Logs, and Cluster Failure Matrices for OpsGenome.

Decouples all demo incident targets, error logs, and simulated cluster failure modes
from the core orchestration and specialist logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from opsgenome.agents.models import ClusterIssue


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_DIR = REPO_ROOT / "demo-projects" / "multi-stack-incident"


@dataclass(frozen=True)
class DemoTargetSpec:
    relative_path: str
    stack: str
    default_code: str
    error_context: str
    description: str


# 1. Multi-Stack Incident Target Definitions
DEMO_TARGET_SPECS: list[DemoTargetSpec] = [
    DemoTargetSpec(
        relative_path="services/payment-engine/main.py",
        stack="python",
        default_code=(
            '"""Payment Engine Microservice - Core processing module."""\n\n'
            "def calculate_fee(amount: float) -> float:\n"
            '    """Calculates transaction fee based on tiered billing rates."""\n'
            "    if amount > 1000:\n"
            "        return amount * fee_rate  # Undefined fee_rate\n"
            "    return 0.0\n\n\n"
            "def process_payment(order_id: str, amount: float) -> dict:\n"
            "    fee = calculate_fee(amount)\n"
            '    return {"order_id": order_id, "amount": amount, "fee": fee, "status": "processed"}\n'
        ),
        error_context="NameError: name 'fee_rate' is not defined in services/payment-engine/main.py:6",
        description="Python Microservice with undefined variable fee_rate",
    ),
    DemoTargetSpec(
        relative_path="services/api-gateway/index.js",
        stack="nodejs",
        default_code=(
            "/**\n"
            " * API Gateway - Payment Proxy Route\n"
            " */\n"
            "const express = require('express');\n"
            "const app = express();\n\n"
            "app.post('/pay', async (req, res) => {\n"
            "    // Inbound request forwarded to internal payment engine\n"
            "    const resp = await fetch('http://payment:8080/charge');\n"
            "    const data = resp.json(); // Missing await on promise\n"
            "    res.send(data.status);\n"
            "});\n\n"
            "module.exports = app;\n"
        ),
        error_context="TypeError: Cannot read properties of Promise (pending) in services/api-gateway/index.js:8",
        description="Node.js Express Gateway with unawaited async response promise",
    ),
    DemoTargetSpec(
        relative_path="services/billing/PaymentProcessor.java",
        stack="java",
        default_code=(
            "package com.opsgenome.billing;\n\n"
            "public class PaymentProcessor {\n"
            "    public double computeTotal(Double amount) {\n"
            "        return amount.doubleValue() * 1.05;\n"
            "    }\n"
            "}\n"
        ),
        error_context="java.lang.NullPointerException: Cannot invoke 'java.lang.Double.doubleValue()' because 'amount' is null in PaymentProcessor.java:5",
        description="Java / JVM Billing Engine with unhandled null amount unboxing",
    ),
    DemoTargetSpec(
        relative_path="deployments/k8s/payment-deployment.yaml",
        stack="kubernetes",
        default_code=(
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: payment-engine\n"
            "  namespace: payments\n"
            "  labels:\n"
            "    app: payment-engine\n"
            "spec:\n"
            "  replicas: 3\n"
            "  selector:\n"
            "    matchLabels:\n"
            "      app: payment-engine\n"
            "  template:\n"
            "    metadata:\n"
            "      labels:\n"
            "        app: payment-engine\n"
            "    spec:\n"
            "      containers:\n"
            "      - name: payment\n"
            "        image: payment-engine:v1.2.0\n"
            "        ports:\n"
            "        - containerPort: 8080\n"
            "        resources:\n"
            "          limits:\n"
            "            memory: 64Mi # Severely undersized, causes OOMKilled\n"
            "          requests:\n"
            "            memory: 32Mi\n"
        ),
        error_context="OOMKilled: Container payment-engine exited with code 137. Memory cgroup out of memory.",
        description="Kubernetes Deployment with undersized 64Mi memory limit",
    ),
]


def extract_error_from_incident_log(target_file: str, default_err: str = "") -> str:
    """Extracts live error block corresponding to the target file from cross_stack_incident.log if present."""
    log_p = DEMO_DIR / "logs" / "cross_stack_incident.log"
    if not log_p.is_file():
        return default_err

    try:
        log_text = log_p.read_text(encoding="utf-8")
        target_name = Path(target_file).name
        target_stem = Path(target_file).stem

        # Match error sections mentioning target filename or service
        matched_lines: list[str] = []
        capture = False
        for line in log_text.splitlines():
            if target_name in line or (target_stem in line and any(k in line for k in ("ERROR", "Traceback", "Exception"))):
                capture = True
            elif target_name == "payment-deployment.yaml" and ("OOMKilled" in line or "memory cgroup" in line):
                capture = True

            if capture:
                matched_lines.append(line)
                if any(k in line for k in ("Error:", "Exception:", "OOMKilled", "TypeError:", "NameError:", "NullPointerException")):
                    break

        if matched_lines:
            return "\n".join(matched_lines)
    except Exception:
        pass
    return default_err


def get_demo_cross_stack_targets(
    read_from_disk_if_available: bool = True,
    use_absolute_paths: bool = False,
) -> list[tuple[str, str, str]]:
    """Returns list of (file_path, code_content, error_context) tuples for swarm analysis.

    If physical files exist in `demo-projects/multi-stack-incident/`, reads code
    and corresponding log context directly from disk so live changes are immediately picked up.
    """
    targets: list[tuple[str, str, str]] = []

    for spec in DEMO_TARGET_SPECS:
        disk_path = DEMO_DIR / spec.relative_path
        rel_repo_path = str(disk_path.relative_to(REPO_ROOT))
        chosen_path = str(disk_path) if use_absolute_paths else rel_repo_path

        if read_from_disk_if_available and disk_path.is_file():
            try:
                code = disk_path.read_text(encoding="utf-8")
                # Dynamically extract live error context from cross_stack_incident.log if available
                live_err = extract_error_from_incident_log(spec.relative_path, default_err=spec.error_context)
                targets.append((chosen_path, code, live_err))
                continue
            except Exception:
                pass

        targets.append((chosen_path, spec.default_code, spec.error_context))

    return targets


def reset_demo_incident_files() -> None:
    """Restores all physical demo files in `demo-projects/multi-stack-incident` to their canonical fault states."""
    for spec in DEMO_TARGET_SPECS:
        disk_path = DEMO_DIR / spec.relative_path
        if disk_path.parent.exists():
            disk_path.write_text(spec.default_code, encoding="utf-8")
            # Remove stale backup files if present
            bak_path = disk_path.with_suffix(disk_path.suffix + ".bak")
            if bak_path.exists():
                bak_path.unlink()


def parse_cluster_events_log(log_path: Path | None = None) -> list[ClusterIssue]:
    """Dynamically parses `k8s_cluster_events.log` from disk to construct live ClusterIssue objects."""
    p = log_path or (DEMO_DIR / "logs" / "k8s_cluster_events.log")
    if not p.is_file():
        return []

    issues: list[ClusterIssue] = []
    try:
        raw_lines = p.read_text(encoding="utf-8").splitlines()
        for raw in raw_lines:
            line = raw.strip()
            if not line or line.startswith("LAST SEEN"):
                continue

            m = re.match(r"^\S+\s+\S+\s+(\S+)\s+([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)\s+(.*)$", line)
            if not m:
                m = re.match(r"^(\S+)\s+([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)\s+(.*)$", line)
            if not m:
                continue

            reason, res_type_raw, res_name, msg = m.groups()
            res_type = res_type_raw.capitalize()

            if "crashloopbackoff" in msg.lower() or reason == "BackOff":
                env_match = re.search(r"Missing\s+`?([A-Z0-9_]+)`?\s+env", msg)
                env_var = env_match.group(1) if env_match else "DATABASE_URL"
                svc_name = res_name.split("-")[0] if "-" in res_name else res_name
                issues.append(
                    ClusterIssue(
                        severity="CRITICAL",
                        resource_type=res_type,
                        resource_name=res_name,
                        namespace="payments",
                        issue_type="CrashLoopBackOff",
                        root_cause=f"Startup failure: Container crashes at entrypoint due to missing mandatory `{env_var}` environment variable.",
                        impact=f"{res_name} intake down (100% 504 Gateway Timeouts across `/api/v1/charge`).",
                        immediate_remediation_cmd=f"kubectl set env deployment/{svc_name}-api {env_var}=\"postgresql://pg-primary.payments.svc:5432/payments\" -n payments",
                        declarative_yaml_patch=f"--- a/{svc_name}-deployment.yaml\n+++ b/{svc_name}-deployment.yaml\n@@ -18,6 +18,8 @@\n         env:\n+        - name: {env_var}\n+          value: \"postgresql://pg-primary.payments.svc:5432/payments\"\n         - name: LOG_LEVEL\n           value: \"info\"",
                        verification_cmd=f"kubectl rollout status deployment/{svc_name}-api -n payments --timeout=45s",
                        safety_tier="AUTOMATED_SAFE",
                    )
                )

            elif "oomkilled" in msg.lower() or reason == "OOMKilled":
                mem_match = re.search(r"memory limit\s+`?(\d+Mi)`?", msg)
                cur_limit = mem_match.group(1) if mem_match else "64Mi"
                svc_name = res_name.split("-")[0] if "-" in res_name else res_name
                issues.append(
                    ClusterIssue(
                        severity="HIGH",
                        resource_type=res_type,
                        resource_name=res_name,
                        namespace="payments",
                        issue_type="OOMKilled",
                        root_cause=f"Container cgroup memory limit `{cur_limit}` exceeded during message batch processing. Linux kernel sent SIGKILL (Exit Code 137).",
                        impact="Asynchronous settlement queue backed up by 14,200 transactions.",
                        immediate_remediation_cmd=f"kubectl patch deployment {svc_name} -n payments -p '{{\"spec\":{{\"template\":{{\"spec\":{{\"containers\":[{{\"name\":\"worker\",\"resources\":{{\"limits\":{{\"memory\":\"512Mi\"}},\"requests\":{{\"memory\":\"256Mi\"}}}}}}]}}}}}}'",
                        declarative_yaml_patch=f"--- a/{svc_name}-deployment.yaml\n+++ b/{svc_name}-deployment.yaml\n@@ -24,4 +24,4 @@\n         resources:\n           limits:\n-            memory: {cur_limit}\n+            memory: 512Mi\n           requests:\n             memory: 256Mi",
                        verification_cmd=f"kubectl get pod -n payments -l app={svc_name} -o jsonpath='{{.items[0].status.phase}}'",
                        safety_tier="AUTOMATED_SAFE",
                    )
                )

            elif "selector" in msg.lower() or reason == "FailedToCreateEndpoint":
                lbl_match = re.search(r"app=([a-zA-Z0-9_-]+)\s+matches 0 pods.*label app=([a-zA-Z0-9_-]+)", msg)
                old_lbl = lbl_match.group(1) if lbl_match else "web-v1"
                new_lbl = lbl_match.group(2) if lbl_match else "web-v2"
                issues.append(
                    ClusterIssue(
                        severity="HIGH",
                        resource_type=res_type,
                        resource_name=res_name,
                        namespace="default",
                        issue_type="SelectorMismatch",
                        root_cause=f"Service spec specifies `selector: app={old_lbl}`, but active pods run label `app={new_lbl}`. Endpoints list is empty.",
                        impact="Inbound user traffic dropped with 502 Bad Gateway at ingress layer.",
                        immediate_remediation_cmd=f"kubectl patch service {res_name} -n default -p '{{\"spec\":{{\"selector\":{{\"app\":\"{new_lbl}\"}}}}}}'",
                        declarative_yaml_patch=f"--- a/{res_name}-service.yaml\n+++ b/{res_name}-service.yaml\n@@ -9,3 +9,3 @@\n   selector:\n-    app: {old_lbl}\n+    app: {new_lbl}",
                        verification_cmd=f"kubectl get endpoints {res_name} -n default",
                        safety_tier="AUTOMATED_SAFE",
                    )
                )

            elif "probe" in msg.lower() or reason == "Unhealthy":
                port_match = re.search(r"port\s+(\d+).*listening on\s+(\d+)", msg)
                p_old = port_match.group(1) if port_match else "8081"
                p_new = port_match.group(2) if port_match else "9090"
                svc_name = res_name.split("-")[0] if "-" in res_name else res_name
                issues.append(
                    ClusterIssue(
                        severity="MEDIUM",
                        resource_type=res_type,
                        resource_name=res_name,
                        namespace="security",
                        issue_type="ReadinessProbeFailed",
                        root_cause=f"Readiness probe HTTP GET `/healthz` targets port {p_old}, but management server listens on port {p_new}. K8s controller marks pod Not Ready.",
                        impact="Pod marked unready; traffic not routed to healthy instances.",
                        immediate_remediation_cmd=f"kubectl patch deployment {svc_name} -n security -p '{{\"spec\":{{\"template\":{{\"spec\":{{\"containers\":[{{\"name\":\"auth\",\"readinessProbe\":{{\"httpGet\":{{\"port\":{p_new}}}}}}}]}}}}}}'",
                        declarative_yaml_patch=f"--- a/{svc_name}-deployment.yaml\n+++ b/{svc_name}-deployment.yaml\n@@ -31,3 +31,3 @@\n         readinessProbe:\n           httpGet:\n             path: /healthz\n-            port: {p_old}\n+            port: {p_new}",
                        verification_cmd=f"kubectl get pods -n security -l app={svc_name} -o jsonpath='{{.items[0].status.containerStatuses[0].ready}}'",
                        safety_tier="AUTOMATED_SAFE",
                    )
                )

            elif "port" in msg.lower() or reason == "FailedToStart":
                port_match = re.search(r"bind for (?:[0-9.]+:)?(\d+) failed", msg)
                pt = port_match.group(1) if port_match else "6379"
                alt_pt = str(int(pt) + 1) if pt.isdigit() else "6380"
                issues.append(
                    ClusterIssue(
                        severity="MEDIUM",
                        resource_type=res_type,
                        resource_name=res_name,
                        namespace="docker-compose",
                        issue_type="PortConflict",
                        root_cause=f"Docker Compose host port `{pt}` already bound by host system daemon, causing container startup failure.",
                        impact="Local caching offline; fallback to direct DB queries with increased latency.",
                        immediate_remediation_cmd=f"docker compose -f docker-compose.yml up -d --scale {res_name}=1",
                        declarative_yaml_patch=f"--- a/docker-compose.yml\n+++ b/docker-compose.yml\n@@ -14,3 +14,3 @@\n     ports:\n-      - \"{pt}:{pt}\"\n+      - \"{alt_pt}:{pt}\"",
                        verification_cmd=f"docker compose ps {res_name}",
                        safety_tier="ADMIN_CONFIRMATION_REQUIRED",
                    )
                )
    except Exception:
        pass

    return issues


# 2. Canonical Cluster Multi-Issue Matrix
def get_demo_cluster_issues(read_from_disk_if_available: bool = True) -> list[ClusterIssue]:
    """Returns standard SRE cluster audit matrix, dynamically parsed from `k8s_cluster_events.log` if present."""
    if read_from_disk_if_available:
        parsed = parse_cluster_events_log()
        if parsed and len(parsed) > 0:
            return parsed

    return [
        ClusterIssue(
            severity="CRITICAL",
            resource_type="Pod",
            resource_name="payments-api-7c9d",
            namespace="payments",
            issue_type="CrashLoopBackOff",
            root_cause="Startup failure: Container crashes at entrypoint due to missing mandatory `DATABASE_URL` environment variable.",
            impact="Payments intake down (100% 504 Gateway Timeouts across `/api/v1/charge`).",
            immediate_remediation_cmd="kubectl set env deployment/payments-api DATABASE_URL=\"postgresql://pg-primary.payments.svc:5432/payments\" -n payments",
            declarative_yaml_patch="""--- a/payments-deployment.yaml
+++ b/payments-deployment.yaml
@@ -18,6 +18,8 @@
         env:
+        - name: DATABASE_URL
+          value: "postgresql://pg-primary.payments.svc:5432/payments"
         - name: LOG_LEVEL
           value: "info"
""",
            verification_cmd="kubectl rollout status deployment/payments-api -n payments --timeout=45s",
            safety_tier="AUTOMATED_SAFE",
        ),
        ClusterIssue(
            severity="HIGH",
            resource_type="Pod",
            resource_name="batch-worker-4e2b",
            namespace="payments",
            issue_type="OOMKilled",
            root_cause="Container cgroup memory limit `64Mi` exceeded during message batch processing (peak allocation: 194Mi). Linux kernel sent SIGKILL (Exit Code 137).",
            impact="Asynchronous settlement queue backed up by 14,200 transactions.",
            immediate_remediation_cmd="kubectl patch deployment batch-worker -n payments -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"worker\",\"resources\":{\"limits\":{\"memory\":\"512Mi\"},\"requests\":{\"memory\":\"256Mi\"}}}]}}}}'",
            declarative_yaml_patch="""--- a/worker-deployment.yaml
+++ b/worker-deployment.yaml
@@ -24,4 +24,4 @@
         resources:
           limits:
-            memory: 64Mi
+            memory: 512Mi
           requests:
-            memory: 32Mi
+            memory: 256Mi
""",
            verification_cmd="kubectl get pod -n payments -l app=batch-worker -o jsonpath='{.items[0].status.phase}'",
            safety_tier="AUTOMATED_SAFE",
        ),
        ClusterIssue(
            severity="HIGH",
            resource_type="Service",
            resource_name="frontend-gateway",
            namespace="default",
            issue_type="SelectorMismatch",
            root_cause="Service spec specifies `selector: app=web-v1`, but active pods run label `app=web-v2`. Endpoints list is empty (`0/0 active endpoints`).",
            impact="Inbound user traffic dropped with 502 Bad Gateway at ingress layer.",
            immediate_remediation_cmd="kubectl patch service frontend-gateway -n default -p '{\"spec\":{\"selector\":{\"app\":\"web-v2\"}}}'",
            declarative_yaml_patch="""--- a/gateway-service.yaml
+++ b/gateway-service.yaml
@@ -9,3 +9,3 @@
   selector:
-    app: web-v1
+    app: web-v2
""",
            verification_cmd="kubectl get endpoints frontend-gateway -n default",
            safety_tier="AUTOMATED_SAFE",
        ),
        ClusterIssue(
            severity="MEDIUM",
            resource_type="Pod",
            resource_name="auth-service-89f1",
            namespace="security",
            issue_type="ReadinessProbeFailed",
            root_cause="Readiness probe HTTP GET `/healthz` targets port 8081, but management server listens on port 9090. K8s controller marks pod Not Ready (`0/1 Running`).",
            impact="Pod marked unready; traffic not routed to healthy auth instances.",
            immediate_remediation_cmd="kubectl patch deployment auth-service -n security -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"auth\",\"readinessProbe\":{\"httpGet\":{\"port\":9090}}}]}}}}'",
            declarative_yaml_patch="""--- a/auth-deployment.yaml
+++ b/auth-deployment.yaml
@@ -31,3 +31,3 @@
         readinessProbe:
           httpGet:
             path: /healthz
-            port: 8081
+            port: 9090
""",
            verification_cmd="kubectl get pods -n security -l app=auth-service -o jsonpath='{.items[0].status.containerStatuses[0].ready}'",
            safety_tier="AUTOMATED_SAFE",
        ),
        ClusterIssue(
            severity="MEDIUM",
            resource_type="Container",
            resource_name="redis-cache",
            namespace="docker-compose",
            issue_type="PortConflict",
            root_cause="Docker Compose host port `6379` already bound by host system daemon, causing container startup failure.",
            impact="Local caching offline; fallback to direct DB queries with 8x latency increase.",
            immediate_remediation_cmd="docker compose -f docker-compose.yml up -d --scale redis-cache=1",
            declarative_yaml_patch="""--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -14,3 +14,3 @@
     ports:
-      - "6379:6379"
+      - "6380:6379"
""",
            verification_cmd="docker compose ps redis-cache",
            safety_tier="ADMIN_CONFIRMATION_REQUIRED",
        ),
    ]


# 3. Incident & Cluster Event Logs
def get_demo_incident_log() -> str:
    """Returns raw cross-stack incident log stream."""
    log_file = DEMO_DIR / "logs" / "cross_stack_incident.log"
    if log_file.is_file():
        try:
            return log_file.read_text(encoding="utf-8")
        except Exception:
            pass

    return (
        '2026-09-13T04:12:01.102Z [payment-engine] INFO: Initializing PaymentProcessor listener on :8080\n'
        '2026-09-13T04:12:02.450Z [api-gateway] INFO: Route POST /pay registered with upstream http://payment:8080/charge\n'
        '2026-09-13T04:12:05.811Z [payment-engine] ERROR: Failed to compute tiered transaction fee\n'
        'Traceback (most recent call last):\n'
        '  File "services/payment-engine/main.py", line 6, in calculate_fee\n'
        '    return amount * fee_rate # Undefined fee_rate\n'
        "NameError: name 'fee_rate' is not defined in services/payment-engine/main.py:6\n"
        '2026-09-13T04:12:05.815Z [api-gateway] ERROR: Unhandled rejection in /pay route handler\n'
        'TypeError: Cannot read properties of Promise (pending) in services/api-gateway/index.js:8\n'
        '    at app.post (/services/api-gateway/index.js:8:23)\n'
        '    at processTicksAndRejections (node:internal/process/task_queues:95:5)\n'
        '2026-09-13T04:12:05.890Z [billing-jvm] ERROR: Exception in thread "main" java.lang.NullPointerException: '
        "Cannot invoke 'java.lang.Double.doubleValue()' because 'amount' is null in PaymentProcessor.java:5\n"
        '    at com.opsgenome.billing.PaymentProcessor.computeTotal(PaymentProcessor.java:5)\n'
        '2026-09-13T04:12:07.120Z [kubelet] WARNING: Pod payment-engine-789f6d4d8-x9z2l exceeded memory limit 64Mi.\n'
        'OOMKilled: Container payment-engine exited with code 137. Memory cgroup out of memory.\n'
    )


def get_demo_cluster_events_log() -> str:
    """Returns raw cluster events log stream detailing all 5 failure modes."""
    log_file = DEMO_DIR / "logs" / "k8s_cluster_events.log"
    if log_file.is_file():
        try:
            return log_file.read_text(encoding="utf-8")
        except Exception:
            pass

    return (
        "LAST SEEN   TYPE      REASON                  OBJECT                          MESSAGE\n"
        "45s         Warning   BackOff                 pod/payments-api-7c9d           Back-off restarting failed container payments in pod payments-api-7c9d_payments: CrashLoopBackOff. Missing DATABASE_URL env var.\n"
        "32s         Warning   OOMKilled               pod/batch-worker-4e2b           Container worker exceeded memory limit 64Mi. Sent SIGKILL (exit code 137).\n"
        "18s         Warning   FailedToCreateEndpoint  service/frontend-gateway        Service selector app=web-v1 matches 0 pods in default namespace. Active pods have label app=web-v2.\n"
        "12s         Warning   Unhealthy               pod/auth-service-89f1           Readiness probe failed: HTTP probe failed with statuscode: 404 connection refused on port 8081. Server listening on 9090.\n"
        "5s          Warning   FailedToStart           container/redis-cache           Docker Compose: bind for 0.0.0.0:6379 failed: port is already allocated on host.\n"
    )
