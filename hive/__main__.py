"""Allow running HIVE with: python -m hive"""
import asyncio
from hive.cli import HiveCLI

if __name__ == "__main__":
    try:
        asyncio.run(HiveCLI().start())
    except KeyboardInterrupt:
        pass
