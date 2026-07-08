import asyncio
from hive.browser.pool import get_pool


async def main():
    pool = get_pool()
    page = await pool.get_page()
    await page.goto("https://open.spotify.com/collection/tracks", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(6000)
    print("url:", page.url)
    info = await page.evaluate("""() => {
        const out = {play: [], links: [], h1: []};
        document.querySelectorAll('h1,h2').forEach(h => out.h1.push((h.textContent||'').trim().slice(0,50)));
        document.querySelectorAll('button[data-testid="play-button"]').forEach(b => out.play.push({al: b.getAttribute('aria-label'), dis: b.disabled}));
        document.querySelectorAll('a[href]').forEach(a => {
            const h = a.getAttribute('href')||'';
            if (h.includes('playlist') || h.includes('collection')) out.links.push({h, t:(a.textContent||'').trim().slice(0,30)});
        });
        return out;
    }""")
    print("h1:", info["h1"][:5])
    print("play:", info["play"][:5])
    print("links:", info["links"][:8])

    if info["play"]:
        await page.locator('button[data-testid="play-button"]').first.click(timeout=5000)
        await page.wait_for_timeout(8000)
        btn = page.locator('[data-testid="control-button-playpause"]').first
        print("bar:", await btn.is_disabled(), await btn.get_attribute("aria-label"))
        if await page.locator('[data-testid="context-item-info-title"]').count():
            print("track:", await page.locator('[data-testid="context-item-info-title"]').first.text_content())

    await pool.close_session()


asyncio.run(main())
