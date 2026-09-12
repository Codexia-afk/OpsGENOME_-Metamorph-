"""Unit and Integration Tests for Error Dictionary and Diagnostic Healthcheck.

Verifies:
1. All custom exception classes documented in README.md exist and are importable.
2. K8sStateCollector.check_health() safely returns diagnostic dict without unhandled exceptions.
3. K8sCollector backward compatibility alias functions properly.
4. opsgenome doctor CLI command executes successfully and outputs subsystem health table.
5. README.md exists and contains exhaustive diagnostic references.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from click.testing import CliRunner

from opsgenome.cli.main import cli
from opsgenome.security.redactor import SecurityBoundaryViolation
from opsgenome.watcher.k8s import (
    K8sCollector,
    K8sCollectorError,
    K8sClusterUnreachableError,
    K8sNamespaceNotFoundError,
    K8sPermissionDeniedError,
    K8sStateCollector,
)


def test_custom_exception_hierarchy():
    """Verify all documented exception classes exist and have proper inheritance."""
    assert issubclass(K8sClusterUnreachableError, K8sCollectorError)
    assert issubclass(K8sNamespaceNotFoundError, K8sCollectorError)
    assert issubclass(K8sPermissionDeniedError, K8sCollectorError)
    assert issubclass(SecurityBoundaryViolation, Exception)

    # Verify instantiation
    err1 = K8sClusterUnreachableError("Cluster down")
    assert "Cluster down" in str(err1)
    err2 = SecurityBoundaryViolation("Secret leak detected")
    assert "Secret leak" in str(err2)


def test_k8s_collector_alias():
    """Verify backward compatibility alias K8sCollector points to K8sStateCollector."""
    assert K8sCollector is K8sStateCollector
    collector = K8sCollector(namespace="test-ns")
    assert isinstance(collector, K8sStateCollector)
    assert collector.namespace == "test-ns"


def test_k8s_collector_check_health_safely_handles_unreachable():
    """Verify check_health() returns structured diagnostic dict instead of uncaught exception."""
    collector = K8sCollector(namespace="nonexistent-namespace", kubeconfig_path="/tmp/nonexistent-kubeconfig")
    health = collector.check_health()
    assert isinstance(health, dict)
    assert "healthy" in health
    assert "namespace" in health
    assert "error" in health
    # Invalid kubeconfig should be flagged as unhealthy with diagnostic error string
    assert health["healthy"] is False
    assert health["error"] is not None


def test_doctor_cli_command_runner():
    """Verify opsgenome doctor executes cleanly via Click CliRunner."""
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    # Must display diagnostic table headers
    assert "OpsGenome Doctor" in result.output
    assert "IPC Socket" in result.output
    assert "SQLite Storage" in result.output
    assert "Kubernetes Collector" in result.output
    assert "Shell Hooks" in result.output
    assert "AI Engine" in result.output
    assert "README.md" in result.output


def test_troubleshooting_documentation_integrity():
    """Verify README.md exists and contains all required error domains."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    readme_file = repo_root / "README.md"
    assert readme_file.exists(), "README.md must exist at repo root"

    content = readme_file.read_text()
    assert "Master Error & Exception Matrix" in content
    assert "Domain 1: Kubernetes Watcher & Cluster State Collector" in content
    assert "Domain 2: Security Boundary & Secret Redaction Guardrails" in content
    assert "Domain 3: Unix Domain Socket IPC & Client Transport" in content
    assert "Domain 4: AI Reasoning Engine & Grounding Gate" in content
    assert "Domain 5: SQLite Database & Storage Engine" in content
    assert "Domain 6: Shell Integration Hooks & Anomaly Detector" in content
    assert "opsgenome doctor" in content
