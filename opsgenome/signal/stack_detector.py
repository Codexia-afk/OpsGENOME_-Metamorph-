"""Command Prefix to Technology Stack and Target Tool Mapping."""

from __future__ import annotations

import shlex

# Structured prefix mapping: Adding a new mapping is a single tuple entry!
PREFIX_TO_STACK: list[tuple[tuple[str, ...], str]] = [
    (("python3", "python", "pytest", "py.test"), "python"),
    (("java", "javac", "mvn", "mvnw", "gradle", "gradlew"), "java"),
    (("node", "npm", "npx", "yarn", "pnpm", "bun"), "javascript"),
    (("terraform", "tofu", "terragrunt"), "terraform"),
    (("go run", "go test", "go"), "go"),
    (("cargo", "rustc"), "rust"),
    (("kubectl", "helm", "k8s", "crictl", "minikube"), "kubernetes"),
    (("docker", "docker-compose", "podman", "nerdctl"), "docker"),
]

# Widened tool coverage for opsgenome run
TARGET_TOOLS: list[str] = [
    "kubectl", "k", "helm", "crictl",
    "python3", "python", "pytest",
    "java", "javac", "mvn",
    "node", "npm", "npx",
    "terraform", "tofu",
    "go",
    "cargo",
    "docker",
]


def detect_stack_from_command(command: str) -> str:
    """Detects technology stack from command prefix.

    Returns the canonical stack name (python, java, javascript, terraform, go, rust, kubernetes, docker)
    or 'general' if unmapped.
    """
    if not command:
        return "general"

    cmd_stripped = command.strip()

    # Check multi-word prefixes first (e.g. "go run", "java -jar")
    cmd_lower = cmd_stripped.lower()
    for prefixes, stack in PREFIX_TO_STACK:
        for prefix in prefixes:
            if " " in prefix:
                if cmd_lower == prefix or cmd_lower.startswith(prefix + " "):
                    return stack

    # Check single-word binary prefix
    try:
        tokens = shlex.split(cmd_stripped)
    except Exception:
        tokens = cmd_stripped.split()

    if not tokens:
        return "general"

    first_bin = tokens[0].lower().split("/")[-1]  # handle /usr/bin/python3

    for prefixes, stack in PREFIX_TO_STACK:
        for prefix in prefixes:
            if " " not in prefix and first_bin == prefix:
                return stack

    return "general"


def is_target_tool(command: str) -> bool:
    """Check if command invokes one of the monitored target tools."""
    if not command:
        return False
    cmd_stripped = command.strip()
    try:
        tokens = shlex.split(cmd_stripped)
    except Exception:
        tokens = cmd_stripped.split()
    if not tokens:
        return False
    first_bin = tokens[0].lower().split("/")[-1]
    return first_bin in TARGET_TOOLS
