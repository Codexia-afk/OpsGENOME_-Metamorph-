#!/usr/bin/env python3
"""Checkout Service Payment Pipeline."""

import sys


def parse_customer_payload(payload: dict) -> dict:
    """Validate customer and route to payment gateway initialization."""
    return init_payment_gateway(payload["gateway_config"])


def init_payment_gateway(gateway_config: dict) -> str:
    """Initialize stripe/adyen gateway connection.

    Fails with KeyError at line 17 because 'api_secret_key' is missing from config.
    """
    secret_key = gateway_config["api_secret_key"]
    return f"Gateway initialized with secret length {len(secret_key)}"


def main() -> None:
    order_context = {
        "order_id": "ORD-2026-9811",
        "customer_id": "CUST-4410",
        "gateway_config": {
            "provider": "stripe",
            "endpoint": "https://api.stripe.com/v1",
            "timeout_seconds": 30,
            # Missing required 'api_secret_key' key planted deliberately
        },
    }
    parse_customer_payload(order_context)


if __name__ == "__main__":
    main()
