"""Live Integration Tests for Real Kubernetes Infrastructure State Collector.

Runs against an actual Kind or Minikube cluster (not mocked).
Validates:
1. Live API server connectivity and namespace inspection.
2. Real snapshot capture: pod phase, ready status, container restarts, ConfigMap resourceVersion/checksum.
3. Live ConfigMap modification detection: captures exact before/after resourceVersion delta.
4. Specific failure mode handling: K8sNamespaceNotFoundError, K8sClusterUnreachableError.
"""

import os
import subprocess
import tempfile
import time
import uuid
import yaml
import pytest
from opsgenome.watcher.k8s import (
    K8sClusterUnreachableError,
    K8sNamespaceNotFoundError,
    K8sPermissionDeniedError,
    K8sStateCollector,
)


def _cluster_available() -> bool:
    """Checks whether a live Kubernetes cluster is reachable."""
    try:
        collector = K8sStateCollector(namespace="payments")
        collector.connect()
        return True
    except Exception:
        return False


CLUSTER_AVAILABLE = _cluster_available()
pytestmark = pytest.mark.skipif(
    not CLUSTER_AVAILABLE,
    reason="Live Kubernetes cluster (Minikube/Kind) not reachable. Run 'minikube start' to run integration tests."
)


def test_k8s_collector_live_cluster_connectivity():
    """Step 1 & 3: Connects to live cluster and reads namespace resources via official API."""
    collector = K8sStateCollector(namespace="payments")
    collector.connect()
    raw_state, is_healthy, status_summary = collector.capture_raw_state()

    assert raw_state["namespace"] == "payments"
    assert "pods" in raw_state
    assert "configmaps" in raw_state
    assert "payments-config" in raw_state["configmaps"]
    cm_info = raw_state["configmaps"]["payments-config"]
    assert "resource_version" in cm_info
    assert "checksum" in cm_info
    assert int(cm_info["resource_version"]) > 0


def test_k8s_collector_live_configmap_diff_detection():
    """Step 3 & 5: Modifies a ConfigMap in the live cluster and asserts the diff identifies real resourceVersion."""
    collector = K8sStateCollector(namespace="payments")
    collector.connect()

    # 1. Capture snapshot before modification
    before_snap = collector.capture_snapshot(incident_id="inc-live-k8s-integ")
    b_rv = before_snap.raw_state["configmaps"]["payments-config"]["resource_version"]
    b_checksum = before_snap.raw_state["configmaps"]["payments-config"]["checksum"]

    # 2. Mutate ConfigMap in the live cluster using kubectl patch with a dynamic value
    import time
    new_timeout = f"{int(time.time() * 1000) % 100000}ms"
    patch_cmd = [
        "kubectl", "-n", "payments", "patch", "configmap", "payments-config",
        "-p", f'{{"data":{{"DB_TIMEOUT":"{new_timeout}"}}}}'
    ]
    res = subprocess.run(patch_cmd, capture_output=True, text=True, check=True)
    assert "patched" in res.stdout

    # 3. Capture snapshot after modification
    after_snap = collector.capture_snapshot(incident_id="inc-live-k8s-integ")
    a_rv = after_snap.raw_state["configmaps"]["payments-config"]["resource_version"]
    a_checksum = after_snap.raw_state["configmaps"]["payments-config"]["checksum"]

    # 4. Verify real Kubernetes resourceVersion incremented
    assert a_rv != b_rv
    assert int(a_rv) > int(b_rv)
    assert a_checksum != b_checksum

    # 5. Compute real diff and verify specific details
    detailed, diff_summary, is_recovery = collector.compute_diff(before_snap, after_snap)
    assert len(detailed["configmap_changes"]) >= 1
    cm_change = next(c for c in detailed["configmap_changes"] if c["name"] == "payments-config")
    assert cm_change["before_version"] == b_rv
    assert cm_change["after_version"] == a_rv
    assert cm_change["before_checksum"] == b_checksum
    assert cm_change["after_checksum"] == a_checksum
    assert f'ConfigMap "payments-config" resourceVersion updated ({b_rv} -> {a_rv}' in diff_summary


def test_k8s_collector_live_pod_lifecycle_state():
    """Verifies pod status, ready count, phase, and container status reflect live cluster."""
    collector = K8sStateCollector(namespace="payments")
    collector.connect()
    snap = collector.capture_snapshot(incident_id="inc-live-pod-test")

    assert len(snap.raw_state["pods"]) >= 1
    pod_name = list(snap.raw_state["pods"].keys())[0]
    pod_data = snap.raw_state["pods"][pod_name]
    assert pod_data["phase"] in ["Running", "Pending", "Failed", "Terminating"]
    assert "ready" in pod_data
    assert "restarts" in pod_data
    assert isinstance(pod_data["containers"], list)


def test_k8s_collector_raises_specific_errors_on_failure():
    """Proves collector fails visibly with specific exceptions instead of silent fake fallbacks."""
    # 1. Non-existent namespace must raise K8sNamespaceNotFoundError
    bad_ns_collector = K8sStateCollector(namespace="non-existent-namespace-404")
    with pytest.raises(K8sNamespaceNotFoundError) as ns_err:
        bad_ns_collector.connect()
    assert "non-existent-namespace-404" in str(ns_err.value)

    # 2. Missing/unreachable kubeconfig must raise K8sClusterUnreachableError
    unreachable_collector = K8sStateCollector(kubeconfig_path="/tmp/non_existent_kubeconfig_path_9999.yaml")
    with pytest.raises(K8sClusterUnreachableError) as unreach_err:
        unreachable_collector.connect()
    assert "unreachable" in str(unreach_err.value).lower()


def test_k8s_collector_live_full_failure_recovery_lifecycle():
    """FIX 3A: Definitive Live Failure -> Remediation -> Recovery -> Diff integration test.

    Proves against live Minikube cluster:
    1. Baseline healthy state (DB_TIMEOUT=30s, pod Running 1/1 ready).
    2. Real failure induction: ConfigMap DB_TIMEOUT="invalid_syntax_error" + pod recreation.
    3. Real workload reaction: wait for live pod to fail (Error / 0/1 ready).
    4. Real BEFORE snapshot captured via collector while cluster is unhealthy.
    5. Real remediation: ConfigMap DB_TIMEOUT="30s" + pod recreation.
    6. Real recovery: wait for live pod to converge to Running 1/1 ready.
    7. Real AFTER snapshot captured via collector while cluster is healthy.
    8. compute_diff() correctly identifies:
       - ConfigMap resourceVersion before != after
       - ConfigMap checksum before != after
       - Pod state transition / recovery
       - Overall transition classified as is_recovery = True
    """
    collector = K8sStateCollector(namespace="payments")
    collector.connect()

    # Step 1: Ensure known healthy baseline
    subprocess.run([
        "kubectl", "-n", "payments", "patch", "configmap", "payments-config",
        "-p", '{"data":{"DB_TIMEOUT":"30s"}}'
    ], check=True, capture_output=True)
    subprocess.run([
        "kubectl", "-n", "payments", "delete", "pod", "-l", "app=payments-service", "--wait=false"
    ], check=True, capture_output=True)

    baseline_healthy = False
    for _ in range(20):
        time.sleep(1)
        _, is_healthy, _ = collector.capture_raw_state()
        if is_healthy:
            baseline_healthy = True
            break
    assert baseline_healthy, "Failed to establish healthy baseline in payments namespace"

    # Step 2: Break ConfigMap for real
    subprocess.run([
        "kubectl", "-n", "payments", "patch", "configmap", "payments-config",
        "-p", '{"data":{"DB_TIMEOUT":"invalid_syntax_error"}}'
    ], check=True, capture_output=True)
    subprocess.run([
        "kubectl", "-n", "payments", "delete", "pod", "-l", "app=payments-service", "--wait=false"
    ], check=True, capture_output=True)

    # Step 3: Wait for real pod failure (poll live cluster)
    observed_unhealthy = False
    for _ in range(20):
        time.sleep(1)
        _, is_healthy, status_summary = collector.capture_raw_state()
        if not is_healthy:
            observed_unhealthy = True
            break
    assert observed_unhealthy, "Pod never entered unhealthy state after invalid ConfigMap injection"

    # Step 4: Capture real BEFORE snapshot from live cluster (zero synthetic values)
    before_snap = collector.capture_snapshot(incident_id="inc-live-lifecycle-audit")
    assert before_snap.is_healthy is False
    assert "payments-config" in before_snap.raw_state["configmaps"]
    b_rv = before_snap.raw_state["configmaps"]["payments-config"]["resource_version"]
    b_checksum = before_snap.raw_state["configmaps"]["payments-config"]["checksum"]

    # Step 5: Fix ConfigMap for real
    subprocess.run([
        "kubectl", "-n", "payments", "patch", "configmap", "payments-config",
        "-p", '{"data":{"DB_TIMEOUT":"30s"}}'
    ], check=True, capture_output=True)
    subprocess.run([
        "kubectl", "-n", "payments", "delete", "pod", "-l", "app=payments-service", "--wait=false"
    ], check=True, capture_output=True)

    # Step 6: Wait for real pod recovery (poll live cluster)
    observed_recovery = False
    for _ in range(25):
        time.sleep(1)
        _, is_healthy, status_summary = collector.capture_raw_state()
        if is_healthy:
            observed_recovery = True
            break
    assert observed_recovery, "Pod failed to recover after ConfigMap remediation"

    # Step 7: Capture real AFTER snapshot from live cluster (zero synthetic values)
    after_snap = collector.capture_snapshot(incident_id="inc-live-lifecycle-audit")
    assert after_snap.is_healthy is True
    a_rv = after_snap.raw_state["configmaps"]["payments-config"]["resource_version"]
    a_checksum = after_snap.raw_state["configmaps"]["payments-config"]["checksum"]

    # Step 8: Compute real diff and assert live transition properties
    detailed, diff_summary, is_recovery = collector.compute_diff(before_snap, after_snap)

    # Assert ConfigMap properties
    assert a_rv != b_rv
    assert int(a_rv) > int(b_rv)
    assert a_checksum != b_checksum
    assert len(detailed["configmap_changes"]) >= 1
    cm_change = next(c for c in detailed["configmap_changes"] if c["name"] == "payments-config")
    assert cm_change["before_version"] == b_rv
    assert cm_change["after_version"] == a_rv
    assert cm_change["before_checksum"] == b_checksum
    assert cm_change["after_checksum"] == a_checksum

    # Assert recovery classification and health delta
    assert is_recovery is True
    assert "RECOVERY:" in diff_summary
    assert before_snap.is_healthy is False
    assert after_snap.is_healthy is True


def test_k8s_collector_live_rbac_permission_denied_403():
    """FIX 3B: Proves K8sPermissionDeniedError against real Kubernetes RBAC HTTP 403.

    Creates a temporary unprivileged ServiceAccount without permissions to inspect
    the payments namespace, attempts connection via its real token, and proves the
    Kubernetes API server returns HTTP 403 Forbidden which maps to K8sPermissionDeniedError.
    """
    sa_name = f"test-rbac-sa-{uuid.uuid4().hex[:6]}"
    subprocess.run(["kubectl", "create", "sa", sa_name, "-n", "payments"], check=True, capture_output=True)

    temp_kc_path = None
    try:
        token_res = subprocess.run(
            ["kubectl", "create", "token", sa_name, "-n", "payments"],
            capture_output=True, text=True, check=True
        )
        sa_token = token_res.stdout.strip()

        with open(os.path.expanduser("~/.kube/config")) as f:
            kc = yaml.safe_load(f)

        cluster_info = kc["clusters"][0]["cluster"]
        unprivileged_config = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [{
                "name": "minikube-test",
                "cluster": cluster_info,
            }],
            "users": [{
                "name": "unprivileged-user",
                "user": {"token": sa_token},
            }],
            "contexts": [{
                "name": "unprivileged-context",
                "context": {
                    "cluster": "minikube-test",
                    "user": "unprivileged-user",
                    "namespace": "payments",
                },
            }],
            "current-context": "unprivileged-context",
        }

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.dump(unprivileged_config, tf)
            temp_kc_path = tf.name

        unprivileged_collector = K8sStateCollector(namespace="payments", kubeconfig_path=temp_kc_path)
        with pytest.raises(K8sPermissionDeniedError) as perm_err:
            unprivileged_collector.connect()

        err_msg = str(perm_err.value).lower()
        assert "denied" in err_msg or "forbidden" in err_msg
    finally:
        if temp_kc_path and os.path.exists(temp_kc_path):
            os.remove(temp_kc_path)
        subprocess.run(["kubectl", "delete", "sa", sa_name, "-n", "payments"], capture_output=True)

