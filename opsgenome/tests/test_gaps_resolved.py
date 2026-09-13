"""Verification tests for the 5 Resolved Architectural Gaps in OpsGenome:

1. Multi-language & multi-frame call stack traceback extraction.
2. High-fidelity offline Kubernetes simulation engine (zero-Minikube guarantee).
3. Command runner (opsgenome run) with live stdout/stderr capture and auto-fix.
4. Groq LPU and Ollama local air-gapped AI provider integrations.
5. Deterministic offline code repairs with zero API calls and zero network.
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from opsgenome.ai.code_fixer import CodeFixEngine, FailureContext
from opsgenome.ai.engine import AIReasoningEngine
from opsgenome.watcher.k8s import K8sStateCollector
from opsgenome.watcher.k8s_sim import SimulatedK8sCollector


# =========================================================================
# GAP 1: MULTI-LANGUAGE & MULTI-FRAME TRACEBACK DIAGNOSIS
# =========================================================================

def test_multi_frame_python_call_stack_extraction(tmp_path):
    """Verifies extraction of entire project call stack in call order."""
    main_py = tmp_path / "main.py"
    main_py.write_text("from service import run\nrun()\n")
    service_py = tmp_path / "service.py"
    service_py.write_text("def run():\n    raise ValueError('fail')\n")

    error_output = f"""Traceback (most recent call last):
  File "{main_py}", line 2, in <module>
    run()
  File "{service_py}", line 2, in run
    raise ValueError('fail')
ValueError: fail
"""
    chain = CodeFixEngine.extract_traceback_chain(error_output, str(tmp_path))
    assert len(chain) == 2
    assert chain[0] == str(main_py.resolve())
    assert chain[1] == str(service_py.resolve())

    # The target file for remediation is the immediate failure site
    target = CodeFixEngine.extract_target_file(error_output, "python main.py", str(tmp_path))
    assert target == str(service_py.resolve())


def test_nodejs_and_shell_error_extraction(tmp_path):
    """Verifies traceback parsing for Node.js stack traces and Shell script errors."""
    app_js = tmp_path / "server.js"
    app_js.write_text("console.log('hi');")
    sh_script = tmp_path / "deploy.sh"
    sh_script.write_text("#!/bin/bash\necho test")

    node_trace = f"""Error: Connection refused
    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1146:16)
    at Object.<anonymous> ({app_js}:12:5)
"""
    chain = CodeFixEngine.extract_traceback_chain(node_trace, str(tmp_path))
    assert str(app_js.resolve()) in chain

    sh_err = f"{sh_script}: line 4: syntax error near unexpected token 'fi'"
    chain_sh = CodeFixEngine.extract_traceback_chain(sh_err, str(tmp_path))
    assert str(sh_script.resolve()) in chain_sh


# =========================================================================
# GAP 2: KUBERNETES SIMULATION ENGINE (ZERO-MINIKUBE GUARANTEE)
# =========================================================================

def test_simulated_k8s_collector_lifecycle():
    """Verifies offline simulated Kubernetes state collection, diffs, and remediation."""
    collector = SimulatedK8sCollector(namespace="payments")
    collector.connect()
    assert collector.is_connected

    health = collector.check_health()
    assert health["healthy"] is True
    assert health["simulated"] is True
    assert health["namespace"] == "payments"

    # Initial capture: pod is in CrashLoopBackOff (0/1 ready)
    raw_state_1, is_healthy_1, status_1 = collector.capture_raw_state()
    assert is_healthy_1 is False
    assert "0/1 pods healthy" in status_1
    assert "CrashLoopBackOff" in status_1

    snap1 = collector.capture_snapshot(incident_id="inc-sim-01")
    assert snap1.is_healthy is False
    assert snap1.raw_state["simulated"] is True

    # Simulate remediation: ConfigMap patched, pod transitions to 1/1 Ready
    collector.simulate_remediation(updated_checksum="sha256:valid_db_pool_c39e")
    raw_state_2, is_healthy_2, status_2 = collector.capture_raw_state()
    assert is_healthy_2 is True
    assert "1/1 pods healthy" in status_2

    # Snapshot 2 with before/after diff calculation
    snap2 = collector.capture_snapshot(
        incident_id="inc-sim-01",
        before_raw_state=snap1.raw_state,
    )
    assert snap2.is_healthy is True
    assert "Ready changed from False to True" in snap2.diff_summary
    assert "resourceVersion bumped" in snap2.diff_summary


def test_k8s_collector_simulation_fallback():
    """Verifies K8sStateCollector falls back seamlessly to simulation when enabled."""
    collector = K8sStateCollector(namespace="payments")
    collector.allow_simulation = True
    collector.connect()
    assert collector.is_simulated is True

    health = collector.check_health()
    assert health["healthy"] is True
    assert health["simulated"] is True

    raw, healthy, status = collector.capture_raw_state()
    assert raw["simulated"] is True


# =========================================================================
# GAP 3: COMMAND RUNNER (OPSGENOME RUN) TELEMETRY CAPTURE
# =========================================================================

def test_code_fixer_capture_failure_from_command(tmp_path):
    """Verifies CodeFixEngine captures stdout, stderr, and exit code directly from command."""
    broken_py = tmp_path / "crash.py"
    broken_py.write_text("import sys\nprint('starting up')\nsys.stderr.write('fatal crash\\n')\nsys.exit(42)\n")

    fixer = CodeFixEngine()
    failure = fixer.capture_failure(str(broken_py), cwd=str(tmp_path))

    assert failure.exit_code == 42
    assert "starting up" in failure.stdout
    assert "fatal crash" in failure.stderr
    assert failure.target_file == str(broken_py.resolve())


# =========================================================================
# GAP 4: GROQ LPU & OLLAMA PROVIDERS
# =========================================================================

def test_groq_and_ollama_provider_init():
    """Verifies AIReasoningEngine configuration for Groq and Ollama."""
    # Groq provider
    groq_engine = AIReasoningEngine(provider="groq", groq_api_key="gsk_test_key_123")
    assert groq_engine.provider == "groq"
    assert "llama-3.3-70b" in groq_engine.model
    assert groq_engine.groq_api_key == "gsk_test_key_123"

    # Ollama provider
    ollama_engine = AIReasoningEngine(provider="ollama", ollama_host="http://localhost:11434")
    assert ollama_engine.provider == "ollama"
    assert "deepseek" in ollama_engine.model
    assert ollama_engine.ollama_host == "http://localhost:11434"


def test_groq_code_fix_execution_mocked():
    """Verifies Groq code fix dispatcher calls OpenAI-compatible API endpoint."""
    groq_engine = AIReasoningEngine(provider="groq", groq_api_key="gsk_test")
    mock_resp = {
        "symptom": "Crash in service",
        "root_cause": "Typo in variable",
        "fixed_code": "x = 10\n",
        "explanation": "Fixed variable name",
        "diff_summary": "Renamed variable",
    }
    with patch.object(groq_engine, "_openai_compatible_call", return_value=mock_resp) as mock_call:
        res = groq_engine.diagnose_and_fix_code(
            filename="app.py",
            code_content="x = 1\n",
            command="python app.py",
            error_output="NameError: name 'x' is not defined",
            exit_code=1,
        )
        assert mock_call.called
        assert res["fixed_code"] == "x = 10\n"
        assert res["root_cause"] == "Typo in variable"


# =========================================================================
# GAP 5: DETERMINISTIC OFFLINE HEURISTIC REPAIRS (ZERO API TOKENS)
# =========================================================================

def test_offline_fix_index_error():
    """Verifies offline heuristic adds bounds checking to IndexError."""
    engine = AIReasoningEngine(provider="offline")
    code = "def get_item(items, i):\n    return items[i]\n"
    err = "IndexError: list index out of range"
    res = engine.diagnose_and_fix_code("handler.py", code, "python handler.py", err, 1)

    assert "len(items)" in res["fixed_code"]
    assert res["symptom"] == "IndexError: list index out of range"


def test_offline_fix_key_error():
    """Verifies offline heuristic replaces direct key lookup with .get()."""
    engine = AIReasoningEngine(provider="offline")
    code = "def read_cfg(cfg):\n    return cfg['db_host']\n"
    err = "KeyError: 'db_host'"
    res = engine.diagnose_and_fix_code("config.py", code, "python config.py", err, 1)

    assert "cfg.get('db_host')" in res["fixed_code"]
    assert "KeyError: 'db_host'" in res["symptom"]


def test_offline_fix_attribute_error_on_none():
    """Verifies offline heuristic guards NoneType attribute dereferencing."""
    engine = AIReasoningEngine(provider="offline")
    code = "def process(user):\n    return user.email\n"
    err = "AttributeError: 'NoneType' object has no attribute 'email'"
    res = engine.diagnose_and_fix_code("user.py", code, "python user.py", err, 1)

    assert "user.email if user is not None else None" in res["fixed_code"]


def test_offline_fix_name_error_missing_import():
    """Verifies offline heuristic prepends standard library imports."""
    engine = AIReasoningEngine(provider="offline")
    code = "def get_pid():\n    return os.getpid()\n"
    err = "NameError: name 'os' is not defined"
    res = engine.diagnose_and_fix_code("worker.py", code, "python worker.py", err, 1)

    assert "import os\n" in res["fixed_code"]


def test_offline_fix_syntax_error_missing_colon():
    """Verifies offline heuristic appends missing colons in block headers."""
    engine = AIReasoningEngine(provider="offline")
    code = "def calculate_total(items)\n    return sum(items)\n"
    err = "SyntaxError: expected ':'"
    res = engine.diagnose_and_fix_code("math_ops.py", code, "python math_ops.py", err, 1)

    assert "def calculate_total(items):" in res["fixed_code"]
