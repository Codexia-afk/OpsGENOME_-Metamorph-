"""Real Kubernetes Infrastructure State Collector for OpsGenome.

Uses official kubernetes Python client to:
1. Connect directly to real Kubernetes API server (Kind, Minikube, or cloud).
2. Poll pod statuses, container CrashLoopBackOff states, restart counts, and ConfigMap resourceVersions.
3. Capture before/after snapshots at incident boundaries and during remediation.
4. Compute deterministic, granular state diffs (exact resourceVersion, restart count delta, phase transition).
5. Handle real failure modes with specific exceptions (cluster unreachable, namespace missing, RBAC denied).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from opsgenome.storage.models import StateSnapshot

logger = logging.getLogger("opsgenome.watcher.k8s")


class K8sCollectorError(Exception):
    """Base exception for Kubernetes state collection errors."""
    pass


class K8sClusterUnreachableError(K8sCollectorError):
    """Raised when the Kubernetes API server is unreachable or kubeconfig is missing/invalid."""
    pass


class K8sNamespaceNotFoundError(K8sCollectorError):
    """Raised when the target Kubernetes namespace does not exist on the cluster."""
    pass


class K8sPermissionDeniedError(K8sCollectorError):
    """Raised when RBAC denies authorization to inspect the required resources."""
    pass


class K8sStateCollector:
    """Collects and diffs real infrastructure state from a live Kubernetes cluster."""

    def __init__(
        self,
        namespace: str = "default",
        kubeconfig_path: str | None = None,
        context: str | None = None,
        poll_interval_seconds: float = 5.0,
    ):
        self.namespace = os.environ.get("OPSGENOME_K8S_NAMESPACE", namespace)
        self.kubeconfig_path = kubeconfig_path or os.environ.get("KUBECONFIG")
        self.context = context
        self.poll_interval = poll_interval_seconds
        self.allow_simulation = os.environ.get("OPSGENOME_K8S_SIMULATION") == "1"
        self._sim_collector = None
        self.is_simulated = False

        self._core_api: client.CoreV1Api | None = None
        self._apps_api: client.AppsV1Api | None = None
        self._polling = False
        self._poll_thread: threading.Thread | None = None
        self._poll_lock = threading.Lock()
        self._latest_snapshot: StateSnapshot | None = None
        self._snapshots: list[StateSnapshot] = []

    def connect(self) -> None:
        """Initializes connection to the Kubernetes API server with specific failure diagnosis."""
        if self.allow_simulation:
            from opsgenome.watcher.k8s_sim import SimulatedK8sCollector
            self._sim_collector = SimulatedK8sCollector(namespace=self.namespace)
            self._sim_collector.connect()
            self.is_simulated = True
            return

        target_kubeconfig = self.kubeconfig_path or os.path.expanduser("~/.kube/config")
        try:
            if os.path.exists(target_kubeconfig):
                config.load_kube_config(
                    config_file=target_kubeconfig,
                    context=self.context,
                )
            else:
                try:
                    config.load_incluster_config()
                except Exception as in_cluster_err:
                    if self.allow_simulation:
                        from opsgenome.watcher.k8s_sim import SimulatedK8sCollector
                        self._sim_collector = SimulatedK8sCollector(namespace=self.namespace)
                        self._sim_collector.connect()
                        self.is_simulated = True
                        return
                    raise K8sClusterUnreachableError(
                        f"Kubernetes cluster unreachable: kubeconfig not found at \"{target_kubeconfig}\" "
                        f"and in-cluster service account configuration failed: {in_cluster_err}"
                    ) from in_cluster_err

            self._core_api = client.CoreV1Api()
            self._apps_api = client.AppsV1Api()
        except K8sCollectorError:
            if self.allow_simulation:
                from opsgenome.watcher.k8s_sim import SimulatedK8sCollector
                self._sim_collector = SimulatedK8sCollector(namespace=self.namespace)
                self._sim_collector.connect()
                self.is_simulated = True
                return
            raise
        except Exception as exc:
            if self.allow_simulation:
                from opsgenome.watcher.k8s_sim import SimulatedK8sCollector
                self._sim_collector = SimulatedK8sCollector(namespace=self.namespace)
                self._sim_collector.connect()
                self.is_simulated = True
                return
            raise K8sClusterUnreachableError(
                f"Failed to connect to Kubernetes cluster API: {exc}"
            ) from exc

        # Fail visibly and specifically if namespace does not exist or RBAC fails
        self._verify_cluster_and_namespace()

    def _verify_cluster_and_namespace(self) -> None:
        """Ensures cluster is responsive and namespace exists with proper RBAC permissions."""
        if not self._core_api:
            raise K8sClusterUnreachableError("Kubernetes client is not initialized.")

        try:
            self._core_api.read_namespace(name=self.namespace)
        except ApiException as api_err:
            if api_err.status == 404:
                raise K8sNamespaceNotFoundError(
                    f"Kubernetes namespace \"{self.namespace}\" does not exist on cluster."
                ) from api_err
            elif api_err.status == 403:
                raise K8sPermissionDeniedError(
                    f"RBAC authorization denied for namespace \"{self.namespace}\": {api_err.reason}"
                ) from api_err
            else:
                raise K8sClusterUnreachableError(
                    f"Kubernetes API server error when querying namespace \"{self.namespace}\" (status {api_err.status}): {api_err.reason}"
                ) from api_err
        except Exception as conn_err:
            raise K8sClusterUnreachableError(
                f"Kubernetes cluster unreachable at configured endpoint: {conn_err}"
            ) from conn_err

    def check_health(self) -> dict[str, Any]:
        """Diagnoses connection and namespace health without raising uncaught exceptions."""
        try:
            self.connect()
            if self.is_simulated and self._sim_collector:
                return self._sim_collector.check_health()
            return {"healthy": True, "namespace": self.namespace, "error": None}
        except K8sNamespaceNotFoundError as e:
            return {"healthy": False, "namespace": self.namespace, "error": f"Namespace not found: {e}"}
        except K8sPermissionDeniedError as e:
            return {"healthy": False, "namespace": self.namespace, "error": f"Permission denied (RBAC): {e}"}
        except K8sClusterUnreachableError as e:
            return {"healthy": False, "namespace": self.namespace, "error": f"Cluster unreachable: {e}"}
        except Exception as e:
            return {"healthy": False, "namespace": self.namespace, "error": f"Unexpected error: {e}"}

    def capture_raw_state(self) -> tuple[dict[str, Any], bool, str]:
        """Polls live Kubernetes API for pod statuses, container states, and ConfigMap metadata."""
        if self.is_simulated and self._sim_collector:
            return self._sim_collector.capture_raw_state()
        if not self._core_api:
            self.connect()
        if self.is_simulated and self._sim_collector:
            return self._sim_collector.capture_raw_state()

        # 1. Gather Pods
        pods_state: dict[str, Any] = {}
        try:
            pod_list = self._core_api.list_namespaced_pod(namespace=self.namespace)
            for p in pod_list.items:
                name = p.metadata.name
                phase = p.status.phase or "Unknown"
                container_statuses = []
                total_restarts = 0
                ready_count = 0
                total_containers = len(p.status.container_statuses) if p.status.container_statuses else 0
                reasons = []

                if p.status.container_statuses:
                    for cs in p.status.container_statuses:
                        total_restarts += cs.restart_count
                        if cs.ready:
                            ready_count += 1
                        state_info: dict[str, Any] = {}
                        if cs.state.running:
                            state_info["state"] = "running"
                            state_info["started_at"] = cs.state.running.started_at.isoformat() if cs.state.running.started_at else None
                        elif cs.state.waiting:
                            state_info["state"] = "waiting"
                            state_info["reason"] = cs.state.waiting.reason
                            state_info["message"] = cs.state.waiting.message
                            if cs.state.waiting.reason:
                                reasons.append(cs.state.waiting.reason)
                        elif cs.state.terminated:
                            state_info["state"] = "terminated"
                            state_info["exit_code"] = cs.state.terminated.exit_code
                            state_info["reason"] = cs.state.terminated.reason
                            if cs.state.terminated.reason:
                                reasons.append(cs.state.terminated.reason)

                        container_statuses.append({
                            "name": cs.name,
                            "ready": cs.ready,
                            "restart_count": cs.restart_count,
                            "image": cs.image,
                            "state": state_info,
                        })

                is_terminating = p.metadata.deletion_timestamp is not None
                ready_str = f"{ready_count}/{total_containers}" if total_containers else ("1/1" if phase == "Running" else "0/1")
                pods_state[name] = {
                    "phase": "Terminating" if is_terminating else phase,
                    "ready": ready_str,
                    "ready_count": ready_count,
                    "total_containers": total_containers,
                    "restarts": total_restarts,
                    "reasons": reasons,
                    "containers": container_statuses,
                    "node_name": p.spec.node_name or "",
                    "pod_ip": p.status.pod_ip or "",
                    "is_terminating": is_terminating,
                }
        except ApiException as api_err:
            if api_err.status == 403:
                raise K8sPermissionDeniedError(f"RBAC denied listing pods in {self.namespace}: {api_err.reason}") from api_err
            raise K8sClusterUnreachableError(f"Failed to query pods from Kubernetes API: {api_err.reason}") from api_err
        except Exception as exc:
            raise K8sClusterUnreachableError(f"Connection error querying pods: {exc}") from exc

        # 2. Gather ConfigMaps
        configmaps_state: dict[str, Any] = {}
        try:
            cm_list = self._core_api.list_namespaced_config_map(namespace=self.namespace)
            for cm in cm_list.items:
                name = cm.metadata.name
                rv = cm.metadata.resource_version
                data = cm.data or {}
                data_keys = sorted(data.keys())
                # Compute deterministic sha256 checksum over data entries
                content_str = json.dumps({k: data[k] for k in data_keys}, sort_keys=True)
                checksum = hashlib.sha256(content_str.encode()).hexdigest()[:16]
                configmaps_state[name] = {
                    "resource_version": rv,
                    "data_keys": data_keys,
                    "checksum": checksum,
                    "entry_count": len(data_keys),
                }
        except ApiException as api_err:
            if api_err.status == 403:
                raise K8sPermissionDeniedError(f"RBAC denied listing ConfigMaps in {self.namespace}: {api_err.reason}") from api_err
            raise K8sClusterUnreachableError(f"Failed to query ConfigMaps: {api_err.reason}") from api_err
        except Exception as exc:
            raise K8sClusterUnreachableError(f"Connection error querying ConfigMaps: {exc}") from exc

        # 3. Assess overall system health (ignoring terminating pods during graceful rollouts)
        all_healthy = True
        health_reasons = []
        active_pods = {k: v for k, v in pods_state.items() if not v.get("is_terminating")}
        if not active_pods:
            status_summary = "Empty namespace: 0 active pods running"
            all_healthy = False
        else:
            for pod_name, pinfo in active_pods.items():
                if pinfo["phase"] != "Running":
                    all_healthy = False
                    health_reasons.append(f"{pod_name} is {pinfo['phase']}")
                elif pinfo["ready_count"] < pinfo["total_containers"]:
                    all_healthy = False
                    r_str = ",".join(pinfo["reasons"]) if pinfo["reasons"] else "NotReady"
                    health_reasons.append(f"{pod_name} ({pinfo['ready']} ready, {r_str})")
                elif any(r in ["CrashLoopBackOff", "Error", "ImagePullBackOff", "RunContainerError"] for r in pinfo["reasons"]):
                    all_healthy = False
                    health_reasons.append(f"{pod_name} ({','.join(pinfo['reasons'])})")

            total_ready = sum(p["ready_count"] for p in active_pods.values())
            total_expected = sum(p["total_containers"] for p in active_pods.values())
            if all_healthy:
                status_summary = f"Running {total_ready}/{total_expected} (All {len(active_pods)} active pod(s) healthy)"
            else:
                status_summary = f"Degraded: {'; '.join(health_reasons[:2])}"

        raw_state = {
            "namespace": self.namespace,
            "pods": pods_state,
            "configmaps": configmaps_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return raw_state, all_healthy, status_summary

    def capture_snapshot(
        self,
        incident_id: str,
        event_id: str | None = None,
    ) -> StateSnapshot:
        """Captures a real infrastructure StateSnapshot from the active cluster."""
        raw_state, is_healthy, status_summary = self.capture_raw_state()
        snapshot = StateSnapshot(
            incident_id=incident_id,
            event_id=event_id,
            resource_type="k8s_cluster",
            raw_state=raw_state,
            status_summary=status_summary,
            is_healthy=is_healthy,
            timestamp=datetime.now(timezone.utc),
        )
        with self._poll_lock:
            self._latest_snapshot = snapshot
            self._snapshots.append(snapshot)
        return snapshot

    def start_polling(
        self,
        incident_id: str,
        on_snapshot: Callable[[StateSnapshot], None] | None = None,
    ) -> None:
        """Starts background periodic polling of target namespace resource state."""
        if self._polling:
            return

        self._polling = True

        def _worker():
            while self._polling:
                try:
                    snap = self.capture_snapshot(incident_id=incident_id)
                    if on_snapshot:
                        on_snapshot(snap)
                except Exception as poll_err:
                    logger.warning(f"K8s poll iteration warning: {poll_err}")
                time.sleep(self.poll_interval)

        self._poll_thread = threading.Thread(target=_worker, daemon=True, name="K8sStateCollectorThread")
        self._poll_thread.start()

    def stop_polling(self) -> StateSnapshot | None:
        """Stops background polling and returns the latest captured snapshot."""
        self._polling = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        with self._poll_lock:
            return self._latest_snapshot

    @staticmethod
    def compute_diff(
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[dict[str, Any], str, bool]:
        """Computes specific, fine-grained diff between before and after cluster snapshots.

        Returns:
            (detailed_diff_dict, formatted_diff_summary, is_meaningful_recovery)
        """
        diff_records: list[str] = []
        detailed: dict[str, Any] = {
            "configmap_changes": [],
            "pod_changes": [],
            "recovered_pods": [],
            "degraded_pods": [],
        }

        b_raw = before.raw_state or {}
        a_raw = after.raw_state or {}
        b_pods = b_raw.get("pods", {})
        a_pods = a_raw.get("pods", {})
        b_cms = b_raw.get("configmaps", {})
        a_cms = a_raw.get("configmaps", {})

        # 1. Detect ConfigMap modifications (resourceVersion, checksum, keys)
        for cm_name, a_cm in a_cms.items():
            if cm_name in b_cms:
                b_cm = b_cms[cm_name]
                if b_cm.get("resource_version") != a_cm.get("resource_version") or b_cm.get("checksum") != a_cm.get("checksum"):
                    cm_desc = (
                        f"ConfigMap \"{cm_name}\" resourceVersion updated "
                        f"({b_cm.get('resource_version')} -> {a_cm.get('resource_version')}, "
                        f"checksum {b_cm.get('checksum')} -> {a_cm.get('checksum')})"
                    )
                    diff_records.append(cm_desc)
                    detailed["configmap_changes"].append({
                        "name": cm_name,
                        "before_version": b_cm.get("resource_version"),
                        "after_version": a_cm.get("resource_version"),
                        "before_checksum": b_cm.get("checksum"),
                        "after_checksum": a_cm.get("checksum"),
                    })

        # 2. Detect Pod State & Container Transitions
        pod_names = sorted(set(b_pods.keys()).union(a_pods.keys()))
        for p_name in pod_names:
            b_p = b_pods.get(p_name)
            a_p = a_pods.get(p_name)

            if b_p and not a_p:
                if b_p.get("reasons"):
                    diff_records.append(f"Failed pod \"{p_name}\" ({','.join(b_p.get('reasons'))}) terminated")
                else:
                    diff_records.append(f"Pod \"{p_name}\" terminated")
                continue
            if not b_p and a_p:
                if a_p.get("phase") == "Running" and a_p.get("ready_count") == a_p.get("total_containers"):
                    diff_records.append(f"Healthy pod \"{p_name}\" spawned in phase Running ({a_p.get('ready')} ready)")
                    detailed["recovered_pods"].append(p_name)
                else:
                    diff_records.append(f"Pod \"{p_name}\" created in phase {a_p.get('phase')} [{a_p.get('ready')}]")
                continue

            # Both exist: check phase, ready, restarts, reasons
            b_phase = b_p.get("phase")
            a_phase = a_p.get("phase")
            b_ready = b_p.get("ready")
            a_ready = a_p.get("ready")
            b_restarts = b_p.get("restarts", 0)
            a_restarts = a_p.get("restarts", 0)
            b_reasons = b_p.get("reasons", [])
            a_reasons = a_p.get("reasons", [])

            # Restart count increase
            if a_restarts > b_restarts:
                diff_records.append(
                    f"Pod \"{p_name}\" restart count increased from {b_restarts} to {a_restarts}"
                )

            # CrashLoopBackOff -> Running recovery
            if "CrashLoopBackOff" in b_reasons and "CrashLoopBackOff" not in a_reasons and a_phase == "Running":
                diff_records.append(
                    f"Pod \"{p_name}\" recovered from CrashLoopBackOff ({b_ready}) to Running ({a_ready})"
                )
                detailed["recovered_pods"].append(p_name)
            elif b_phase != a_phase or b_ready != a_ready:
                diff_records.append(
                    f"Pod \"{p_name}\" transitioned from {b_phase} [{b_ready}] to {a_phase} [{a_ready}]"
                )

        # 3. Classify overall recovery vs degradation
        is_recovery = False
        if not before.is_healthy and after.is_healthy:
            is_recovery = True
            prefix = f"RECOVERY: State improved from unhealthy [{before.status_summary}] to healthy [{after.status_summary}]."
        elif before.is_healthy and not after.is_healthy:
            prefix = f"DEGRADATION: State degraded from healthy [{before.status_summary}] to unhealthy [{after.status_summary}]."
        elif diff_records:
            prefix = f"STATE_CHANGE: [{before.status_summary}] -> [{after.status_summary}]."
        else:
            prefix = f"UNCHANGED: [{after.status_summary}]."

        if diff_records:
            summary = f"{prefix} Details: {'; '.join(diff_records[:4])}"
        else:
            summary = prefix

        return detailed, summary, is_recovery

    def create_transition_snapshot(
        self,
        incident_id: str,
        before: StateSnapshot,
        after: StateSnapshot,
        event_id: str | None = None,
    ) -> StateSnapshot:
        """Creates a consolidated StateSnapshot holding before/after state and computed diff."""
        detailed, diff_summary, is_recovery = self.compute_diff(before, after)
        b_state = dict(before.raw_state) if before else {}
        if before and before.status_summary:
            b_state["summary"] = before.status_summary
        a_state = dict(after.raw_state) if after else {}
        if after and after.status_summary:
            a_state["summary"] = after.status_summary

        return StateSnapshot(
            incident_id=incident_id,
            event_id=event_id,
            resource_type="k8s_cluster",
            before_state=b_state,
            after_state=a_state,
            raw_state={
                "before": b_state,
                "after": a_state,
                "diff": detailed,
            },
            diff_summary=diff_summary,
            is_healthy=after.is_healthy,
            status_summary=after.status_summary,
            timestamp=datetime.now(timezone.utc),
        )


# Backward compatibility alias
K8sCollector = K8sStateCollector

