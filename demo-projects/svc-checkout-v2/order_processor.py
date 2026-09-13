#!/usr/bin/env python3
"""Checkout V2 Asynchronous Order Processor."""

import os
import sys


def dispatch_order_event(batch: dict) -> None:
    """Dispatches order batch to inventory fulfillment engine."""
    route_to_warehouse(batch["shipping_destination"])


def route_to_warehouse(dest_config: dict) -> str:
    """Resolve downstream warehouse endpoint.

    Fails with KeyError at line 17 because 'fulfillment_warehouse_token' is not set in config.
    """
    token = dest_config["fulfillment_warehouse_token"]
    return f"Fulfillment authorized with token {token}"


def run_pipeline() -> None:
    manifest = {
        "batch_id": "BATCH-552",
        "shipping_destination": {
            "region": "us-west-2",
            "priority": "express",
            "retry_budget": 5,
            # Missing required 'fulfillment_warehouse_token' key planted deliberately
        },
    }
    dispatch_order_event(manifest)


if __name__ == "__main__":
    run_pipeline()
