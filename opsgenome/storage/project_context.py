"""Automatic Project Context & Technology Stack Detector for OpsGenome.

Derives a stable, non-sensitive identifier for the active project and
detects the operational technology stack without leaking local user directories.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def _clean_identifier(name: str) -> str:
    """Normalize project identifier to safe alphanumeric, dashes, and underscores."""
    cleaned = re.sub(r"[^\w\-.]", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned.lower() if cleaned else "default_project"


def detect_project(cwd: str | Path | None = None) -> str:
    """Derive a stable project identifier.

    Priority:
    1. OPSGENOME_PROJECT environment variable override.
    2. Git remote origin URL repository name (e.g. 'payments-service').
    3. Git repository root directory name (e.g. 'OPsGenome').
    4. Base directory name of cwd.
    5. Fallback: 'default_project'.
    """
    # 1. Environment Variable Override
    env_override = os.environ.get("OPSGENOME_PROJECT", "").strip()
    if env_override:
        return _clean_identifier(env_override)

    target_dir = str(cwd) if cwd else os.getcwd()
    target_path = Path(target_dir).resolve()

    # Check if within distinct subproject / monorepo package (e.g. demo-projects, services)
    for p in [target_path] + list(target_path.parents):
        if p.parent and p.parent.name in ("demo-projects", "services", "microservices", "apps"):
            return _clean_identifier(p.name)

    # 2. Git Remote Origin URL
    try:
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=target_dir,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        ).strip()
        if remote_url:
            # Handle both https://... and git@... formats
            repo_part = remote_url.split("/")[-1].replace(".git", "")
            if ":" in repo_part:
                repo_part = repo_part.split(":")[-1]
            if repo_part:
                return _clean_identifier(repo_part)
    except Exception:
        pass

    # 3. Git Root Directory Name
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=target_dir,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        ).strip()
        if git_root:
            return _clean_identifier(Path(git_root).name)
    except Exception:
        pass

    # 4. Current Directory Basename
    try:
        dirname = Path(target_dir).resolve().name
        if dirname and dirname not in {"/", "."}:
            return _clean_identifier(dirname)
    except Exception:
        pass

    return "default_project"


def detect_stack(command_or_text: str = "", cwd: str | Path | None = None) -> str:
    """Lightweight, best-effort technology stack detector.

    Honest classification derived from active operational command binaries
    and filesystem indicators.
    """
    text_lower = (command_or_text or "").lower()

    # Tool binary heuristics
    if any(k in text_lower for k in ["kubectl", "minikube", "helm", "k8s", "crictl", "kubeadm"]):
        return "kubernetes"
    if any(k in text_lower for k in ["terraform", "terragrunt", "tofu", "pulumi"]):
        return "iac_terraform"
    if any(k in text_lower for k in ["docker", "podman", "docker-compose", "nerdctl"]):
        return "docker_containers"
    if any(k in text_lower for k in ["psql", "pg_dump", "mysql", "postgres", "redis-cli", "mongosh", "sqlite3"]):
        return "database"
    if any(k in text_lower for k in ["aws ", "gcloud", "az ", "s3cmd"]):
        return "cloud_cli"
    if any(k in text_lower for k in ["pytest", "python", "pip ", "poetry", "node ", "npm ", "cargo", "go "]):
        return "app_runtime"

    # Filesystem indicators if cwd provided
    if cwd:
        try:
            p = Path(cwd)
            if (p / "Dockerfile").exists() or (p / "docker-compose.yml").exists():
                return "docker_containers"
            if any(p.glob("*.tf")):
                return "iac_terraform"
            if (p / "k8s").exists() or (p / "manifests").exists():
                return "kubernetes"
        except Exception:
            pass

    return "general"
