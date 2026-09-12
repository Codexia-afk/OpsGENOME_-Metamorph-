"""OpsGenome CLI Application.

Provides complete terminal command-line interface, interactive SRE flight simulator,
ASCII banner, and categorized key-driven help guide.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
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
                ("drift [3 / d]", "Systemic Drift Radar", "Detects repeating root causes and automatically generates Jira/Linear defect tickets."),
                ("bus-factor [4 / b]", "Tribal Knowledge Risk Matrix", "Calculates bus factor ratings and identifies single-point-of-failure on-call engineers."),
            ],
        ),
        (
            "⚙️ 5. PLATFORM SETUP, DAEMON & DEMO",
            [
                ("demo [6 / t]", "Run 6-Step Hackathon Demo", "Executes full end-to-end demo (CrashLoopBackOff -> Redaction -> Recurrence -> Drift)."),
                ("daemon [7 / w]", "Launch Daemon & Web UI", "Starts REST API, Webhook listener (PagerDuty/Slack), and Web Dashboard on :8765."),
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
        print(f"  {BOLD}[?]{RESET} or {BOLD}[h]{RESET} -> {CYAN}help{RESET}          (View Full Categorized Command Matrix)")
        print(f"  {BOLD}[q]{RESET}         -> Exit\n")

        choice = click.prompt(f"{YELLOW}Select an action [1-7 / s / r / d / b / p / t / w / ? / q]{RESET}", default="?", show_default=False)
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
@click.option("--host", default="127.0.0.1", help="Host to bind daemon to.")
@click.option("--port", default=8765, type=int, help="Port to listen on.")
def cmd_daemon(host: str, port: int) -> None:
    """Start the OpsGenome local background daemon & webhook server."""
    print_logo()

    # Check if port is already occupied
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                content = (
                    f"• Daemon is ALREADY active on: http://{host}:{port}\n"
                    f"• Web Dashboard:             http://{host}:{port}\n"
                    f"• To stop previous process:   lsof -ti :{port} | xargs kill -9"
                )
                print_banner("OpsGenome Daemon Already Running", content, color=YELLOW)
                return
    except Exception:
        pass

    content = (
        f"• Web Dashboard URL:   http://{host}:{port}\n"
        f"• PagerDuty Webhook:   http://{host}:{port}/api/v1/webhooks/pagerduty\n"
        f"• Live War Room WS:    ws://{host}:{port}/ws/live"
    )
    print_banner("OpsGenome Operational Memory Engine Online", content, color=GREEN)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except (OSError, SystemExit):
        print(f"\n{YELLOW}⚠ Port {port} is already in use by another OpsGenome daemon process.{RESET}")
        print(f"  • Your OpsGenome daemon is ALREADY active and running!")
        print(f"  • View it directly in browser: {CYAN}http://localhost:{port}{RESET}")
        print(f"  • Or stop the old process to restart: {GREEN}lsof -ti :{port} | xargs kill -9{RESET}\n")




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
        print_banner("⚡ RECURRENCE ALERT (Sub-50ms Intake Match)", rec_content, color=YELLOW)


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
def cmd_runbooks(service: str | None) -> None:
    """List synthesized runbooks with earned confidence scores."""
    db = DatabaseManager()
    runbooks = db.list_runbooks(service=service)

    if not runbooks:
        print(f"\n{DIM}No runbooks stored yet. Resolve an incident to generate operational memory.{RESET}\n")
        return

    table_rows = []
    for r in runbooks:
        table_rows.append([
            r.id,
            r.title[:35],
            r.service,
            r.root_cause_category[:30],
            f"v{r.version}",
            f"{GREEN}{r.confidence_display}{RESET}",
        ])
    print(f"\n{BOLD}{CYAN}OpsGenome Operational Runbook Library{RESET}")
    print(tabulate(table_rows, headers=["ID", "Title", "Service", "Root Cause", "Ver", "Earned Confidence"], tablefmt="fancy_grid"))
    print()


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
    print()


if __name__ == "__main__":
    cli()
