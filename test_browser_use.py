"""Test script for Browser Use worker."""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

async def test_browser_use():
    """Test browser use with a simple task."""
    from hive.agents.workers.browser_use_worker import _run_browser_use_task

    print("Testing Browser Use worker...")
    print("This will open a browser window and navigate to a test page.")
    print("Press Ctrl+C to cancel.\n")

    try:
        result = await _run_browser_use_task(
            task="Go to https://example.com and tell me what the page says",
            headless=False,
            max_steps=5,
        )
        print(f"\nResult:\n{result}")
        return True
    except Exception as e:
        print(f"\nError: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_browser_use())
    sys.exit(0 if success else 1)
