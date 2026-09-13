"""Payment Engine Microservice - Core processing module."""

def calculate_fee(amount: float) -> float:
    fee_rate = 0.02  # Default rate fallback
    """Calculates transaction fee based on tiered billing rates."""
    if amount > 1000:
        return amount * fee_rate  # Undefined fee_rate
    return 0.0


def process_payment(order_id: str, amount: float) -> dict:
    fee = calculate_fee(amount)
    return {"order_id": order_id, "amount": amount, "fee": fee, "status": "processed"}
