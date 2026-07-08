import asyncio
from hive.browser import spotify
from hive.browser.pool import get_pool


async def main():
    await get_pool().close_session()

    print("=== Looksmax playlist ===")
    p = await spotify.control("play_playlist", "Looksmax")
    print(p)

    await asyncio.sleep(5)

    print("\n=== Blinding Lights ===")
    s = await spotify.control("play", "Blinding Lights The Weeknd")
    print(s)

    await get_pool().close_session()


asyncio.run(main())
