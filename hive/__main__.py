"""Allow running HIVE with: python -m hive"""
import asyncio
from hive.cli import HiveCLI

async def _cleanup_browser():
    """Close any open browser windows."""
    try:
        from hive.browser.pool import get_pool
        pool = get_pool()
        await pool.close_all()
    except Exception:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(HiveCLI().start())
    except KeyboardInterrupt:
        asyncio.run(_cleanup_browser())
    except SystemExit:
        asyncio.run(_cleanup_browser())
