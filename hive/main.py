"""HIVE OS entry point."""

import asyncio
import sys
from hive.cli import HiveCLI


async def _cleanup_browser():
    """Close any open browser windows."""
    try:
        from hive.browser.pool import get_pool
        pool = get_pool()
        await pool.close_all()
    except Exception:
        pass


def main():
    """Run HIVE OS."""
    cli = HiveCLI()
    try:
        asyncio.run(cli.start())
    except KeyboardInterrupt:
        asyncio.run(_cleanup_browser())
        print("\nBye.")
        sys.exit(0)
    except SystemExit:
        asyncio.run(_cleanup_browser())


if __name__ == "__main__":
    main()
