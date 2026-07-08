import asyncio
from hive.browser.pool import get_pool


async def main():
    pool = get_pool()
    page = await pool.get_page()
    await page.goto("https://open.spotify.com", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)

    # Click playlist row in Your Library
    row = page.locator('[data-testid="rootlist-item-row"], [data-testid="card"]').filter(has_text="Second").first
    print("rows:", await page.locator('[data-testid="rootlist-item-row"]').count())
    if await row.count():
        await row.click(timeout=5000)
        await page.wait_for_timeout(5000)
        print("URL:", page.url)

    # All play-ish buttons on page
    buttons = await page.evaluate("""() => Array.from(document.querySelectorAll('button[data-testid="play-button"], button[aria-label*="Shuffle"], button[aria-label*="Play"]')).slice(0,15).map(b => ({aria: b.getAttribute('aria-label'), testid: b.getAttribute('data-testid'), disabled: b.disabled}))""")
    for b in buttons:
        print(b)

    # Click first main play/shuffle
    main_play = page.locator('main button[data-testid="play-button"]').first
    if await main_play.count():
        print("clicking main play:", await main_play.get_attribute("aria-label"))
        await main_play.click(timeout=8000)
        await page.wait_for_timeout(8000)

    pp = page.locator('[data-testid="control-button-playpause"]').first
    print("playpause:", await pp.get_attribute("aria-label"), "disabled:", await pp.is_disabled())
    title = page.locator('[data-testid="context-item-info-title"]').first
    if await title.count():
        print("track:", await title.text_content())

    await page.screenshot(path="C:/Users/lokes/hive/.hive/screenshots/spotify_second_page.png")
    await pool.close_session()


asyncio.run(main())
