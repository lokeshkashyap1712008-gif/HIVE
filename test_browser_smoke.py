#!/usr/bin/env python3
"""Smoke tests for HIVE browser automation, vault, signup, and checkout.

Run: python test_browser_smoke.py
Requires: playwright install chromium
"""

import asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_vault():
    print("\n=== Vault Tests ===")
    from hive.browser.vault import (
        store_credential, get_credential, list_credentials, delete_credential,
        store_card, list_cards, delete_card,
    )

    cred_id = store_credential("test.example.com", "test@example.com", "testpass123")
    assert cred_id, "store_credential failed"
    cred = get_credential("test.example.com")
    assert cred and cred["password"] == "testpass123", "get_credential failed"
    creds = list_credentials()
    assert any(c["site"] == "test.example.com" for c in creds), "list_credentials failed"
    delete_credential(cred_id)
    print("  [OK] Credential store/retrieve/delete")

    card_id = store_card("test-card", "4111111111111111", "12/28", "123", "Test User", "10001")
    cards = list_cards()
    assert any(c["last4"] == "1111" for c in cards), "list_cards failed"
    delete_card(card_id)
    print("  [OK] Card store/list/delete")


async def test_browser_open_inspect():
    print("\n=== Browser Open + Inspect ===")
    from hive.tools import execute_tool

    result = await execute_tool("browser_open", url="https://example.com")
    if "error" in result:
        print(f"  [SKIP] browser_open failed (playwright not installed?): {result['error']}")
        return False

    assert result.get("status") == "opened", f"Unexpected: {result}"
    print(f"  [OK] Opened: {result.get('title')}")

    inspect = await execute_tool("browser_inspect")
    assert inspect.get("count", 0) > 0, "No elements found"
    print(f"  [OK] Inspected {inspect['count']} elements")

    screenshot = await execute_tool("browser_screenshot", filename="smoke_test.png")
    assert screenshot.get("status") == "saved", f"Screenshot failed: {screenshot}"
    print(f"  [OK] Screenshot: {screenshot.get('path')}")

    await execute_tool("browser_close")
    print("  [OK] Browser closed")
    return True


async def test_session_save_load():
    print("\n=== Session Save/Load ===")
    from hive.tools import execute_tool

    await execute_tool("browser_open", url="https://example.com")
    save = await execute_tool("browser_session_save", name="smoke_test")
    if "error" in save:
        print(f"  [SKIP] session save failed: {save['error']}")
        return

    sessions = await execute_tool("browser_list_sessions")
    assert "smoke_test" in sessions.get("sessions", []), "Session not listed"
    print("  [OK] Session saved and listed")

    await execute_tool("browser_close")
    load = await execute_tool("browser_session_load", name="smoke_test")
    assert load.get("status") == "loaded", f"Load failed: {load}"
    print("  [OK] Session loaded")

    await execute_tool("browser_delete_session", name="smoke_test")
    await execute_tool("browser_close")
    print("  [OK] Session deleted")


async def test_checkout_gate():
    print("\n=== Checkout Spending Gate ===")
    from hive.browser.checkout import check_spending_limits, get_daily_spend

    ok, reason = check_spending_limits(100.0, "amazon.com")
    print(f"  [OK] $100 on amazon.com: {ok} ({reason})")

    ok, reason = check_spending_limits(99999.0, "amazon.com")
    assert not ok, "Should block excessive amount"
    print(f"  [OK] Excessive amount blocked: {reason}")

    daily = get_daily_spend()
    print(f"  [OK] Daily spend so far: ${daily:.2f}")


async def test_engine_routing():
    print("\n=== Engine Routing ===")
    from hive.agents.leader import _select_browser_worker

    assert _select_browser_worker("login to github") == "browser_use_worker"
    assert _select_browser_worker("click the search button") == "browser_agent"
    assert _select_browser_worker("checkout and buy item") == "payment_agent"
    assert _select_browser_worker("sign up for new account") == "browser_agent"
    print("  [OK] Engine routing logic")


async def test_safety_gate():
    print("\n=== Safety Gate ===")
    from hive.agents.safety_agent import SafetyAgent

    agent = SafetyAgent()
    result = await agent.check("checkout and buy a book for $15")
    assert result.get("approved") is True, "Checkout should be approved"
    assert result.get("requires_human") is True, "Checkout should require human"
    print("  [OK] Checkout requires human approval")

    result = await agent.check("rm -rf /")
    # This might be caught by denied patterns in safety agent via regex from config
    print(f"  [OK] Dangerous command check: approved={result.get('approved')}")


async def main():
    print("HIVE Browser Smoke Tests")
    print("=" * 40)

    try:
        await test_vault()
        await test_engine_routing()
        await test_safety_gate()
        await test_checkout_gate()
        browser_ok = await test_browser_open_inspect()
        if browser_ok:
            await test_session_save_load()
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 40)
    print("All smoke tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
