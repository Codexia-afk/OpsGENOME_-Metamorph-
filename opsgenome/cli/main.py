"""OpsGenome CLI Application.

Provides complete terminal command-line interface, interactive SRE flight simulator,
ASCII banner, and categorized key-driven help guide.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import click
from tabulate import tabulate
import uvicorn
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
        print(f"  {BOLD}[?]{RESET} or {BOLD}[h]{RESET} -> {CYAN}help{RESET}          (View Full Categorized Command Matrix)")
        print(f"  {BOLD}[q]{RESET}         -> Exit\n")

        choice = click.prompt(f"{YELLOW}Select an action [1-8 / s / r / d / b / p / t / w / c / ? / q]{RESET}", default="?", show_default=False)
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
            sock_diag = f"Socket file exists but is not responding. Fix: rm -f {sock_str} (TROUBLESHOOTING.md §5.2)"
    else:
        sock_status = f"{YELLOW}OFFLINE{RESET}"
        sock_diag = f"Daemon not running. Fix: opsgenome daemon (TROUBLESHOOTING.md §5.1)"
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
                db_diag = f"Missing columns: {missing}. Restart daemon to auto-migrate. (TROUBLESHOOTING.md §7.2)"
            else:
                db_status = f"{GREEN}HEALTHY{RESET} (WAL: {journal_mode.upper()})"
                db_diag = f"SQLite verified with WAL mode at {db.db_path}."
    except Exception as e:
        db_status = f"{RED}ERROR{RESET}"
        db_diag = f"{e}. (TROUBLESHOOTING.md §7.1)"
    results.append(["SQLite Storage", db_status, db_diag])

    # 3. Kubernetes Collector
    try:
        collector = K8sCollector(namespace=namespace)
        health = collector.check_health()
        if health.get("healthy"):
            k8s_status = f"{GREEN}CONNECTED{RESET}"
            k8s_diag = f"API server responsive; namespace '{namespace}' active."
        else:
            k8s_status = f"{YELLOW}UNREACHABLE / RBAC{RESET}"
            k8s_diag = f"{health.get('error')}. (TROUBLESHOOTING.md §3)"
    except Exception as e:
        k8s_status = f"{RED}ERROR{RESET}"
        k8s_diag = f"{e}. (TROUBLESHOOTING.md §3)"
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
        hook_diag = "Terminal hooks not verified. Run: opsgenome init (TROUBLESHOOTING.md §8.1)"
    results.append(["Shell Hooks", hook_status, hook_diag])

    # 5. AI Reasoning & Grounding
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_key:
        ai_status = f"{GREEN}CLAUDE ONLINE{RESET}"
        ai_diag = "Anthropic API key set; multi-candidate semantic disambiguation enabled."
    else:
        ai_status = f"{CYAN}OFFLINE HEURISTIC{RESET}"
        ai_diag = "Deterministic rule engine active with honest fallback. (TROUBLESHOOTING.md §6.1)"
    results.append(["AI Engine", ai_status, ai_diag])

    print(tabulate(results, headers=["Subsystem", "Health Status", "Diagnostic Details / Resolution"], tablefmt="fancy_grid"))
    print(f"\n{BOLD}{GREEN}💡 Diagnostic Guide:{RESET} For step-by-step root cause analysis and resolution commands, see {CYAN}TROUBLESHOOTING.md{RESET}.\n")


if __name__ == "__main__":
    cli()
