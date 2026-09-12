"""CLI / Demo script to seed 10-week incident history and display live analytics."""

from __future__ import annotations

from tabulate import tabulate
from opsgenome.prevention.bus_factor import BusFactorAnalyzer
from opsgenome.prevention.drift import DriftDetectionEngine
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.seed import seed_incident_history

# Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main():
    print(f"\n{BOLD}{CYAN}=== Seeding 10-Week Incident History for 'payments-deploy' ==={RESET}")
    db = DatabaseManager()
    seeded = seed_incident_history(db)
    print(f"{GREEN}✔ Seeded {len(seeded)} real historical incidents spanning 10 weeks into SQLite database.{RESET}\n")

    # 1. Runbooks
    print(f"{BOLD}{CYAN}1. Runbooks with Computed Confidence Scores:{RESET}")
    runbooks = db.list_runbooks(service="payments-deploy")
    rb_table = []
    for r in runbooks:
        rb_table.append([r.id, r.title, r.root_cause_category, f"v{r.version}", r.confidence_display])
    print(tabulate(rb_table, headers=["ID", "Runbook Title", "Root Cause Category", "Version", "Earned Confidence"], tablefmt="fancy_grid"))

    # 2. Systemic Drift
    print(f"\n{BOLD}{RED}2. Systemic Drift Radar (Live Detected from 11 Incidents):{RESET}")
    drift_engine = DriftDetectionEngine(db=db, recurrence_threshold=2)
    reports = drift_engine.analyze_drift()
    drift_table = []
    for d in reports:
        if d.service == "payments-deploy":
            drift_table.append([d.service, d.root_cause_category, d.incident_count, d.severity, d.backlog_recommendation[:60] + "..."])
    print(tabulate(drift_table, headers=["Service", "Root Cause Category", "Recurrences", "Severity", "Backlog Action Item"], tablefmt="fancy_grid"))

    # 3. Bus Factor
    print(f"\n{BOLD}{YELLOW}3. Bus Factor & Tribal Knowledge Matrix:{RESET}")
    bus_analyzer = BusFactorAnalyzer(db=db)
    metrics = bus_analyzer.analyze_services()
    bus_table = []
    for m in metrics:
        if m.service == "payments-deploy":
            bus_table.append([m.service, m.bus_factor_score, m.top_expert, f"{int(m.top_expert_share * 100)}%", str(m.risk_level.value if hasattr(m.risk_level, 'value') else m.risk_level).upper(), m.recommendation[:55] + "..."])
    print(tabulate(bus_table, headers=["Service", "Bus Factor", "Top Expert", "Share", "Risk Level", "Recommendation"], tablefmt="fancy_grid"))
    print()


if __name__ == "__main__":
    main()
