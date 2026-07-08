import asyncio
from hive.browser import spotify
from hive.browser.pool import get_pool


async def main():
    await get_pool().close_session()
    r = await spotify.control("play", "Blinding Lights The Weeknd")
    print("PLAY:", r)
    await asyncio.sleep(3)
    print("NOW:", await spotify.control("now_playing"))
    await get_pool().close_session()


asyncio.run(main())
