"""Engine routing tests."""

from hive.agents.leader import _select_browser_worker, _is_browser_task, _is_checkout_task


def test_simple_click_uses_playwright():
    assert _select_browser_worker("click the search button on the page") == "browser_agent"


def test_login_uses_browser_agent():
    assert _select_browser_worker("login to github with email and password") == "browser_agent"


def test_checkout_uses_payment_agent():
    assert _select_browser_worker("checkout and buy the backpack") == "payment_agent"


def test_signup_uses_browser_agent():
    assert _select_browser_worker("sign up for a new account") == "browser_agent"


def test_browser_task_detection():
    assert _is_browser_task("navigate to example.com")
    assert _is_checkout_task("add to cart and checkout")
