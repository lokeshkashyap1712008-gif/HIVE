"""Browser pool — keeps Playwright browsers alive for reuse across tool calls."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth


class BrowserPool:
    """Singleton pool of Playwright browser sessions."""

    def __init__(self):
        self._playwright = None
        self._browsers: dict[str, Browser] = {}
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}
        self._default_session = "default"
        self._sessions_dir = Path(".hive") / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_playwright(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def get_page(self, session_id: str = None) -> Page:
        """Get or create a page for this session."""
        sid = session_id or self._default_session
        if sid in self._pages and not self._pages[sid].is_closed():
            return self._pages[sid]
        return await self._create_session(sid)

    async def _create_session(self, sid: str, storage_state: str = None) -> Page:
        """Create a new browser + context + page with stealth mode."""
        await self._ensure_playwright()
        
        browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080",
            ],
        )
        
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        
        if storage_state and Path(storage_state).exists():
            context_args["storage_state"] = storage_state
        
        context = await browser.new_context(**context_args)
        
        # Apply stealth patches
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        
        # Additional stealth patches for aggressive bot detection
        await context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            
            // Override navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Override navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Override chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        page = await context.new_page()
        self._browsers[sid] = browser
        self._contexts[sid] = context
        self._pages[sid] = page
        return page

    async def save_session(self, name: str, session_id: str = None) -> str:
        """Save current browser session to disk. Returns file path."""
        sid = session_id or self._default_session
        if sid not in self._contexts:
            return ""
        
        context = self._contexts[sid]
        storage = await context.storage_state()
        
        file_path = self._sessions_dir / f"{name}.json"
        with open(file_path, "w") as f:
            json.dump(storage, f, indent=2)
        
        return str(file_path)

    async def load_session(self, name: str) -> bool:
        """Load a saved browser session. Returns True if successful."""
        file_path = self._sessions_dir / f"{name}.json"
        if not file_path.exists():
            return False
        
        # Close existing session if any
        await self.close_session(self._default_session)
        
        # Create new session with saved state
        await self._create_session(self._default_session, str(file_path))
        return True

    async def list_sessions(self) -> list[str]:
        """List all saved session names."""
        return [f.stem for f in self._sessions_dir.glob("*.json")]

    async def delete_session(self, name: str) -> bool:
        """Delete a saved session. Returns True if deleted."""
        file_path = self._sessions_dir / f"{name}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def close_session(self, session_id: str = None):
        """Close a specific session."""
        sid = session_id or self._default_session
        if sid in self._pages:
            try:
                await self._pages[sid].close()
            except Exception:
                pass
            del self._pages[sid]
        if sid in self._contexts:
            try:
                await self._contexts[sid].close()
            except Exception:
                pass
            del self._contexts[sid]
        if sid in self._browsers:
            try:
                await self._browsers[sid].close()
            except Exception:
                pass
            del self._browsers[sid]

    async def close_all(self):
        """Close all sessions and stop Playwright."""
        for sid in list(self._browsers.keys()):
            await self.close_session(sid)
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


# Global singleton
_pool: BrowserPool | None = None


def get_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool
