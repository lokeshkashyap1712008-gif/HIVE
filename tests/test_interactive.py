"""Interactive prompt tests."""

import pytest
from hive.interactive import register_handlers, clear_handlers, prompt_2fa_code, prompt_checkout_confirm


@pytest.fixture(autouse=True)
def _clear():
    clear_handlers()
    yield
    clear_handlers()


@pytest.mark.asyncio
async def test_prompt_2fa_with_handler():
    async def mock_2fa(site, msg):
        return "123456"

    register_handlers(prompt_2fa=mock_2fa)
    code = await prompt_2fa_code("github.com", "enter code")
    assert code == "123456"


@pytest.mark.asyncio
async def test_prompt_2fa_no_handler_returns_none():
    assert await prompt_2fa_code("x.com") is None


@pytest.mark.asyncio
async def test_checkout_confirm_handler():
    async def mock_confirm(amount, merchant, url):
        return amount < 100

    register_handlers(prompt_checkout_confirm=mock_confirm)
    assert await prompt_checkout_confirm(50.0, "shop.com") is True
    assert await prompt_checkout_confirm(500.0, "shop.com") is False
