"""Checkout spending gate tests."""

import pytest
from hive.browser import checkout


@pytest.fixture(autouse=True)
def reset_spend_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_HOME", str(tmp_path))
    checkout.SPEND_LOG = tmp_path / "checkout_spend.json"
    monkeypatch.setenv("HIVE_MAX_ORDER_AMOUNT", "500")
    monkeypatch.setenv("HIVE_MAX_DAILY_SPEND", "1000")
    monkeypatch.delenv("HIVE_CHECKOUT_ALLOWED_MERCHANTS", raising=False)
    checkout.MAX_ORDER_AMOUNT = 500.0
    checkout.MAX_DAILY_SPEND = 1000.0
    checkout.ALLOWED_MERCHANTS = []
    yield


def test_allows_normal_order():
    ok, reason = checkout.check_spending_limits(29.99, "saucedemo.com")
    assert ok is True
    assert reason == "OK"


def test_blocks_excessive_order():
    ok, reason = checkout.check_spending_limits(9999.0, "amazon.com")
    assert ok is False
    assert "per-order cap" in reason


def test_merchant_allowlist():
    checkout.ALLOWED_MERCHANTS = ["amazon.com"]
    ok, _ = checkout.check_spending_limits(10.0, "amazon.com")
    assert ok is True
    ok, reason = checkout.check_spending_limits(10.0, "evil.com")
    assert ok is False
    assert "allowlist" in reason


def test_daily_spend_tracking():
    checkout.record_order(50.0, "test.com", "completed")
    assert checkout.get_daily_spend() == 50.0


def test_extract_domain():
    assert checkout.extract_domain("https://www.amazon.com/cart") == "www.amazon.com"
