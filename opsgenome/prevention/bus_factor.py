"""Bus Factor & Tribal Knowledge Analyzer.

Measures the concentration of operational knowledge across engineers and services,
identifying single points of failure in on-call response.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from opsgenome.storage.db import DatabaseManager
from opsgenome.storage.models import BusFactorMetric, Incident, RiskLevel


class BusFactorAnalyzer:
    """Calculates bus factor and tribal knowledge distribution across services."""

    def __init__(self, db: DatabaseManager | None = None):
        self.db = db or DatabaseManager()

    def analyze_services(self, incidents: list[Incident] | None = None) -> list[BusFactorMetric]:
        """Compute bus factor metrics for all services."""
        if incidents is None:
            incidents = self.db.list_incidents(limit=500)

        service_map: dict[str, list[str]] = defaultdict(list)
        for inc in incidents:
            if inc.resolved_by:
                service_map[inc.service].append(inc.resolved_by)

        metrics: list[BusFactorMetric] = []

        for service, engineers in service_map.items():
            total = len(engineers)
            if total == 0:
                continue

            counts = Counter(engineers)
            sorted_engineers = sorted(counts.items(), key=lambda x: x[1], reverse=True)

            top_engineer, top_count = sorted_engineers[0]
            top_share = round(top_count / total, 2)

            # Bus factor: minimum number of engineers accounting for >= 75% of resolutions
            cumulative = 0
            bus_factor = 0
            for _, count in sorted_engineers:
                cumulative += count
                bus_factor += 1
                if cumulative / total >= 0.75:
                    break

            # Risk level
            if bus_factor == 1 or top_share >= 0.70:
                risk = RiskLevel.CRITICAL
                recommendation = (
                    f"CRITICAL RISK: {top_engineer} handles {int(top_share * 100)}% of incidents on '{service}'. "
                    f"Schedule SRE Replay Flight Simulator onboarding for junior engineers to distribute tribal knowledge."
                )
            elif bus_factor == 2:
                risk = RiskLevel.WARNING
                recommendation = (
                    f"MODERATE RISK: Knowledge for '{service}' is concentrated in 2 engineers. "
                    "Run shadow mode sessions during upcoming on-call rotations."
                )
            else:
                risk = RiskLevel.HEALTHY
                recommendation = f"HEALTHY: Operational knowledge for '{service}' is well distributed across the team."

            metrics.append(
                BusFactorMetric(
                    service=service,
                    domain="Core Services",
                    total_incidents=total,
                    engineers=dict(counts),
                    bus_factor_score=bus_factor,
                    top_expert=top_engineer,
                    top_expert_share=top_share,
                    risk_level=risk,
                    recommendation=recommendation,
                )
            )

        return sorted(metrics, key=lambda x: (x.risk_level == RiskLevel.CRITICAL, x.top_expert_share), reverse=True)
