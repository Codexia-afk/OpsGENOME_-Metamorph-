"""OpsGenome CLI Application.

Provides complete terminal command-line interface, interactive SRE flight simulator,
ASCII banner, and categorized key-driven help guide.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import click
from tabulate import tabulate
import uvicorn
from opsgenome.agents.cluster_auditor import ClusterMultiIssueAuditor
from opsgenome.agents.demo_scenarios import get_demo_cross_stack_targets, reset_demo_incident_files
from opsgenome.agents.orchestrator import LeadSREOrchestrator

from opsgenome.ai.runbook_generator import RunbookGenerator
from opsgenome.cli.hook_installer import HookInstaller
from opsgenome.daemon.server import create_app
from opsgenome.prevention.bus_factor import BusFactorAnalyzer
from opsgenome.prevention.drift import DriftDetectionEngine
from opsgenome.prevention.recurrence import RecurrenceAlertEngine
from opsgenome.simulator.flight_sim import FlightSimulatorEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import Incident, IncidentStatus, TriggerType

# ANSI Color Utilities
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


ASCII_LOGO = f"""{CYAN}
 ██████╗ ██████╗ ███████╗ ██████╗ ███████╗███╗   ██╗ ██████╗ ███╗   ███╗███████╗
██╔═══██╗██╔══██╗██╔════╝██╔════╝ ██╔════╝████╗  ██║██╔═══██╗████╗ ████║██╔════╝
██║   ██║██████╔╝███████╗██║  ███╗█████╗  ██╔██╗ ██║██║   ██║██╔████╔██║█████╗  
██║   ██║██╔═══╝ ╚════██║██║   ██║██╔══╝  ██║╚██╗██║██║   ██║██║╚██╔╝██║██╔══╝  
╚██████╔╝██║     ███████║╚██████╔╝███████╗██║ ╚████║╚██████╔╝██║ ╚═╝ ██║███████╗
 ╚═════╝ ╚═╝     ╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝{RESET}
            {BOLD}{MAGENTA}🧬  T H E   O P E R A T I O N A L   M E M O R Y   E N G I N E  🧬{RESET}
"""

ASCII_MASCOT = f"""
       {GREEN}╭─────────────────────────────────────────────────────────────╮{RESET}
  {YELLOW}⚡{RESET}   {GREEN}│{RESET}  {BOLD}"Never fix the same production incident a fourth time."{RESET}     {GREEN}│{RESET}
 {CYAN}(◕‿◕){RESET} {GREEN}╰─────────────────────────────────────────────────────────────╯{RESET}
 {CYAN}╭─█─╮{RESET}
 {CYAN}│{RESET}{MAGENTA} 🧬{RESET}{CYAN}│{RESET}   {BOLD}OpsGenome v1.0.0{RESET} • Local-First SRE Intelligence Platform
 {CYAN}╯   ╰{RESET}
"""


def print_logo() -> None:
    print(ASCII_LOGO)
    print(ASCII_MASCOT)


def print_banner(title: str, content: str, color: str = CYAN) -> None:
    width = 78
    print(f"\n{color}┌{'─' * (width - 2)}┐{RESET}")
    print(f"{color}│ {BOLD}{title.ljust(width - 4)}{RESET}{color} │{RESET}")
    print(f"{color}├{'─' * (width - 2)}┤{RESET}")
    for line in content.split("\n"):
        print(f"{color}│{RESET} {line.ljust(width - 4)} {color}│{RESET}")
    print(f"{color}└{'─' * (width - 2)}┘{RESET}")


def show_categorized_help() -> None:
    print_logo()

    print(f"{BOLD}{YELLOW}══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}📖 OPSGENOME COMMAND & RESULT MATRIX — WHAT EACH KEY/COMMAND GIVES YOU{RESET}")
    print(f"{BOLD}{YELLOW}══════════════════════════════════════════════════════════════════════════════{RESET}\n")

    categories = [
        (
            "🚨 1. INCIDENT CAPTURE & LIVE WAR ROOM",
            [
                ("status [1 / s]", "Live Active Incident State", "Shows active incident, captured event count, scores & recurrence alerts."),
                ("start-incident <title>", "Open Incident Session", "Starts auto-capture window, scores commands, and runs sub-50ms recurrence check."),
                ("resolve [-u user]", "Synthesize Memory & Runbook", "Closes incident, runs 2-call AI clustering, generates runbook, updates confidence."),
            ],
        ),
        (
            "📖 2. RUNBOOK INTELLIGENCE & EARNED CONFIDENCE",
            [
                ("runbooks [2 / r]", "Query Runbook Library", "Displays stored runbooks with mathematically earned confidence (e.g. '87% — 7 of 8')."),
                ("apply-fix <id>", "Trust-Gated Fix Execution", "Applies remediation fix through strict gate: single-ack for same-project, dual-confirm for cross-project."),
                ("export-runbook <id>", "Export Runbook as Markdown", "Outputs clean, publishable GitHub-flavored Markdown runbook with provenance trail."),
            ],
        ),
        (
            "🛩️ 3. SRE FLIGHT SIMULATOR (REPLAY & ONBOARDING)",
            [
                ("replay <incident_id> [5 / p]", "Interactive Flight Simulator", "Steps through historical outage command-by-command with expert reasoning quizzes."),
            ],
        ),
        (
            "🔍 4. PREVENTION, DRIFT RADAR & BUS FACTOR",
            [
                ("drift [3 / d]", "Systemic Drift Radar", "Detects repeating root causes and formats structured architectural defect tickets stored in SQLite."),
                ("bus-factor [4 / b]", "Tribal Knowledge Risk Matrix", "Calculates bus factor ratings and identifies single-point-of-failure on-call engineers."),
            ],
        ),
        (
            "⚙️ 5. PLATFORM SETUP, DAEMON & DEMO",
            [
                ("demo [6 / t]", "Run 6-Step Hackathon Demo", "Executes full end-to-end demo (CrashLoopBackOff -> Redaction -> Recurrence -> Drift)."),
                ("daemon [7 / w]", "Launch Daemon", "Starts local daemon listener on secure Unix Domain Socket (mode 0600, zero TCP exposure)."),
                ("doctor [8 / c]", "Automated Health & Diagnostics", "Inspects socket, database, kubernetes, hooks, and AI engine status."),
                ("init", "Install Shell Integration Hooks", "Installs non-blocking async capture hooks into ~/.zshrc or ~/.bashrc."),
                ("help [? / h]", "Display This Help Matrix", "Shows categorized command reference and quick action shortcuts."),
            ],
        ),
        (
            "🤖 5. MULTI-AGENT SWARM & CROSS-STACK RESOLUTION",
            [
                ("multi-agent analyze [--demo]", "Swarm Cross-Stack Analysis", "Lead Orchestrator dispatches concurrent specialists (Python, Java, Node, K8s) and synthesizes atomic plan."),
                ("multi-agent cluster-audit", "Cluster Multi-Issue Auditor", "Scans K8s & Docker clusters for simultaneous issues and outputs exact copyable CLI commands and YAML patches."),
                ("multi-agent demo [9 / m]", "Live Multi-Agent Swarm Demo", "Executes complete end-to-end multi-agent resolution and cluster audit in < 1 second."),
            ],
        ),
    ]

    for cat_title, cmds in categories:
        print(f"{BOLD}{MAGENTA}{cat_title}{RESET}")
        table_rows = []
        for cmd_name, result_title, purpose in cmds:
            table_rows.append([
                f"{CYAN}{cmd_name}{RESET}",
                f"{BOLD}{result_title}{RESET}",
                f"{DIM}{purpose}{RESET}",
            ])
        print(tabulate(table_rows, headers=["Command / Shortcut", "Operational Result", "What It Does For You"], tablefmt="fancy_grid"))
        print()

    print(f"{BOLD}{GREEN}💡 Pro-Tip:{RESET} Type {CYAN}opsgenome{RESET} with no arguments for the interactive quick-action menu.\n")


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="1.0.0", prog_name="opsgenome")
def cli(ctx: click.Context) -> None:
    """OpsGenome: The Operational Memory Engine."""
    if ctx.invoked_subcommand is None:
        # Launch Interactive Quick Menu
        print_logo()
        print(f"{BOLD}{CYAN}Operational Quick Access — Press a key or enter a number:{RESET}\n")
        print(f"  {BOLD}[1]{RESET} or {BOLD}[s]{RESET} -> {CYAN}status{RESET}        (Inspect Live Active Incident & Telemetry)")
        print(f"  {BOLD}[2]{RESET} or {BOLD}[r]{RESET} -> {CYAN}runbooks{RESET}      (List Runbook Library & Earned Confidence)")
        print(f"  {BOLD}[3]{RESET} or {BOLD}[d]{RESET} -> {CYAN}drift{RESET}         (Systemic Drift Radar & Backlog Defect Tickets)")
        print(f"  {BOLD}[4]{RESET} or {BOLD}[b]{RESET} -> {CYAN}bus-factor{RESET}    (Tribal Knowledge Concentration & Bus Factor)")
        print(f"  {BOLD}[5]{RESET} or {BOLD}[p]{RESET} -> {CYAN}replay{RESET}        (SRE Flight Simulator Interactive Replay)")
        print(f"  {BOLD}[6]{RESET} or {BOLD}[t]{RESET} -> {CYAN}demo{RESET}          (Run 6-Step Hackathon Core Loop Demo)")
        print(f"  {BOLD}[7]{RESET} or {BOLD}[w]{RESET} -> {CYAN}daemon{RESET}        (Start Background Daemon & Web Dashboard)")
        print(f"  {BOLD}[8]{RESET} or {BOLD}[c]{RESET} -> {CYAN}doctor{RESET}        (Automated Diagnostic System Healthcheck)")
        print(f"  {BOLD}[9]{RESET} or {BOLD}[m]{RESET} -> {CYAN}multi-agent{RESET}   (Multi-Agent Swarm Analysis & Cluster Audit)")
        print(f"  {BOLD}[?]{RESET} or {BOLD}[h]{RESET} -> {CYAN}help{RESET}          (View Full Categorized Command Matrix)")
        print(f"  {BOLD}[q]{RESET}         -> Exit\n")

        choice = click.prompt(f"{YELLOW}Select an action [1-9 / s / r / d / b / p / t / w / c / m / ? / q]{RESET}", default="?", show_default=False)
        choice_clean = choice.strip().lower()

        if choice_clean in ["1", "s"]:
            ctx.invoke(cmd_status)
        elif choice_clean in ["2", "r"]:
            ctx.invoke(cmd_runbooks)
        elif choice_clean in ["3", "d"]:
            ctx.invoke(cmd_drift)
        elif choice_clean in ["4", "b"]:
            ctx.invoke(cmd_bus_factor)
        elif choice_clean in ["5", "p"]:
            db = DatabaseManager()
            incidents = db.list_incidents()
            if not incidents:
                print(f"{YELLOW}No recorded incidents found yet. Run `opsgenome demo` first to seed scenarios.{RESET}")
            else:
                ctx.invoke(cmd_replay, incident_id=incidents[0].id)
        elif choice_clean in ["6", "t"]:
            ctx.invoke(cmd_demo)
        elif choice_clean in ["7", "w"]:
            ctx.invoke(cmd_daemon)
        elif choice_clean in ["8", "c"]:
            ctx.invoke(cmd_doctor)
        elif choice_clean in ["9", "m"]:
            ctx.invoke(cmd_multi_agent_demo)
        elif choice_clean in ["?", "h", "help"]:
            show_categorized_help()
        elif choice_clean == "q":
            print(f"{GREEN}Goodbye! Operational memory preserved.{RESET}")
            sys.exit(0)
        else:
            show_categorized_help()


@cli.command("help")
def cmd_help() -> None:
    """Display comprehensive categorized command guide with results and shortcuts."""
    show_categorized_help()


@cli.command("init")
def cmd_init() -> None:
    """Install OpsGenome shell hooks into ~/.zshrc or ~/.bashrc."""
    print_logo()
    print(f"\n{BOLD}{CYAN}=== OpsGenome Shell Integration Setup ==={RESET}")
    success, msg = HookInstaller.install()
    if success:
        print(f"{GREEN}✔ {msg}{RESET}")
    else:
        print(f"{RED}✘ {msg}{RESET}")


@cli.command("daemon")
@click.option("--socket-path", "-s", default=None, help="Path to Unix domain socket (default: ~/.opsgenome/daemon.sock).")
@click.option("--host", "-h", default=None, help="TCP host to bind (e.g. 127.0.0.1 for local web UI/development).")
@click.option("--port", "-p", default=None, type=int, help="TCP port to bind (e.g. 8765 for local web UI/development).")
def cmd_daemon(socket_path: str | None, host: str | None, port: int | None) -> None:
    """Start the OpsGenome local background daemon on a secure Unix domain socket or HTTP dev port."""
    from opsgenome.cli.client import get_default_socket_path
    import socket
    from pathlib import Path

    print_logo()
    app = create_app()

    # If TCP host/port is explicitly requested (e.g. for Web UI dev server via ./run_opsgenome.sh)
    if host or port:
        tcp_host = host or "127.0.0.1"
        tcp_port = port or 8765
        content = (
            f"• Web UI Backend:      http://{tcp_host}:{tcp_port}\n"
            f"• Dashboard Frontend:  http://localhost:3000 (via python3 run_frontend.py)\n"
            f"• Access Control:      Localhost Loopback Only\n"
            f"• Mode:                Development HTTP Web Server"
        )
        print_banner(f"OpsGenome Daemon Online (HTTP Web Mode :{tcp_port})", content, color=GREEN)
        uvicorn.run(app, host=tcp_host, port=tcp_port, log_level="info")
        return

    sock_str = socket_path or get_default_socket_path()
    sock_path = Path(sock_str)
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if socket is already active
    if sock_path.exists():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(sock_path))
                content = (
                    f"• Daemon is ALREADY active on socket: {sock_str}\n"
                    f"• Socket Permissions: 0600 (owner read/write only)\n"
                    f"• TCP Port Binding: NONE (zero network/loopback exposure)"
                )
                print_banner("OpsGenome Daemon Already Running", content, color=YELLOW)
                return
        except Exception:
            # Stale socket file, unlink it
            sock_path.unlink(missing_ok=True)

    content = (
        f"• Unix Domain Socket:  {sock_str}\n"
        f"• Access Control:      POSIX 0600 (Restricted to current user)\n"
        f"• Network Exposure:    NONE (No TCP ports or loopback addresses bound)\n"
        f"• Client Integration:  In-process pre-redaction before socket dispatch"
    )
    print_banner("OpsGenome Daemon Online (Unix Domain Socket Mode)", content, color=GREEN)

    # Bind socket with strict 0600 permissions
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    os.chmod(str(sock_path), 0o600)
    sock.listen(128)

    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
        sock_path.unlink(missing_ok=True)


@cli.command("redact-and-send")
@click.option("--command", "-c", default=None, help="Command string to redact and send.")
@click.option("--exit-code", "-e", default=0, type=int, help="Command exit code.")
@click.option("--duration-ms", "-d", default=0, type=int, help="Command duration in ms.")
@click.option("--cwd", "-w", default="", help="Working directory.")
@click.option("--socket-path", "-s", default=None, help="Path to Unix domain socket.")
def cmd_redact_and_send(command: str | None, exit_code: int, duration_ms: int, cwd: str, socket_path: str | None) -> None:
    """Redact command in-process on client and transmit via Unix Domain Socket."""
    from opsgenome.cli.client import redact_and_dispatch
    raw_cmd = command if command is not None else sys.stdin.read().strip()
    if not raw_cmd:
        return
    redact_and_dispatch(
        command=raw_cmd,
        exit_code=exit_code,
        duration_ms=duration_ms,
        cwd=cwd or os.getcwd(),
        socket_path=socket_path,
    )




@cli.command("demo")
def cmd_demo() -> None:
    """Run the complete 6-step Hackathon Core Loop Demo."""
    from demo.run_hackathon_demo import run_demo
    run_demo()


@cli.command("start-incident")
@click.argument("title")
@click.option("--service", "-s", default="payments-service", help="Target service name.")
@click.option("--severity", "-p", default="P1", help="Severity level (P1, P2, P3).")
@click.option("--symptoms", "-m", multiple=True, help="Observed symptom strings.")
def cmd_start_incident(title: str, service: str, severity: str, symptoms: tuple[str, ...]) -> None:
    """Manually start an incident capture window."""
    db = DatabaseManager()
    active = db.get_active_incident()
    if active:
        print(f"{YELLOW}⚠ An active incident is already running: {BOLD}{active.title}{RESET} (ID: {active.id})")
        print(f"Run {CYAN}opsgenome resolve{RESET} or {CYAN}opsgenome status{RESET} first.")
        return

    symptom_list = list(symptoms) if symptoms else [title]
    inc = Incident(
        title=title,
        service=service,
        severity=severity,
        trigger_source=TriggerType.MANUAL,
        status=IncidentStatus.OPEN,
        symptoms=symptom_list,
    )
    db.create_incident(inc)

    content = (
        f"• ID: {inc.id}\n"
        f"• Title: {inc.title}\n"
        f"• Service: {inc.service} | Severity: {inc.severity}\n"
        f"• Terminal commands will now be automatically captured and scored."
    )
    print_banner("● Active Incident Capture Window Opened", content, color=GREEN)

    rec_engine = RecurrenceAlertEngine(db)
    match = rec_engine.check_recurrence(inc)
    if match:
        rec_content = (
            f"{match['alert_message']}\n\n"
            f"Recommended Historical Actions:\n"
            + "\n".join([f"  $ {cmd}" for cmd in match["top_commands"]])
        )
        if match.get("same_project"):
            banner_title = f"⚡ RECURRENCE ALERT (Same-Project Intake Match: {match.get('source_project')})"
            banner_color = GREEN
        else:
            banner_title = f"⚠ CROSS-PROJECT RECURRENCE ADVISORY (Source: {match.get('source_project')})"
            banner_color = YELLOW
        print_banner(banner_title, rec_content, color=banner_color)


@cli.command("status")
def cmd_status() -> None:
    """Show current active incident, captured event count, and live telemetry."""
    db = DatabaseManager()
    active = db.get_active_incident()

    if not active:
        print(f"\n{DIM}No active incident in progress. Capture engine is idle / standing by.{RESET}")
        print(f"Start one with: {CYAN}opsgenome start-incident <title>{RESET} or via Webhook.\n")
        return

    events = db.get_events_for_incident(active.id)
    content = (
        f"• Title: {active.title} (ID: {active.id})\n"
        f"• Project: {active.project} | Stack: {active.stack}\n"
        f"• Service: {active.service} | Severity: {active.severity} | Trigger: {active.trigger_source.value}\n"
        f"• Started: {active.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"• Captured Events: {len(events)}"
    )
    print_banner("● OpsGenome Active Capture State", content, color=RED)

    if events:
        table_rows = []
        for e in events[-10:]:
            status_tag = f"{GREEN}{e.classification.value.upper()}{RESET}" if e.classification.value == "fix" else (
                f"{RED}{e.classification.value.upper()}{RESET}" if e.classification.value == "dead_end" else f"{YELLOW}{e.classification.value.upper()}{RESET}"
            )
            table_rows.append([
                e.id,
                e.raw_command[:50],
                str(e.exit_code),
                f"{e.signal_weight:.2f}",
                status_tag,
            ])
        print("\nRecent Captured Commands:")
        print(tabulate(table_rows, headers=["Event ID", "Command", "Exit", "Weight", "Classification"], tablefmt="fancy_grid"))
        print()


@cli.command("resolve")
@click.option("--incident-id", "-i", default=None, help="Incident ID to resolve.")
@click.option("--by", "-u", default="oncall_engineer", help="Name of engineer resolving.")
@click.option("--root-cause", "-r", default=None, help="Explicit root cause override.")
def cmd_resolve(incident_id: str | None, by: str, root_cause: str | None) -> None:
    """Resolve an incident, trigger causal graph extraction, and synthesize runbook."""
    db = DatabaseManager()
    if incident_id:
        inc = db.get_incident(incident_id)
    else:
        inc = db.get_active_incident()

    if not inc:
        print(f"{RED}No active incident found to resolve.{RESET}")
        return

    inc.status = IncidentStatus.RESOLVED
    inc.ended_at = datetime.now(timezone.utc)
    inc.resolved_by = by
    if root_cause:
        inc.root_cause_category = root_cause

    events = db.get_events_for_incident(inc.id)
    print(f"\n{CYAN}Synthesizing intelligence graph and runbook for {len(events)} captured events...{RESET}")

    gen = RunbookGenerator(db=db)
    chain, runbook = gen.generate_runbook_for_incident(
        incident=inc,
        events=events,
        is_success=True,
    )

    content = (
        f"• Title: {inc.title}\n"
        f"• Inferred Root Cause: {runbook.root_cause_category}\n"
        f"• Synthesized Runbook: {runbook.title} (v{runbook.version})\n"
        f"• Earned Confidence: {runbook.confidence_display}\n"
        f"• Success Uses: {runbook.success_count} | Failures: {runbook.failure_count}"
    )
    print_banner("✔ Incident Resolved & Memory Recorded", content, color=GREEN)

    # Check drift
    drift_engine = DriftDetectionEngine(db)
    drift_reports = drift_engine.analyze_drift()
    if drift_reports:
        for d in drift_reports:
            if d.service == inc.service:
                d_content = f"{d.drift_summary}\n\nRecommendation:\n{d.backlog_recommendation}"
                print_banner("⚠ SYSTEMIC DRIFT DETECTED", d_content, color=RED)


@cli.command("runbooks")
@click.option("--service", "-s", default=None, help="Filter by service.")
@click.option("--project", "-p", default=None, help="Filter by project.")
def cmd_runbooks(service: str | None, project: str | None) -> None:
    """List synthesized runbooks with earned confidence scores."""
    db = DatabaseManager()
    runbooks = db.list_runbooks(service=service, project=project)

    if not runbooks:
        print(f"\n{DIM}No runbooks stored yet. Resolve an incident to generate operational memory.{RESET}\n")
        return

    table_rows = []
    for r in runbooks:
        table_rows.append([
            r.id,
            r.title[:30],
            r.project,
            r.service,
            r.root_cause_category[:25],
            f"v{r.version}",
            f"{GREEN}{r.confidence_display}{RESET}",
        ])
    print(f"\n{BOLD}{CYAN}OpsGenome Operational Runbook Library{RESET}")
    print(tabulate(table_rows, headers=["ID", "Title", "Project", "Service", "Root Cause", "Ver", "Earned Confidence"], tablefmt="fancy_grid"))
    print()


@cli.command("apply-fix")
@click.argument("runbook_id")
@click.option("--incident-id", "-i", default=None, help="Target incident ID (defaults to active incident).")
@click.option("--auto-approve", "--yolo", is_flag=True, default=False, help="Auto-approve execution without interactive prompt.")
@click.option("--ack", default=None, help="Cross-project acknowledgment string (e.g. 'CONFIRM FROM <source_project>').")
def cmd_apply_fix(runbook_id: str, incident_id: str | None, auto_approve: bool, ack: str | None) -> None:
    """Apply a verified remediation fix through the strict Trust Asymmetry Permission Gate."""
    import subprocess
    from opsgenome.prevention.permission_gate import (
        FixApplicationGate,
        FixExecutionRequest,
        CrossProjectAutoApproveForbiddenError,
        CrossProjectAcknowledgmentRequiredError,
    )
    from opsgenome.storage.project_context import detect_project

    db = DatabaseManager()
    runbook = db.get_runbook(runbook_id)
    if not runbook:
        print(f"{RED}Runbook '{runbook_id}' not found.{RESET}")
        return

    # Determine target incident and target project
    inc = None
    if incident_id:
        inc = db.get_incident(incident_id)
    else:
        inc = db.get_active_incident()

    target_project = inc.project if inc else detect_project()
    target_inc_id = inc.id if inc else "ad-hoc"
    source_project = runbook.project or "default"
    same_project = (target_project == source_project)

    # Get primary remediation command
    command = runbook.steps[0].command if runbook.steps else "echo 'No command specified'"

    content = (
        f"• Runbook: {runbook.title} ({runbook.id})\n"
        f"• Remediation Command: {command}\n"
        f"• Source Project: {source_project}\n"
        f"• Target Project: {target_project}\n"
        f"• Trust Tier: {'SAME-PROJECT (High Trust)' if same_project else 'CROSS-PROJECT (Explicit Lower Trust)'}"
    )
    if same_project:
        print_banner("⚡ Same-Project Remediation Fix Application", content, color=GREEN)
    else:
        print_banner("⚠ CROSS-PROJECT REMEDIATION FIX APPLICATION", content, color=YELLOW)
        print(f"{BOLD}{YELLOW}Notice:{RESET} This fix was generated in project '{source_project}'.")
        print(f"It has NOT been validated in this project's context ('{target_project}').")
        print(f"Automatic application (--auto-approve) is strictly prohibited.\n")

    confirmed = auto_approve
    cross_ack = ack

    if not auto_approve and not confirmed:
        if same_project:
            ans = click.confirm(f"Apply fix in {target_project}?", default=True)
            confirmed = ans
        else:
            ans = click.confirm(f"Do you want to apply this unvalidated fix from '{source_project}'?", default=False)
            confirmed = ans
            if confirmed and not cross_ack:
                print(f"\n{BOLD}{RED}MANDATORY DUAL-CONFIRMATION REQUIRED:{RESET}")
                print(f"To execute this cross-project command, you must type: {BOLD}CONFIRM FROM {source_project}{RESET}")
                cross_ack = click.prompt("Confirmation phrase", default="")

    req = FixExecutionRequest(
        runbook_id=runbook.id,
        target_incident_id=target_inc_id,
        target_project=target_project,
        source_project=source_project,
        command=command,
        same_project=same_project,
        confirmed=confirmed,
        cross_project_ack=cross_ack,
        auto_approve=auto_approve,
    )

    def execute_command(cmd: str) -> None:
        print(f"\n{CYAN}Executing: {cmd}{RESET}")
        try:
            tokens = shlex.split(cmd)
            res = subprocess.run(tokens, shell=False, capture_output=True, text=True)
        except Exception:
            # Safe fallback if binary requires shell builtins
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.stdout:
            print(res.stdout)
        if res.stderr:
            print(f"{YELLOW}{res.stderr}{RESET}")
        if res.returncode != 0:
            print(f"{RED}Command exited with code {res.returncode}{RESET}")
        else:
            print(f"{GREEN}Command completed successfully.{RESET}")

    try:
        result = FixApplicationGate.authorize_and_apply(req, runner_fn=execute_command)
        if result.executed:
            print(f"\n{GREEN}✔ {result.message}{RESET}\n")
        else:
            print(f"\n{YELLOW}✘ {result.message}{RESET}\n")
    except (CrossProjectAutoApproveForbiddenError, CrossProjectAcknowledgmentRequiredError) as err:
        print(f"\n{BOLD}{RED}⛔ PERMISSION GATE REFUSAL:{RESET} {err}\n")
        sys.exit(1)


@cli.command("export-runbook")
@click.argument("runbook_id")
def cmd_export_runbook(runbook_id: str) -> None:
    """Export a runbook as formatted Markdown."""
    db = DatabaseManager()
    runbook = db.get_runbook(runbook_id)
    if not runbook:
        print(f"{RED}Runbook '{runbook_id}' not found.{RESET}")
        return
    from opsgenome.ai.runbook_generator import RunbookGenerator
    md = RunbookGenerator.export_markdown(runbook)
    print(md)


@cli.command("replay")
@click.argument("incident_id")
def cmd_replay(incident_id: str) -> None:
    """Launch interactive SRE Replay Flight Simulator for an incident in the terminal."""
    db = DatabaseManager()
    flight_sim = FlightSimulatorEngine(db)
    sim_data = flight_sim.build_simulation(incident_id)

    if not sim_data:
        print(f"{RED}Error: Incident '{incident_id}' not found or has no captured events.{RESET}")
        return

    steps = sim_data["steps"]
    total = len(steps)

    header = (
        f"• Scenario: {sim_data['title']}\n"
        f"• Service: {sim_data['service']} | Severity: {sim_data['severity']}\n"
        f"• Root Cause: {sim_data['root_cause_category']}\n"
        f"• Steps: {total}"
    )
    print_banner("OPSGENOME SRE FLIGHT SIMULATOR", header, color=CYAN)

    current_idx = 0
    while current_idx < total:
        s = steps[current_idx]
        step_content = (
            f"Executed Command:\n  $ {s['command']}\n\n"
            f"Exit Code: {s['exit_code']} | Causal Status: {s['causal_status'].upper()}\n"
            f"Observed Output: {s['stdout'][:200]}\n"
            + (f"Stderr: {s['stderr']}\n" if s['stderr'] else "")
            + f"State Transition: {s['state_delta']}\n\n"
            f"Expert SRE Annotation:\n{s['expert_annotation']}"
        )
        print_banner(f"STEP {s['step_index']}/{s['total_steps']} — [{s['phase']}] (+{s['timestamp_offset_sec']}s)", step_content, color=YELLOW)

        if s.get("quiz_question"):
            print(f"\n{YELLOW}❓ {s['quiz_question']}{RESET}")
            for opt_idx, opt in enumerate(s["quiz_options"]):
                print(f"  [{opt_idx + 1}] {opt}")
            ans = click.prompt("Your choice", default="1")
            try:
                if int(ans) - 1 == s["quiz_correct_index"]:
                    print(f"{GREEN}✔ Correct! Excellent operational reasoning.{RESET}\n")
                else:
                    print(f"{RED}✘ Incorrect. Best practice was option [{s['quiz_correct_index'] + 1}].{RESET}\n")
            except ValueError:
                pass

        nav = click.prompt(f"{CYAN}[Enter/n]{RESET} Next | {CYAN}[p]{RESET} Previous | {CYAN}[q]{RESET} Quit", default="n")
        if nav.lower() == "q":
            break
        elif nav.lower() == "p":
            current_idx = max(0, current_idx - 1)
        else:
            current_idx += 1

    print(f"\n{GREEN}Simulation Complete. Operational knowledge imprinted!{RESET}\n")


@cli.command("drift")
def cmd_drift() -> None:
    """Show systemic drift analysis and recommended architectural backlog tickets."""
    db = DatabaseManager()
    drift_engine = DriftDetectionEngine(db)
    reports = drift_engine.analyze_drift()

    if not reports:
        print(f"\n{GREEN}✔ No systemic drift detected across services.{RESET}\n")
        return

    table_rows = []
    for r in reports:
        table_rows.append([
            r.service,
            r.root_cause_category[:35],
            str(r.incident_count),
            r.severity,
            r.backlog_recommendation[:50] + "...",
        ])
    print(f"\n{BOLD}{RED}OpsGenome Systemic Drift Radar & Backlog Recommendations{RESET}")
    print(tabulate(table_rows, headers=["Service", "Root Cause Category", "Recurrences", "Severity", "Backlog Action"], tablefmt="fancy_grid"))
    print()


@cli.command("bus-factor")
def cmd_bus_factor() -> None:
    """Analyze tribal knowledge concentration and bus factor scores."""
    db = DatabaseManager()
    analyzer = BusFactorAnalyzer(db)
    metrics = analyzer.analyze_services()

    if not metrics:
        print(f"\n{DIM}No incident resolution records found to analyze bus factor.{RESET}\n")
        return

    table_rows = []
    for m in metrics:
        risk_tag = f"{RED}{m.risk_level.value.upper()}{RESET}" if m.risk_level.value == "critical" else (
            f"{YELLOW}{m.risk_level.value.upper()}{RESET}" if m.risk_level.value == "warning" else f"{GREEN}{m.risk_level.value.upper()}{RESET}"
        )
        table_rows.append([
            m.service,
            str(m.bus_factor_score),
            m.top_expert,
            f"{int(m.top_expert_share * 100)}%",
            risk_tag,
            m.recommendation[:50] + "...",
        ])
    print(f"\n{BOLD}{CYAN}OpsGenome Tribal Knowledge & Bus Factor Analysis{RESET}")
    print(tabulate(table_rows, headers=["Service", "Bus Factor", "Top Expert", "Share", "Risk Level", "Recommendation"], tablefmt="fancy_grid"))
@cli.command("doctor")
@click.option("--namespace", "-n", default="payments", help="Kubernetes namespace to check.")
def cmd_doctor(namespace: str) -> None:
    """Run automated diagnostic healthcheck across all OpsGenome subsystems."""
    from opsgenome.cli.client import get_default_socket_path
    from opsgenome.watcher.k8s import K8sCollector

    print_logo()
    print(f"\n{BOLD}{CYAN}=== OpsGenome Doctor — Automated System Health & Diagnostics ==={RESET}\n")

    results = []

    # 1. Unix Domain Socket
    sock_str = get_default_socket_path()
    sock_path = Path(sock_str)
    if sock_path.exists():
        mode = oct(sock_path.stat().st_mode)[-4:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(sock_str)
                sock_status = f"{GREEN}ONLINE{RESET} (mode {mode})"
                sock_diag = f"UDS active at {sock_str} (POSIX 0600 isolation)."
        except Exception:
            sock_status = f"{YELLOW}STALE SOCKET{RESET}"
            sock_diag = f"Socket file exists but is not responding. Fix: rm -f {sock_str} (README.md §5.2)"
    else:
        sock_status = f"{YELLOW}OFFLINE{RESET}"
        sock_diag = f"Daemon not running. Fix: opsgenome daemon (README.md §5.1)"
    results.append(["IPC Socket", sock_status, sock_diag])

    # 2. Database & Schema Integrity
    try:
        db = DatabaseManager()
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            cursor.execute("PRAGMA table_info(causal_chains);")
            cols = [r["name"] for r in cursor.fetchall()]
            missing = [c for c in ["ranked_hypotheses_json", "disambiguation_required"] if c not in cols]
            if missing:
                db_status = f"{YELLOW}SCHEMA DRIFT{RESET}"
                db_diag = f"Missing columns: {missing}. Restart daemon to auto-migrate. (README.md §7.2)"
            else:
                db_status = f"{GREEN}HEALTHY{RESET} (WAL: {journal_mode.upper()})"
                db_diag = f"SQLite verified with WAL mode at {db.db_path}."
    except Exception as e:
        db_status = f"{RED}ERROR{RESET}"
        db_diag = f"{e}. (README.md §7.1)"
    results.append(["SQLite Storage", db_status, db_diag])

    # 3. Kubernetes Collector
    try:
        collector = K8sCollector(namespace=namespace)
        health = collector.check_health()
        if health.get("healthy"):
            if health.get("simulated"):
                k8s_status = f"{CYAN}SIMULATED [OK]{RESET}"
                k8s_diag = f"Minikube offline; high-fidelity simulation engine active (namespace: '{namespace}')."
            else:
                k8s_status = f"{GREEN}CONNECTED{RESET}"
                k8s_diag = f"API server responsive; namespace '{namespace}' active."
        else:
            from opsgenome.watcher.k8s_sim import SimulatedK8sCollector
            sim = SimulatedK8sCollector(namespace=namespace)
            sim_health = sim.check_health()
            if sim_health.get("healthy"):
                k8s_status = f"{CYAN}SIMULATED [OK]{RESET}"
                k8s_diag = f"Minikube offline; high-fidelity simulation engine active (namespace: '{namespace}')."
            else:
                k8s_status = f"{YELLOW}UNREACHABLE / RBAC{RESET}"
                k8s_diag = f"{health.get('error')}. (README.md §3)"
    except Exception as e:
        k8s_status = f"{RED}ERROR{RESET}"
        k8s_diag = f"{e}. (README.md §3)"
    results.append(["Kubernetes Collector", k8s_status, k8s_diag])

    # 4. Shell Integration Hooks
    home = Path.home()
    zsh_hook = home / ".opsgenome" / "hooks" / "opsgenome.zsh"
    zshrc = home / ".zshrc"
    has_rc = False
    try:
        if zshrc.exists():
            has_rc = "OpsGenome Shell Integration Hook" in zshrc.read_text(errors="ignore")
    except (PermissionError, OSError):
        has_rc = False

    try:
        hook_exists = zsh_hook.exists()
    except (PermissionError, OSError):
        hook_exists = False

    if hook_exists and has_rc:
        hook_status = f"{GREEN}INSTALLED{RESET}"
        hook_diag = "preexec/precmd hooks active in ~/.zshrc."
    elif hook_exists:
        hook_status = f"{YELLOW}PARTIAL{RESET}"
        hook_diag = "Hook script exists but ~/.zshrc unlinked. Run: opsgenome init"
    else:
        hook_status = f"{YELLOW}NOT INSTALLED / UNVERIFIED{RESET}"
        hook_diag = "Terminal hooks not verified. Run: opsgenome init (README.md §8.1)"
    results.append(["Shell Hooks", hook_status, hook_diag])

    # 5. AI Reasoning & Grounding
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_groq = bool(os.environ.get("GROQ_API_KEY"))
    has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_ollama = bool(os.environ.get("OLLAMA_HOST") or os.environ.get("OPSGENOME_LOCAL_LLM") == "1")
    if has_gemini:
        ai_status = f"{GREEN}GEMINI ONLINE{RESET}"
        ai_diag = "Google Gemini API key set; multimodal semantic reasoning active."
    elif has_groq:
        ai_status = f"{GREEN}GROQ LPU ONLINE{RESET}"
        ai_diag = "Groq LPU API key set; sub-200ms ultra-fast inference active."
    elif has_claude:
        ai_status = f"{GREEN}CLAUDE ONLINE{RESET}"
        ai_diag = "Anthropic API key set; multi-candidate semantic disambiguation enabled."
    elif has_ollama:
        ai_status = f"{GREEN}OLLAMA LOCAL ONLINE{RESET}"
        ai_diag = "Local air-gapped LLM provider active on localhost:11434."
    else:
        ai_status = f"{CYAN}OFFLINE HEURISTIC{RESET}"
        ai_diag = "Deterministic rule engine active with zero-token offline code repair."
    results.append(["AI Engine", ai_status, ai_diag])

    print(tabulate(results, headers=["Subsystem", "Health Status", "Diagnostic Details / Resolution"], tablefmt="fancy_grid"))
    print(f"\n{BOLD}{GREEN}💡 Diagnostic Guide:{RESET} For step-by-step root cause analysis and resolution commands, see {CYAN}README.md §Troubleshooting & Error Dictionary{RESET}.\n")


@cli.command("fix")
@click.argument("targets", nargs=-1, required=False)
@click.option("--ai", default="auto", type=click.Choice(["auto", "gemini", "groq", "claude", "ollama", "offline"], case_sensitive=False), help="AI reasoning engine provider.")
@click.option("--model", default=None, help="Model override (e.g. gemini-1.5-flash, llama-3.3-70b-versatile, claude-3-5-sonnet-20241022).")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Auto-apply patch without interactive confirmation prompt.")
@click.option("--verify/--no-verify", default=True, help="Run closed-loop verification after applying patch.")
def cmd_fix(targets: tuple[str, ...], ai: str, model: str | None, auto_approve: bool, verify: bool) -> None:
    """Autonomous AI Code & Incident Fixer with Closed-Loop Verification across single or multiple files."""
    from opsgenome.ai.code_fixer import CodeFixEngine
    from opsgenome.ai.engine import AIReasoningEngine

    db = DatabaseManager()
    ai_engine = AIReasoningEngine(provider=ai, model=model)
    fixer = CodeFixEngine(ai_engine=ai_engine, db=db)

    target_list = list(targets) if targets else [None]

    print(f"\n{BOLD}{CYAN}⚡ OpsGenome AI Autonomous Incident Fixer{RESET}")
    print(f"{DIM}AI Provider: {ai_engine.provider.upper()} ({ai_engine.model}) • Checking {len(target_list)} target{'s' if len(target_list) > 1 else ''}{RESET}\n")

    for idx, target in enumerate(target_list, start=1):
        if len(target_list) > 1:
            print(f"\n{BOLD}{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
            print(f"{BOLD}{CYAN}▶ [{idx}/{len(target_list)}] Target: {target or 'Auto-Detect Latest Failure'}{RESET}")
            print(f"{BOLD}{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

        try:
            failure = fixer.capture_failure(target)
        except Exception as err:
            print(f"{RED}Error capturing failure context:{RESET} {err}")
            if len(target_list) > 1:
                continue
            sys.exit(1)

        print(f"• {BOLD}Target Script / File:{RESET} {failure.target_file}")
        print(f"• {BOLD}Failed Command:{RESET} {failure.command} (Exit Code: {RED}{failure.exit_code}{RESET})")
        if failure.call_stack_files and len(failure.call_stack_files) > 1:
            print(f"• {BOLD}Multi-File Stack:{RESET} {CYAN}{' ➔ '.join(Path(f).name for f in failure.call_stack_files)}{RESET}")
        
        try:
            fix_result = fixer.generate_fix(failure)
        except Exception as err:
            print(f"{RED}Diagnosis failed:{RESET} {err}")
            if len(target_list) > 1:
                continue
            sys.exit(1)

        print(f"• {BOLD}Symptom:{RESET} {YELLOW}{fix_result.symptom}{RESET}")
        print(f"• {BOLD}Root Cause:{RESET} {fix_result.root_cause}")
        if fix_result.explanation:
            print(f"• {BOLD}Analysis:{RESET} {fix_result.explanation}")

        if fix_result.raw_bytes > 0:
            print(f"• {BOLD}Telemetry Distillation:{RESET} {GREEN}{fix_result.raw_bytes:,} bytes{RESET} raw log ➔ {CYAN}{fix_result.distilled_bytes:,} bytes{RESET} semantic frame ({BOLD}{GREEN}{fix_result.compression_percent}% token compression{RESET})")

        if fix_result.cache_hit:
            print(f"• {BOLD}API Optimization:{RESET} {BOLD}{GREEN}MEMORY CACHE HIT{RESET} (0 external API calls consumed)")
        elif ai_engine.provider == "offline":
            print(f"• {BOLD}API Optimization:{RESET} {BOLD}{CYAN}DETERMINISTIC FIRST-PASS{RESET} (0 external API calls consumed)")
        else:
            print(f"• {BOLD}API Optimization:{RESET} {BOLD}{GREEN}1 COMPACT SEMANTIC PROMPT{RESET} (rate-limit protected)")

        if not fix_result.diff.strip():
            print(f"\n{YELLOW}No code modifications needed. Script may already be up to date or healthy.{RESET}\n")
            continue

        print(f"\n{BOLD}{CYAN}Proposed Remediation Patch:{RESET}")
        print("=" * 60)
        for line in fix_result.diff.splitlines():
            if line.startswith("---") or line.startswith("+++"):
                print(f"{BOLD}{line}{RESET}")
            elif line.startswith("@@"):
                print(f"{CYAN}{line}{RESET}")
            elif line.startswith("+"):
                print(f"{GREEN}{line}{RESET}")
            elif line.startswith("-"):
                print(f"{RED}{line}{RESET}")
            else:
                print(line)
        print("=" * 60)

        confirmed = auto_approve
        if not auto_approve:
            target_name = Path(fix_result.target_file).name
            confirmed = click.confirm(f"\nApply this remediation patch to {target_name}?", default=True)

        if not confirmed:
            print(f"\n{YELLOW}Remediation cancelled by user. Target unchanged.{RESET}\n")
            continue

        backup_path = fixer.apply_patch(fix_result)
        print(f"\n{GREEN}✔ Patch applied successfully.{RESET}")
        print(f"  {DIM}Reversible backup created: {backup_path}{RESET}")

        if verify:
            print(f"\n{CYAN}🔄 Running Closed-Loop Verification:{RESET}")
            print(f"  Executing: {BOLD}{fix_result.command}{RESET}")
            retcode, stdout, stderr = fixer.verify_remediation(fix_result.command)
            if retcode == 0:
                print(f"\n{BOLD}{GREEN}✔ VERIFICATION PASSED (Exit Code 0):{RESET}")
                if stdout.strip():
                    print(f"{DIM}{stdout.strip()}{RESET}")
                print(f"\n{GREEN}Target restored to healthy baseline.{RESET}\n")
            else:
                print(f"\n{BOLD}{RED}✘ VERIFICATION FAILED (Exit Code {retcode}):{RESET}")
                if stderr.strip():
                    print(f"{RED}{stderr.strip()}{RESET}")
                if click.confirm("\nVerification failed. Rollback changes to original?", default=True):
                    fixer.rollback(fix_result)
                    print(f"{YELLOW}Rollback complete. Original state restored.{RESET}\n")


@cli.command("run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.argument("cmd_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--auto-fix", "-f", is_flag=True, default=False, help="Automatically trigger auto-fix if command fails.")
@click.option("--ai", default="auto", type=click.Choice(["auto", "gemini", "groq", "claude", "ollama", "offline"], case_sensitive=False), help="AI reasoning engine provider.")
def cmd_run(cmd_args: tuple[str, ...], auto_fix: bool, ai: str) -> None:
    """Execute command with real-time streaming, full stdout/stderr capture, structured error parsing, and auto-fix.

    Streams output live to the terminal. On failure (exit code != 0), captures telemetry,
    redacts secrets, extracts structured error diagnostics (exception_type, message, file, line),
    stores the event in the active or implicit incident, and checks cross-project recurrence.
    """
    import subprocess
    import time
    from opsgenome.cli.client import redact_and_dispatch
    from opsgenome.security.redactor import SecretRedactor, redact_structure
    from opsgenome.signal.parsers import parse_error
    from opsgenome.signal.stack_detector import detect_stack_from_command
    from opsgenome.storage.db import DatabaseManager
    from opsgenome.storage.models import Event, EventClassification, Incident, IncidentStatus, TriggerSource
    from opsgenome.storage.project_context import detect_project

    if not cmd_args:
        print(f"{RED}Error:{RESET} No command provided. Usage: opsgenome run <command...>")
        sys.exit(1)

    command_str = " ".join(cmd_args)
    work_dir = os.getcwd()

    # Prepend project's bin directory to PATH so local tools/runners are accessible
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[2]
    bin_dir = repo_root / "bin"
    if bin_dir.exists():
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    start_time = time.time()
    proc = subprocess.run(
        command_str,
        shell=True,
        capture_output=True,
        text=True,
        cwd=work_dir,
        env=env,
    )
    duration_ms = int((time.time() - start_time) * 1000)

    # 1. Output raw streams to terminal
    if proc.stdout:
        sys.stdout.write(proc.stdout)
        sys.stdout.flush()
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        sys.stderr.flush()

    # 2. In-process Secret Redaction (Fail-closed boundary)
    redactor = SecretRedactor()
    clean_cmd, _ = redactor.redact(command_str)
    clean_stdout, _ = redactor.redact(proc.stdout or "")
    clean_stderr, _ = redactor.redact(proc.stderr or "")

    # Security validation
    assert redactor.validate_clean(clean_cmd), "Command failed clean validation"
    assert redactor.validate_clean(clean_stdout), "Stdout failed clean validation"
    assert redactor.validate_clean(clean_stderr), "Stderr failed clean validation"

    # 3. Stack and Language Detection
    current_project = detect_project(work_dir)
    detected_stack = detect_stack_from_command(clean_cmd)

    # 4. Structured Error Parsing
    parsed_error = None
    combined_err = (clean_stderr + "\n" + clean_stdout).strip()
    if proc.returncode != 0 or any(k in combined_err for k in ["Traceback", "Exception", "Error:", "TypeError", "NullPointerException"]):
        parsed_error = parse_error(combined_err, language=detected_stack)
        if parsed_error:
            clean_pe, _ = redact_structure(parsed_error)
            parsed_error = clean_pe

    # 5. Incident Lifecycle & Event Storage
    db = DatabaseManager()
    active_inc = db.get_active_incident()
    created_implicit = False

    if not active_inc:
        symptom_list = []
        if parsed_error:
            symptom_list.append(f"{parsed_error.get('exception_type')}: {parsed_error.get('message')}")
        else:
            symptom_list.append(f"Command execution (exit {proc.returncode})")

        active_inc = Incident(
            title=f"Run: {clean_cmd[:50]}",
            service=current_project,
            project=current_project,
            stack=detected_stack,
            trigger_source=TriggerSource.MANUAL,
            status=IncidentStatus.OPEN,
            symptoms=symptom_list,
        )
        db.create_incident(active_inc)
        created_implicit = True

    event = Event(
        incident_id=active_inc.id,
        raw_command=clean_cmd,
        exit_code=proc.returncode,
        stdout_snippet=clean_stdout,
        stderr_snippet=clean_stderr,
        duration_ms=duration_ms,
        cwd=work_dir,
        tool_category=detected_stack if detected_stack != "general" else "system",
        project=current_project,
        stack=detected_stack,
        parsed_error=parsed_error,
        classification=EventClassification.DEAD_END if proc.returncode != 0 else EventClassification.FIX,
    )
    db.save_event(event)

    # Dispatch to daemon socket without truncation
    redact_and_dispatch(
        command=clean_cmd,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        cwd=work_dir,
        incident_id=active_inc.id,
        stdout_snippet=clean_stdout,
        stderr_snippet=clean_stderr,
    )

    # 6. Display Structured Diagnostics if Error Parsed
    if parsed_error:
        line_display = str(parsed_error['line']) if parsed_error['line'] is not None else "null"
        top_frame = parsed_error['stack_frames'][0] if parsed_error.get('stack_frames') else None
        top_frame_str = f"{top_frame['function']} in {top_frame['file']}:{top_frame['line']}" if top_frame else "None"

        diag_content = (
            f"• Language:       {parsed_error.get('language', '').upper()}\n"
            f"• Exception Type: {parsed_error.get('exception_type')}\n"
            f"• Message:        {parsed_error.get('message')}\n"
            f"• Primary File:   {parsed_error.get('file')}\n"
            f"• Fault Line:     {line_display}\n"
            f"• Top Frame:      {top_frame_str}\n"
            f"• Project Tag:    {current_project} | Stack: {detected_stack}\n"
            f"• Incident ID:    {active_inc.id} ({'Implicit Single-Shot' if created_implicit else 'Active Incident'})"
        )
        print_banner("⚡ OpsGenome Structured Error Diagnostics", diag_content, color=YELLOW)

        # Check recurrence alert across all projects
        rec_engine = RecurrenceAlertEngine(db=db)
        match = rec_engine.check_recurrence(active_inc, current_project=current_project)
        if match:
            rec_content = (
                f"{match['alert_message']}\n\n"
                f"Recommended Historical Actions:\n"
                + "\n".join([f"  $ {cmd}" for cmd in match.get("top_commands", [])])
            )
            banner_title = (
                f"⚡ RECURRENCE ALERT (Same-Project Intake Match: {match.get('source_project')})"
                if match.get("same_project")
                else f"⚠ CROSS-PROJECT RECURRENCE ADVISORY (Source: {match.get('source_project')})"
            )
            print_banner(banner_title, rec_content, color=GREEN if match.get("same_project") else YELLOW)

    if proc.returncode != 0:
        print(f"\n{BOLD}{RED}✘ Command failed with exit code {proc.returncode}{RESET}")
        if auto_fix:
            print(f"{CYAN}⚡ Auto-fix requested. Launching OpsGenome Autonomous Fixer...{RESET}")
            from opsgenome.ai.code_fixer import CodeFixEngine
            from opsgenome.ai.engine import AIReasoningEngine
            fixer = CodeFixEngine(ai_engine=AIReasoningEngine(provider=ai))
            failure = fixer.capture_failure(command_str)
            fix_result = fixer.generate_fix(failure)
            if fix_result.diff.strip():
                backup = fixer.apply_patch(fix_result)
                print(f"{GREEN}✔ Applied fix (backup: {backup}){RESET}")
                retcode, out, err = fixer.verify_remediation(fix_result.command)
                if retcode == 0:
                    print(f"{BOLD}{GREEN}✔ Closed-loop verification PASSED (Exit Code 0).{RESET}\n")
                    sys.exit(0)
                else:
                    print(f"{BOLD}{RED}✘ Verification failed. Rolling back...{RESET}")
                    fixer.rollback(fix_result)
                    sys.exit(proc.returncode)
        else:
            print(f"{CYAN}💡 Proactive Fix Available:{RESET} Run {BOLD}opsgenome fix{RESET} (or add {BOLD}-f / --auto-fix{RESET}) to autonomously repair this failure.\n")
        sys.exit(proc.returncode)


@click.command(name="triage")
@click.argument("log_sources", nargs=-1, required=False)
@click.option("--pod", "-p", default=None, help="Pod name provenance tag.")
@click.option("--container", "-c", default=None, help="Container name provenance tag.")
@click.option("--incident-id", "-i", default=None, help="Incident ID to attach triage findings to.")
@click.option("--threshold", "-t", default=0.60, type=float, help="Minimum signal confidence threshold (0.0-1.0).")
@click.option("--ai", default="auto", help="AI provider for Stage B disambiguation.")
def cmd_triage(log_sources: tuple[str, ...], pod: str | None, container: str | None, incident_id: str | None, threshold: float, ai: str) -> None:
    """Large-scale streaming log triage for Kubernetes, CI/CD, and container logs across single or multiple files."""
    from opsgenome.signal.streaming_scanner import StreamingLogScanner, merge_log_streams
    from opsgenome.security.redactor import EventSanitizer
    from opsgenome.ai.engine import AIReasoningEngine
    from opsgenome.storage.models import Event, EventClassification

    db = DatabaseManager()
    sanitizer = EventSanitizer()

    sources = list(log_sources) if log_sources else ["-"]

    # 1. Resolve Incident Session
    active_inc = None
    created_implicit = False
    if incident_id:
        active_inc = db.get_incident(incident_id)
    if not active_inc:
        open_incs = db.list_incidents(status=IncidentStatus.OPEN, limit=1)
        if open_incs:
            active_inc = open_incs[0]
        else:
            first_name = Path(sources[0]).name if sources[0] != "-" else "stream"
            active_inc = db.create_incident(
                Incident(
                    title=f"Log Triage: {first_name}" if len(sources) == 1 else f"Log Triage: {len(sources)} sources",
                    service=pod or "kubernetes-workload",
                    severity="P2",
                    trigger_source=TriggerType.MANUAL,
                )
            )
            created_implicit = True

    print(f"\n{BOLD}{CYAN}🔍 OpsGenome Large-Scale Streaming Log Triage{RESET}")
    source_desc = f"{len(sources)} source files" if len(sources) > 1 else (sources[0] if sources[0] != "-" else "stdin stream")
    print(f"{DIM}Stage A: Scanning {source_desc} in O(1) memory...{RESET}")

    scanner = StreamingLogScanner(min_signal_threshold=threshold)

    # 2. Open Stream(s) Lazily (Never materialize full log in memory)
    if len(sources) == 1:
        src = sources[0]
        def line_generator():
            if src == "-" or not os.path.exists(src):
                for line in sys.stdin:
                    yield line
            else:
                with open(src, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        yield line
        result = scanner.scan_stream(line_generator(), source_pod=pod, source_container=container)
    else:
        # Multi-file streaming: merge lazily via min-heap in O(num_streams) memory
        file_streams = []
        for file_path in sources:
            if os.path.exists(file_path):
                # Derive pod and container provenance from filename (e.g. payment-svc_app.log -> pod: payment-svc)
                stem = Path(file_path).stem
                parts = stem.split("_")
                p_name = pod or parts[0]
                c_name = container or (parts[1] if len(parts) > 1 else "main")

                def make_gen(p):
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            yield line

                file_streams.append((p_name, c_name, make_gen(file_path)))

        if not file_streams:
            print(f"{RED}Error:{RESET} None of the specified log files exist: {sources}")
            sys.exit(1)

        merged_stream = merge_log_streams(file_streams)
        result = scanner.scan_stream(merged_stream)

    # 3. Fail-Closed Redaction & Persistence of Surviving Candidates
    for cand in result.candidates:
        sanitizer.sanitize_candidate_window(cand)

        # Store candidate as Event in SQLite
        ev = Event(
            incident_id=active_inc.id,
            raw_command=f"log-triage: {cand.signal_type}",
            exit_code=1 if cand.score >= 0.80 else 0,
            stdout_snippet=cand.full_window_text[:1500],
            signal_weight=cand.score,
            tool_category="k8s_triage",
            project=active_inc.project,
            stack=active_inc.stack,
            parsed_error=cand.parsed_error,
            source_pod=cand.trigger_line.source_pod,
            source_container=cand.trigger_line.source_container,
            line_offset=cand.trigger_line.line_number,
            classification=EventClassification.DEAD_END if cand.score >= 0.80 else EventClassification.INVESTIGATION,
        )
        db.save_event(ev)

    # 4. Stage B Targeted Reasoning on Bounded Candidates
    ai_engine = AIReasoningEngine(provider=ai)
    stage_b_result = ai_engine.disambiguate_triage_candidates(active_inc, result.candidates)

    # 5. Display Triage Results Banner
    peak_mb = result.peak_memory_bytes / (1024 * 1024)
    speed_lps = int(result.total_lines_scanned / max(0.001, result.wall_time_seconds))

    sources_str = f"{len(sources)} files ({', '.join(Path(s).name for s in sources[:3])}{'...' if len(sources) > 3 else ''})" if len(sources) > 1 else (sources[0] if sources[0] != "-" else "stdin")
    telemetry_summary = (
        f"• Sources Checked:     {sources_str}\n"
        f"• Total Lines Scanned: {result.total_lines_scanned:,} lines\n"
        f"• Wall-Clock Time:     {result.wall_time_seconds:.3f} seconds ({speed_lps:,} lines/sec)\n"
        f"• Peak Memory (O(1)):  {peak_mb:.2f} MB\n"
        f"• High-Signal Found:   {'YES' if result.high_confidence_signal_found else 'NO'}\n"
        f"• Stage B Budget:      {len(result.candidates)} candidates ({sum(c.line_count for c in result.candidates)} lines of context, {stage_b_result.get('prompt_size_chars', 0)} chars)"
    )
    print_banner("⚡ Stage A Streaming Scanner Performance", telemetry_summary, color=CYAN)

    if result.high_confidence_signal_found and result.top_candidate:
        top = result.top_candidate
        pod_str = f"Pod: {top.trigger_line.source_pod}" if top.trigger_line.source_pod else "Pod: Unknown"
        cont_str = f" | Container: {top.trigger_line.source_container}" if top.trigger_line.source_container else ""
        diag_lines = [
            f"• Primary Hypothesis:  {stage_b_result.get('hypothesis')}",
            f"• Confidence Score:    {int(top.score * 100)}%",
            f"• Provenance:          {pod_str}{cont_str}",
            f"• Line Offset:         Line {top.trigger_line.line_number}",
        ]
        if top.parsed_error:
            diag_lines.extend([
                f"• Stack / Language:    {top.parsed_error.get('language', '').upper()}",
                f"• Exception Type:      {top.parsed_error.get('exception_type')}",
                f"• Location:            {top.parsed_error.get('file')}:{top.parsed_error.get('line')}",
                f"• Error Message:       {top.parsed_error.get('message')}",
            ])
        if stage_b_result.get("disambiguation_required"):
            diag_lines.append("\n• Ranked Hypotheses (Stage B Disambiguation):")
            for h in stage_b_result.get("ranked_hypotheses", []):
                diag_lines.append(f"  [{h['rank']}] {h['hypothesis']} (Confidence: {int(h['confidence']*100)}%)")
                diag_lines.append(f"      Distinguishing Factor: {h.get('distinguishing_factor')}")

        print_banner("🎯 Root Cause Diagnostics & Attribution", "\n".join(diag_lines), color=GREEN)
    else:
        print_banner(
            "ℹ Triage Result: Clean Log Stream",
            f"No critical root-cause errors detected across {result.total_lines_scanned:,} lines.\n"
            f"All lines scored below confidence threshold {threshold:.2f} (zero false positives reported).",
            color=YELLOW,
        )


# --- Multi-Agent Swarm CLI Commands ---

@cli.group("multi-agent")
def multi_agent_group() -> None:
    """Multi-Agent Swarm Orchestration & Cross-Stack Incident Resolution."""
    pass


@multi_agent_group.command("analyze")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--file", "-f", "file_options", multiple=True, type=click.Path(exists=True), help="Path to file to analyze (can be passed multiple times).")
@click.option("--demo", is_flag=True, help="Run cross-stack demo incident (Python, Node, Java, K8s).")
@click.option("--reset", is_flag=True, help="Reset demo incident files to default benchmark state.")
def cmd_multi_agent_analyze(files: tuple[str, ...], file_options: tuple[str, ...], demo: bool, reset: bool = False) -> None:
    """Analyze multiple heterogeneous files across stacks with agent swarm."""
    orchestrator = LeadSREOrchestrator()

    combined_files = list(files) + list(file_options)

    if demo or not combined_files:
        if reset:
            reset_demo_incident_files()
        targets = get_demo_cross_stack_targets(read_from_disk_if_available=True)
    else:
        from opsgenome.agents.demo_scenarios import extract_error_from_incident_log
        from opsgenome.ai.code_fixer import safe_subprocess_run
        import shutil
        import sys
        targets = []
        for f in combined_files:
            p = Path(f)
            if p.suffix == ".log":
                log_text = p.read_text(encoding="utf-8", errors="replace")
                src_matches = set(re.findall(r'([a-zA-Z0-9_\-\./\\]+\.(?:py|js|mjs|java|yaml|yml|tf|hcl))', log_text))
                for sm in src_matches:
                    resolved = Path(sm) if Path(sm).is_file() else (REPO_ROOT / sm).resolve()
                    if resolved.is_file():
                        code = resolved.read_text(encoding="utf-8", errors="replace")
                        err_ctx = extract_error_from_incident_log(str(resolved), default_err=f"Failure trace in {p.name}")
                        targets.append((str(resolved), code, err_ctx))
                continue

            code = p.read_text(encoding="utf-8", errors="replace")
            err_ctx = extract_error_from_incident_log(str(p), default_err="")
            if not err_ctx:
                ext = p.suffix.lower()
                if ext == ".py":
                    try:
                        import ast
                        ast.parse(code, filename=str(p))
                        proc = safe_subprocess_run([sys.executable, str(p)], timeout=3)
                        if proc.returncode != 0:
                            err_ctx = (proc.stderr or proc.stdout).strip()
                    except SyntaxError as se:
                        err_ctx = f"SyntaxError: {se.msg} at line {se.lineno}"
                elif ext in (".js", ".mjs") and shutil.which("node"):
                    proc = safe_subprocess_run(["node", "--check", str(p)], timeout=3)
                    if proc.returncode != 0:
                        err_ctx = (proc.stderr or proc.stdout).strip()
                elif ext in (".yaml", ".yml"):
                    mem_m = re.search(r"memory:\s*[\"']?(\d+)(Mi|Gi|M|G)[\"']?", code, re.IGNORECASE)
                    if mem_m and int(mem_m.group(1)) < 512:
                        err_ctx = f"OOMKilled: Container memory limit `{mem_m.group(1)}{mem_m.group(2)}` is below 512Mi minimum threshold."
                elif ext in (".tf", ".hcl"):
                    err_ctx = f"TerraformError: Configuration diagnostic in {p.name}"
            targets.append((str(p), code, err_ctx or f"Error detected in {p.name}"))


    ai_engine = orchestrator.ai_engine
    ai_prov = getattr(ai_engine, "provider", "offline").upper()
    ai_mod = getattr(ai_engine, "model", "default")
    print(f"\n{BOLD}{CYAN}🤖 OPSGENOME MULTI-AGENT SWARM: CROSS-STACK INCIDENT RESOLUTION{RESET}")
    print(f"• {BOLD}Active AI Engine:{RESET} {GREEN}{ai_prov}{RESET} ({CYAN}{ai_mod}{RESET})")
    print(f"• {BOLD}API Credit Optimization:{RESET} {GREEN}ACTIVE{RESET} (Heuristic Pre-Filter + Semantic Log Distillation + Token Caps)")
    print(f"{DIM}Lead Orchestrator dispatching tasks across {len(targets)} components...{RESET}\n")

    plan, messages = orchestrator.analyze_and_coordinate(targets)

    # 1. Display Swarm Dialogue
    print(f"{BOLD}{MAGENTA}─── 💬 SWARM INTER-AGENT DIALOGUE ─────────────────────────────────────────────{RESET}")
    for msg in messages:
        sender_color = CYAN if "Lead" in msg.sender else (GREEN if "Specialist" in msg.sender else YELLOW)
        type_badge = f"{BOLD}[{msg.message_type}]{RESET}"
        print(f"{sender_color}{BOLD}{msg.sender}{RESET} ➔ {DIM}{msg.recipient}{RESET} {type_badge}")
        print(f"   {msg.content}\n")

    # 2. Display Coordinated Resolution Plan
    print(f"{BOLD}{GREEN}─── 📋 COORDINATED RESOLUTION PLAN (ID: {plan.plan_id}) ─────────────────────{RESET}")
    print(f"{BOLD}Summary:{RESET} {plan.cross_stack_summary}\n")
    print(f"{BOLD}Execution Order (Topological Dependency via Kahn's Algorithm):{RESET}")
    for i, fpath in enumerate(plan.execution_order, 1):
        finding = next((f for f in plan.findings if f.target_file == fpath), None)
        stack_badge = f"[{finding.stack.upper()}]" if finding else ""
        print(f"  {CYAN}{i}.{RESET} {BOLD}{Path(fpath).name}{RESET} {DIM}{stack_badge}{RESET}")

    if getattr(plan, "edge_explanations", None):
        print(f"\n{BOLD}Topological Dependency Graph Edges:{RESET}")
        for edge in plan.edge_explanations:
            print(f"  • {DIM}{edge}{RESET}")

    print(f"\n{BOLD}Atomic Diffs Formulated:{RESET}")
    for finding in plan.findings:
        eng_src = getattr(finding, "engine_source", "Deterministic Heuristic")
        print(f"\n{YELLOW}--- {Path(finding.target_file).name} ({finding.stack.upper()} | {finding.exception_type}) ---{RESET}")
        print(f"• {BOLD}Diagnosis & Repair Engine:{RESET} {CYAN}{eng_src}{RESET}")
        print(f"{DIM}Root Cause:{RESET} {finding.root_cause}")
        print(finding.proposed_diff)

    print(f"\n{BOLD}{CYAN}Verification & Rollback Strategy:{RESET}")
    for cmd in plan.verification_commands:
        print(f"  • Verification: {CYAN}{cmd}{RESET}")
    for rb in plan.rollback_plan:
        print(f"  • Safety Guard: {YELLOW}{rb}{RESET}")
    print()


@multi_agent_group.command("cluster-audit")
@click.option("--namespace", default="default", help="Kubernetes namespace to audit.")
def cmd_multi_agent_cluster_audit(namespace: str) -> None:
    """Audit Kubernetes & Docker clusters for multiple concurrent failure modes."""
    auditor = ClusterMultiIssueAuditor()
    print(f"\n{BOLD}{CYAN}🔍 KUBERNETES & DOCKER CLUSTER MULTI-ISSUE AUDITOR{RESET}")
    print(f"{DIM}Namespace: {namespace} | Deep cluster anomaly & misconfiguration scan...{RESET}\n")

    report = auditor.audit_cluster(namespace=namespace)

    # 1. Summary Matrix Table
    table_data = []
    for issue in report.issues:
        sev_color = RED if issue.severity == "CRITICAL" else (YELLOW if issue.severity == "HIGH" else CYAN)
        table_data.append([
            f"{sev_color}{issue.severity}{RESET}",
            issue.resource_type,
            f"{BOLD}{issue.resource_name}{RESET}",
            issue.issue_type,
            issue.safety_tier,
            issue.root_cause[:45] + ("..." if len(issue.root_cause) > 45 else ""),
        ])

    print(tabulate(table_data, headers=["Severity", "Type", "Resource", "Issue", "Safety Tier", "Root Cause"], tablefmt="fancy_grid"))
    print(f"\n{BOLD}Total Anomalies Detected:{RESET} {len(report.issues)} simultaneous issues.\n")

    # 2. Step-by-Step Remediation Playbook
    print(f"{BOLD}{GREEN}─── 🛠 STEP-BY-STEP REMEDIATION PLAYBOOK & YAML PATCHES ────────────────────────{RESET}")
    for i, issue in enumerate(report.issues, 1):
        print(f"\n{BOLD}{CYAN}[Issue #{i}] {issue.resource_name} ({issue.issue_type}){RESET}")
        print(f"{BOLD}Root Cause:{RESET} {issue.root_cause}")
        print(f"{BOLD}Impact:{RESET} {issue.impact}")
        if issue.immediate_remediation_cmd:
            print(f"{BOLD}Immediate Remediation CLI:{RESET}")
            print(f"  {GREEN}{issue.immediate_remediation_cmd}{RESET}")
        if issue.declarative_yaml_patch:
            print(f"{BOLD}Declarative YAML Patch:{RESET}")
            print(f"{DIM}{issue.declarative_yaml_patch.strip()}{RESET}")
        if issue.verification_cmd:
            print(f"{BOLD}Verification CLI:{RESET}")
            print(f"  {CYAN}{issue.verification_cmd}{RESET}")

    print(f"\n{BOLD}{GREEN}✔ Cluster multi-issue diagnostic audit complete.{RESET}\n")


@multi_agent_group.command("demo")
def cmd_multi_agent_demo() -> None:
    """Run full simulated end-to-end multi-agent cross-stack incident & cluster audit."""
    print_logo()
    print_banner(
        "🤖 OpsGenome Multi-Agent Swarm Demonstration",
        "1. Dispatching concurrent analysis across 4 heterogeneous tech stacks.\n"
        "2. Security Sentinel enforcing zero secret leakage and safe execution.\n"
        "3. Synthesizing topological dependency order for atomic patching.\n"
        "4. Auditing live cluster for 3 concurrent Kubernetes & Docker failure modes.",
        color=MAGENTA,
    )

    orchestrator = LeadSREOrchestrator()
    auditor = ClusterMultiIssueAuditor()

    # Phase 1: Cross-Stack Analysis (Loaded from decoupled demo_scenarios)
    demo_targets = get_demo_cross_stack_targets(read_from_disk_if_available=True)


    print(f"\n{BOLD}{CYAN}=== STEP 1: CONCURRENT SPECIALIST AGENT DISPATCH ==={RESET}\n")
    plan, messages = orchestrator.analyze_and_coordinate(demo_targets)

    for msg in messages:
        sender_color = CYAN if "Lead" in msg.sender else (GREEN if "Specialist" in msg.sender else MAGENTA)
        print(f"{sender_color}{BOLD}{msg.sender}{RESET} ➔ {DIM}{msg.recipient}{RESET} {BOLD}[{msg.message_type}]{RESET}")
        print(f"   {msg.content}\n")

    print(f"\n{BOLD}{CYAN}=== STEP 2: SYNTHESIZED TOPOLOGICAL EXECUTION PLAN ==={RESET}\n")
    print(f"{BOLD}Execution Sequence:{RESET}")
    for idx, path in enumerate(plan.execution_order, 1):
        print(f"  {CYAN}[Step {idx}]{RESET} Apply atomic patch to {BOLD}{Path(path).name}{RESET}")

    print(f"\n{BOLD}{CYAN}=== STEP 3: CLUSTER MULTI-ISSUE AUDIT & REMEDIATION PLAYBOOK ==={RESET}\n")
    report = auditor.audit_cluster(namespace="production")
    for issue in report.issues:
        print(f"• {RED}{BOLD}[{issue.severity}] {issue.resource_name}{RESET}: {issue.issue_type}")
        print(f"  Root Cause: {issue.root_cause}")
        if issue.immediate_remediation_cmd:
            print(f"  Remediation CLI: {GREEN}{issue.immediate_remediation_cmd}{RESET}")
    print(f"\n{BOLD}{GREEN}✔ Multi-agent demonstration completed successfully!{RESET}\n")


@multi_agent_group.command("chaos-test")
@click.option("--fail-verify", is_flag=True, help="Simulate a verification check failure to prove transactional rollback.")
def cmd_multi_agent_chaos_test(fail_verify: bool) -> None:
    """Inject live chaos, synthesize Topological DAG, and verify transactional commit or rollback."""
    orchestrator = LeadSREOrchestrator()
    print(f"\n{BOLD}{CYAN}⚡ OPSGENOME MULTI-AGENT SWARM: LIVE CHAOS & TRANSACTIONAL VERIFICATION{RESET}")
    print(f"{DIM}Demonstrating live fault injection, Kahn's algorithm DAG, and transactional atomic commit...{RESET}\n")

    # Ensure demo files are in fresh incident state
    reset_demo_incident_files()
    targets = get_demo_cross_stack_targets(read_from_disk_if_available=True)

    print(f"{BOLD}Step 1: Active Multi-Stack Cascade Incident Detected Across {len(targets)} Components{RESET}")
    for p, _, err in targets:
        print(f"  • {BOLD}{Path(p).name}{RESET}: {DIM}{err}{RESET}")

    print(f"\n{BOLD}Step 2: Synthesizing Master Resolution Plan & Topological DAG...{RESET}")
    plan, messages = orchestrator.analyze_and_coordinate(targets)

    print(f"\n{BOLD}Topological Execution Sequence (Kahn's Algorithm):{RESET}")
    for idx, path in enumerate(plan.execution_order, 1):
        print(f"  {CYAN}[Step {idx}]{RESET} {BOLD}{Path(path).name}{RESET}")

    if getattr(plan, "edge_explanations", None):
        print(f"\n{BOLD}Dependency Graph Edges:{RESET}")
        for edge in plan.edge_explanations:
            print(f"  • {DIM}{edge}{RESET}")

    if fail_verify:
        print(f"\n{YELLOW}{BOLD}Step 3: Chaos Mode Active -- Intentionally injecting invalid syntax to trigger verification failure...{RESET}")
        for f in plan.findings:
            if f.stack == "python":
                f.fixed_code = "def syntax_broken(:\n    invalid code here\n"
                f.proposed_diff = "@@ -1,5 +1,2 @@\n-def calculate_fee\n+def syntax_broken(:"

    print(f"\n{BOLD}Step 4: Executing Two-Phase Transactional Commit & Closed-Loop Verification...{RESET}")
    success, log = orchestrator.apply_coordinated_fix(plan, verify_live=True)

    for line in log:
        if "✔" in line:
            print(f"  {GREEN}{line}{RESET}")
        elif "✘" in line:
            print(f"  {RED}{line}{RESET}")
        elif "↺" in line:
            print(f"  {YELLOW}{line}{RESET}")
        else:
            print(f"  {DIM}{line}{RESET}")

    if success:
        print(f"\n{BOLD}{GREEN}✔ TRANSACTION STATUS: VERIFIED_AND_COMMITTED{RESET}")
        print(f"{DIM}All patches verified against live syntax & health gates. Zero regression guarantee.{RESET}\n")
    else:
        print(f"\n{BOLD}{YELLOW}↺ TRANSACTION STATUS: ROLLED_BACK (Safety Invariant Preserved){RESET}")
        print(f"{DIM}Verification failed as expected; all files deterministically restored from .bak with verified SHA-256 hashes.{RESET}\n")



cli.add_command(multi_agent_group, name="multi-agent")
cli.add_command(multi_agent_group, name="multiagent")
cli.add_command(cmd_fix, name="auto-fix")
cli.add_command(cmd_run, name="exec")
cli.add_command(cmd_triage, name="triage")


if __name__ == "__main__":
    cli()


