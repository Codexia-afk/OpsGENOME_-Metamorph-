"""Simulated Kubernetes Collector Engine for OpsGenome.

Provides high-fidelity offline simulation of Kubernetes cluster states (CrashLoopBackOff,
pod container readiness transitions 0/1 -> 1/1, and ConfigMap resourceVersion checksums).
Used during demos, tests, and air-gapped environments when a live Minikube/Kind cluster
is not active.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any

from opsgenome.storage.models import StateSnapshot


class SimulatedK8sCollector:
    """High-fidelity offline simulated Kubernetes state collector."""

    def __init__(self, namespace: str = "payments"):
        self.namespace = namespace
        self.is_connected = False
        self._resource_version = 10452
        self._configmap_checksum = "sha256:bad_db_connection_string_a9f1"
        self._pod_restarts = 4
        self._pod_ready = False
        self._pod_phase = "Running"
        self._waiting_reason = "CrashLoopBackOff"
        self._waiting_message = "Back-off 5m0s restarting failed container=payment-worker"

    def connect(self) -> None:
        """Simulates successful connection to Kubernetes API."""
        self.is_connected = True

    def check_health(self) -> dict[str, Any]:
        """Returns healthy status indicating simulated cluster engine is ready."""
        return {
            "healthy": True,
            "namespace": self.namespace,
            "simulated": True,
            "cluster_version": "v1.28.2-simulated",
            "error": None,
        }

    def simulate_failure(self, reason: str = "CrashLoopBackOff") -> None:
        """Sets simulated pod state to unhealthy/crashing."""
        self._pod_ready = False
        self._pod_restarts += 1
        self._waiting_reason = reason
        self._waiting_message = f"Container failed: {reason}"

    def simulate_remediation(self, updated_checksum: str = "sha256:valid_db_pool_c39e") -> None:
        """Simulates applying a ConfigMap patch and pod recovery to 1/1 Ready."""
        self._resource_version += 1
        self._configmap_checksum = updated_checksum
        self._pod_ready = True
        self._waiting_reason = None
        self._waiting_message = None

    def capture_raw_state(self) -> tuple[dict[str, Any], bool, str]:
        """Simulates raw K8s API polling for pods and configmaps."""
        pod_name = f"{self.namespace}-service-7b5c89df9-w4x2z"
        pods = {
            pod_name: {
                "phase": self._pod_phase,
                "ready": self._pod_ready,
                "restarts": self._pod_restarts,
                "container_count": 1,
                "ready_count": 1 if self._pod_ready else 0,
                "waiting_reason": self._waiting_reason,
                "waiting_message": self._waiting_message,
            }
        }
        configmaps = {
            f"{self.namespace}-config": {
                "resource_version": str(self._resource_version),
                "checksum": self._configmap_checksum,
                "data_keys": ["DATABASE_URL", "POOL_SIZE", "TIMEOUT_MS"],
            }
        }
        all_ready = self._pod_ready
        status = (
            f"Namespace '{self.namespace}': 1/1 pods healthy, all containers Ready"
            if all_ready
            else f"Namespace '{self.namespace}': 0/1 pods healthy, pod '{pod_name}' in {self._waiting_reason}"
        )
        return {"pods": pods, "configmaps": configmaps, "simulated": True}, all_ready, status

    def capture_snapshot(
        self,
        incident_id: str,
        event_id: str | None = None,
        before_raw_state: dict[str, Any] | None = None,
    ) -> StateSnapshot:
        """Produces a validated Pydantic StateSnapshot with state diffs."""
        raw_state, is_healthy, status = self.capture_raw_state()
        before = before_raw_state or {}

        # Compute diff if before state exists
        diff_lines = []
        if before:
            b_pods = before.get("pods", {})
            a_pods = raw_state.get("pods", {})
            for name, a_info in a_pods.items():
                if name in b_pods:
                    b_info = b_pods[name]
                    if b_info.get("ready") != a_info.get("ready"):
                        diff_lines.append(
                            f"Pod {name}: Ready changed from {b_info.get('ready')} to {a_info.get('ready')}"
                        )
                    if b_info.get("waiting_reason") != a_info.get("waiting_reason"):
                        diff_lines.append(
                            f"Pod {name}: Reason changed from '{b_info.get('waiting_reason')}' to '{a_info.get('waiting_reason')}'"
                        )
            b_cm = before.get("configmaps", {})
            a_cm = raw_state.get("configmaps", {})
            for name, a_info in a_cm.items():
                if name in b_cm:
                    b_info = b_cm[name]
                    if b_info.get("resource_version") != a_info.get("resource_version"):
                        diff_lines.append(
                            f"ConfigMap {name}: resourceVersion bumped {b_info.get('resource_version')} -> {a_info.get('resource_version')}"
                        )

        diff_summary = "\n".join(diff_lines) if diff_lines else "Initial baseline snapshot captured (simulated)."

        return StateSnapshot(
            id=str(uuid.uuid4())[:8],
            incident_id=incident_id,
            event_id=event_id,
            resource_type="k8s_pod",
            before_state=before,
            after_state=raw_state,
            raw_state=raw_state,
            diff_summary=diff_summary,
            is_healthy=is_healthy,
            status_summary=status,
            timestamp=datetime.now(timezone.utc),
        )
