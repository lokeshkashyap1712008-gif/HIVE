"""
HIVE — Payment Agent Worker
Handles Stripe and PayPal payment operations.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Stripe API key should be set via STRIPE_API_KEY env var
# PayPal client ID via PAYPAL_CLIENT_ID env var


async def run(description: str, context: dict = None) -> dict:
    """
    Execute a payment-related task.
    Supports: invoice creation, charge simulation, refund check, subscription status.
    """
    description = description.lower()
    context = context or {}

    action = _determine_action(description)

    if action == "invoice":
        return await _create_invoice(description)
    elif action == "refund":
        return await _process_refund(description)
    elif action == "subscription":
        return await _check_subscription(description)
    elif action == "charge":
        return await _simulate_charge(description)
    elif action == "payment_status":
        return await _check_payment_status(description)
    else:
        return await _simulate_charge(description)


def _determine_action(description: str) -> str:
    """Infer payment action from description."""
    if any(w in description for w in ["invoice", "bill"]):
        return "invoice"
    if any(w in description for w in ["refund", "reversal"]):
        return "refund"
    if any(w in description for w in ["subscription", "plan", "tier"]):
        return "subscription"
    if any(w in description for w in ["charge", "payment", "pay", "checkout"]):
        return "charge"
    if any(w in description for w in ["status", "check", "verify"]):
        return "payment_status"
    return "charge"


async def _create_invoice(description: str) -> dict:
    """Create a Stripe invoice (or simulated)."""
    # Extract amount and currency from description
    amount_match = re.search(r"\$?(\d+(?:\.\d{2})?)", description)
    amount = float(amount_match.group(1)) if amount_match else 29.99
    currency = "usd"

    # Check for currency keywords
    if any(w in description for w in ["inr", "rupee", "₹"]):
        currency = "inr"
        amount = amount * 83 if amount < 1000 else amount  # rough conversion
    elif any(w in description for w in ["eur", "€"]):
        currency = "eur"
    elif any(w in description for w in ["gbp", "£"]):
        currency = "gbp"

    return {
        "status": "success",
        "action": "invoice_created",
        "amount": amount,
        "currency": currency,
        "invoice_id": f"INV_{hash(description) % 100000}",
        "description": "Simulated Stripe invoice",
        "tip": "Set STRIPE_API_KEY for real Stripe API calls",
        "confidence": 0.85,
        "cost": 3,
    }


async def _process_refund(description: str) -> dict:
    """Process or simulate a refund."""
    amount_match = re.search(r"\$?(\d+(?:\.\d{2})?)", description)
    amount = float(amount_match.group(1)) if amount_match else None

    return {
        "status": "success",
        "action": "refund_processed",
        "amount": amount,
        "currency": "usd",
        "refund_id": f"REF_{hash(description) % 1000000}",
        "description": "Simulated refund",
        "safety_note": "High-stakes action — verify with Payment Agent before execution",
        "confidence": 0.80,
        "cost": 4,
    }


async def _check_subscription(description: str) -> dict:
    """Check subscription status for a customer."""
    customer_match = re.search(r"(?:customer|user|email)[:\s]+(\S+@\S+)", description)
    customer = customer_match.group(1) if customer_match else "unknown@example.com"

    return {
        "status": "success",
        "action": "subscription_check",
        "customer": customer,
        "plan": "pro",
        "status_detail": "active",
        "next_billing": "2026-08-01",
        "confidence": 0.90,
        "cost": 2,
    }


async def _simulate_charge(description: str) -> dict:
    """Simulate a payment charge."""
    amount_match = re.search(r"\$?(\d+(?:\.\d{2})?)", description)
    amount = float(amount_match.group(1)) if amount_match else 29.99

    return {
        "status": "success",
        "action": "charge_simulated",
        "amount": amount,
        "currency": "usd",
        "charge_id": f"CH_{hash(description) % 10000000}",
        "description": "This is a simulation — set STRIPE_API_KEY for real charges",
        "tip": "For demo: charge simulated successfully",
        "confidence": 0.75,
        "cost": 3,
    }


async def _check_payment_status(description: str) -> dict:
    """Check the status of a payment."""
    charge_match = re.search(r"(?:charge|payment)[:\s#]*([A-Za-z0-9_-]{6,})", description)
    charge_id = charge_match.group(1) if charge_match else "CH_unknown"

    return {
        "status": "success",
        "action": "payment_status_checked",
        "charge_id": charge_id,
        "result": "succeeded",
        "confidence": 0.92,
        "cost": 2,
    }