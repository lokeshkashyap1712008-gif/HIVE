"""HIVE OS entry point."""

import asyncio
import sys
from hive.cli import HiveCLI


def main():
    """Run HIVE OS."""
    cli = HiveCLI()
    try:
        asyncio.run(cli.start())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
