"""Human-in-the-loop prompts — CLI registers handlers, workers call these."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

Prompt2FA = Callable[[str, str], Awaitable[Optional[str]]]
PromptCheckout = Callable[[float, str, str], Awaitable[bool]]
PromptCaptcha = Callable[[str, str], Awaitable[bool]]

_handlers: dict = {}


def register_handlers(
    prompt_2fa: Optional[Prompt2FA] = None,
    prompt_checkout_confirm: Optional[PromptCheckout] = None,
    prompt_captcha_handoff: Optional[PromptCaptcha] = None,
) -> None:
    if prompt_2fa:
        _handlers["prompt_2fa"] = prompt_2fa
    if prompt_checkout_confirm:
        _handlers["prompt_checkout_confirm"] = prompt_checkout_confirm
    if prompt_captcha_handoff:
        _handlers["prompt_captcha_handoff"] = prompt_captcha_handoff


def clear_handlers() -> None:
    _handlers.clear()


async def prompt_2fa_code(site: str, message: str = "") -> Optional[str]:
    """Ask user for 2FA/verification code. Returns None if no handler or cancelled."""
    fn = _handlers.get("prompt_2fa")
    if not fn:
        return None
    try:
        return await fn(site, message)
    except Exception as e:
        logger.warning("2FA prompt failed: %s", e)
        return None


async def prompt_checkout_confirm(
    amount: float, merchant: str, url: str = "",
) -> Optional[bool]:
    """Ask user to confirm purchase. None = no handler."""
    fn = _handlers.get("prompt_checkout_confirm")
    if not fn:
        return None
    try:
        return await fn(amount, merchant, url)
    except Exception as e:
        logger.warning("Checkout confirm prompt failed: %s", e)
        return None


async def prompt_captcha_handoff(site: str, url: str = "") -> bool:
    """Ask user to solve CAPTCHA in browser. False if cancelled or no handler."""
    fn = _handlers.get("prompt_captcha_handoff")
    if not fn:
        return False
    try:
        return await fn(site, url)
    except Exception as e:
        logger.warning("CAPTCHA handoff prompt failed: %s", e)
        return False
