"""HIVE — Payment Agent Worker — guarded browser checkout."""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _extract_url(task: str) -> Optional[str]:
    m = re.search(r"https?://[^\s]+", task)
    return m.group(0).rstrip(".,;") if m else None


def _extract_amount(task: str) -> Optional[float]:
    patterns = [
        r"\$\s*([\d,]+\.?\d*)",
        r"([\d,]+\.?\d*)\s*(?:usd|dollars?)",
        r"amount[:\s]+\$?([\d,]+\.?\d*)",
    ]
    for pat in patterns:
        m = re.search(pat, task, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


async def run(description: str, context: dict = None) -> dict:
    """Run guarded browser checkout."""
    from hive.browser.checkout import run_checkout, confirm_checkout, check_spending_limits, extract_domain

    context = context or {}
    url = context.get("url") or _extract_url(description)
    amount = context.get("amount") or _extract_amount(description)
    card_id = context.get("card_id")
    human_confirmed = context.get("human_confirmed", False)

    # Explicit confirm command
    if any(kw in description.lower() for kw in ["confirm purchase", "confirm checkout", "place order", "complete purchase"]):
        return await confirm_checkout(
            task=description,
            url=url,
            amount=amount,
            card_id=card_id,
        )

    merchant = extract_domain(url or description)
    if amount is not None:
        ok, reason = check_spending_limits(amount, merchant)
        if not ok:
            return {"status": "blocked", "reason": reason, "agent": "payment_agent"}

    return await run_checkout(
        task=description,
        url=url,
        amount=amount,
        card_id=card_id,
        human_confirmed=human_confirmed,
    )
