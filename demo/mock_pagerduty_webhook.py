"""Utility to trigger simulated PagerDuty / Slack Webhooks to a running OpsGenome Daemon."""

from __future__ import annotations

import sys
import httpx


def trigger_pagerduty_alert(
    daemon_url: str = "http://127.0.0.1:8765",
    title: str = "CRITICAL: payments-service 504 Gateway Timeout spike",
    service: str = "payments-service",
    urgency: str = "high",
) -> None:
    endpoint = f"{daemon_url}/api/v1/webhooks/pagerduty"
    payload = {
        "event": "incident.trigger",
        "incident": {
            "title": title,
            "service": {"summary": service},
            "urgency": urgency,
            "created_at": "2026-08-29T18:00:00Z",
        },
    }
    print(f"📡 Sending PagerDuty Webhook to {endpoint}...")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(endpoint, json=payload)
            print(f"Status: {resp.status_code}")
            print(resp.json())
    except Exception as e:
        print(f"Error connecting to daemon: {e}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    trigger_pagerduty_alert(daemon_url=url)
