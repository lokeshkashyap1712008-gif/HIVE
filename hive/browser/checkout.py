"""Guarded browser checkout flow with spending caps and human confirmation."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from hive.browser.vault import get_card, get_card_sensitive_data
from hive.core.audit_logger import audit_logger

logger = logging.getLogger(__name__)

SPEND_LOG = Path(os.environ.get("HIVE_HOME", Path.home() / ".hive")) / "checkout_spend.json"

# Config from env
MAX_ORDER_AMOUNT = float(os.environ.get("HIVE_MAX_ORDER_AMOUNT", "500"))
MAX_DAILY_SPEND = float(os.environ.get("HIVE_MAX_DAILY_SPEND", "1000"))
CHECKOUT_AUTONOMOUS = os.environ.get("HIVE_CHECKOUT_AUTONOMOUS", "false").lower() in ("1", "true", "yes")
ALLOWED_MERCHANTS = [
    m.strip().lower()
    for m in os.environ.get("HIVE_CHECKOUT_ALLOWED_MERCHANTS", "").split(",")
    if m.strip()
]


def _load_spend_log() -> dict:
    if SPEND_LOG.exists():
        try:
            return json.loads(SPEND_LOG.read_text())
        except Exception:
            pass
    return {"daily": {}, "orders": []}


def _save_spend_log(data: dict) -> None:
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    SPEND_LOG.write_text(json.dumps(data, indent=2))


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_daily_spend() -> float:
    log = _load_spend_log()
    return float(log.get("daily", {}).get(_today_key(), 0))


def check_spending_limits(amount: float, merchant_domain: str) -> tuple[bool, str]:
    """Validate order against caps and merchant allowlist."""
    if amount <= 0:
        return False, "Invalid order amount"

    if amount > MAX_ORDER_AMOUNT:
        return False, f"Order amount ${amount:.2f} exceeds per-order cap ${MAX_ORDER_AMOUNT:.2f}"

    daily = get_daily_spend()
    if daily + amount > MAX_DAILY_SPEND:
        return False, f"Daily spend cap exceeded (${daily:.2f} + ${amount:.2f} > ${MAX_DAILY_SPEND:.2f})"

    if ALLOWED_MERCHANTS:
        domain = merchant_domain.lower().strip()
        if not any(domain == m or domain.endswith("." + m) for m in ALLOWED_MERCHANTS):
            return False, f"Merchant '{domain}' not in allowlist: {ALLOWED_MERCHANTS}"

    return True, "OK"


def record_order(amount: float, merchant: str, status: str, metadata: Optional[dict] = None) -> None:
    log = _load_spend_log()
    today = _today_key()
    log.setdefault("daily", {})[today] = log.get("daily", {}).get(today, 0) + amount
    log.setdefault("orders", []).append({
        "amount": amount,
        "merchant": merchant,
        "status": status,
        "timestamp": time.time(),
        "metadata": metadata or {},
    })
    # Keep last 100 orders
    log["orders"] = log["orders"][-100:]
    _save_spend_log(log)


def extract_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.hostname or "").lower()


def parse_amount_from_text(text: str) -> Optional[float]:
    """Try to extract a dollar amount from page text."""
    patterns = [
        r"(?:total|order total|amount due|pay now)[:\s]*\$?([\d,]+\.?\d*)",
        r"\$\s*([\d,]+\.\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


async def run_checkout(
    task: str,
    url: Optional[str] = None,
    amount: Optional[float] = None,
    card_id: Optional[str] = None,
    human_confirmed: bool = False,
) -> dict:
    """Execute guarded checkout via browser_agent loop.

    Stops before final purchase unless HIVE_CHECKOUT_AUTONOMOUS=true or human_confirmed=True.
    """
    from hive.agents.workers.browser_agent import run as browser_run

    merchant = extract_domain(url or task)
    from hive.playbooks import record_success, site_key
    sk = site_key(merchant)
    audit_logger.log(
        "checkout_started",
        f"Checkout initiated for {merchant}",
        agents_affected=["payment_agent"],
        metadata={"task": task[:200], "url": url, "amount": amount},
    )

    # Pre-flight spending check if amount known
    if amount is not None:
        ok, reason = check_spending_limits(amount, merchant)
        if not ok:
            audit_logger.log("checkout_blocked", reason, metadata={"amount": amount, "merchant": merchant})
            return {"status": "blocked", "reason": reason}

    card = get_card(card_id)
    if not card:
        return {
            "status": "error",
            "reason": "No payment card in vault. Use vault_store_card first.",
        }

    card_data = get_card_sensitive_data(card.get("id"))
    sensitive = {k: v for k, v in card_data.items() if v}

    # Build checkout task for browser agent
    checkout_instructions = f"""
CHECKOUT TASK (payment_agent):
1. Navigate to the checkout/payment page
2. Fill shipping/billing forms if present
3. Enter card details using these placeholders (NEVER type raw numbers in reasoning):
   - Card number: ${{card_number}}
   - Expiry: ${{card_expiry}}
   - CVV: ${{card_cvv}}
   - Name on card: ${{card_name}}
   - Billing ZIP: ${{billing_zip}}
4. Review the order total
5. {"Click Place Order / Pay Now to complete purchase" if (CHECKOUT_AUTONOMOUS or human_confirmed) else "STOP before clicking Place Order / Pay Now / Complete Purchase — take screenshot and report total"}
6. Report final status

Original task: {task}
"""
    if url:
        checkout_instructions += f"\nStart URL: {url}"

    context = {
        "credentials": sensitive,
        "sensitive_data": sensitive,
        "checkout_mode": True,
        "human_confirmed": human_confirmed or CHECKOUT_AUTONOMOUS,
    }

    result = await browser_run(checkout_instructions, context=context)

    # Interactive confirm prompt when checkout is ready
    if (
        not CHECKOUT_AUTONOMOUS
        and not human_confirmed
        and result.get("status") == "pending_confirmation"
    ):
        from hive.interactive import prompt_checkout_confirm
        display_amount = amount or 0.0
        approved = await prompt_checkout_confirm(display_amount, merchant, url or "")
        if approved is True:
            audit_logger.log(
                "checkout_confirmed",
                f"User confirmed purchase at {merchant}",
                metadata={"amount": display_amount, "merchant": merchant},
            )
            return await confirm_checkout(task=task, url=url, amount=amount, card_id=card_id)
        if approved is False:
            return {
                "status": "cancelled",
                "message": "Purchase cancelled by user.",
                "merchant": merchant,
                "amount": amount,
            }
        # No handler — return pending for manual confirm
        audit_logger.log(
            "checkout_pending_confirmation",
            "Checkout ready — awaiting human approval",
            metadata={"merchant": merchant, "browser_result": result.get("status")},
        )
        return {
            "status": "pending_confirmation",
            "message": "Checkout form filled. Confirm to complete purchase.",
            "merchant": merchant,
            "amount": amount,
            "browser_result": result,
            "requires_human": True,
        }

    if result.get("status") == "pending_confirmation":
        return {
            "status": "pending_confirmation",
            "message": result.get("message", "Review checkout in browser."),
            "merchant": merchant,
            "amount": amount,
            "browser_result": result,
            "requires_human": True,
        }

    # Record spend on success
    final_amount = amount
    if final_amount and result.get("status") == "completed":
        record_order(final_amount, merchant, "completed")
        record_success(
            sk,
            flow="checkout",
            last_url=result.get("url") or url,
            trust_delta=12,
            note="checkout_completed",
        )
        audit_logger.log(
            "checkout_completed",
            f"Order placed at {merchant} for ${final_amount:.2f}",
            metadata={"merchant": merchant, "amount": final_amount},
        )

    return {
        "status": result.get("status", "unknown"),
        "merchant": merchant,
        "amount": final_amount,
        "browser_result": result,
    }


async def confirm_checkout(
    task: str,
    url: Optional[str] = None,
    amount: Optional[float] = None,
    card_id: Optional[str] = None,
) -> dict:
    """Place order after human confirmation."""
    if amount is not None:
        merchant = extract_domain(url or task)
        ok, reason = check_spending_limits(amount, merchant)
        if not ok:
            return {"status": "blocked", "reason": reason}

    return await run_checkout(
        task=task,
        url=url,
        amount=amount,
        card_id=card_id,
        human_confirmed=True,
    )
