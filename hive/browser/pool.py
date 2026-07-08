"""Browser pool — keeps a persistent Playwright browser alive across tool calls.

Uses a PERSISTENT browser profile (user_data_dir) instead of a throwaway
context. This is critical for real-world logins (Spotify, Google, etc.):
  * Cookies + localStorage persist across runs, so once you log in you STAY
    logged in and skip the login form entirely next time.
  * A stable browser fingerprint/history dramatically lowers the bot score
    that triggers CAPTCHAs and "unusual activity" challenges.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

_STEALTH_INIT_JS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
"""

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--start-maximized",
    "--autoplay-policy=no-user-gesture-required",
]

_CONTEXT_KWARGS = {
    "viewport": {"width": 1920, "height": 1080},
    "screen": {"width": 1920, "height": 1080},
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "locale": "en-US",
    "timezone_id": "America/New_York",
}


def _base_dir() -> Path:
    # Single source of truth: use the same HIVE_HOME as the rest of HIVE so
    # the browser profile lives in one stable place regardless of cwd.
    try:
        from hive.config import HIVE_HOME
        return Path(HIVE_HOME)
    except Exception:
        home = os.environ.get("HIVE_HOME")
        return Path(home).expanduser() if home else (Path.home() / ".hive")


def _find_chrome_user_data_dir() -> Path | None:
    """Locate the real Chrome 'User Data' directory for this OS/user."""
    from hive.config import HIVE_CHROME_USER_DATA_DIR

    if HIVE_CHROME_USER_DATA_DIR:
        p = Path(HIVE_CHROME_USER_DATA_DIR).expanduser()
        return p if p.exists() else None

    candidates = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Google" / "Chrome" / "User Data")
            candidates.append(Path(local) / "Microsoft" / "Edge" / "User Data")
    else:
        home = Path.home()
        # macOS
        candidates.append(home / "Library" / "Application Support" / "Google" / "Chrome")
        # Linux
        candidates.append(home / ".config" / "google-chrome")
        candidates.append(home / ".config" / "chromium")

    for c in candidates:
        if c.exists():
            return c
    return None


def _snapshot_real_chrome_profile(dest_profile_dir: Path) -> bool:
    """Copy the user's real Chrome login state into dest_profile_dir (read-only
    snapshot of the original). Returns True if a usable snapshot was created.

    Only the files needed for login state are copied (cookies, Local State key,
    login data, preferences) — NOT the whole cache — to keep it fast and avoid
    locked files. The original Chrome profile is never modified.
    """
    from hive.config import HIVE_CHROME_SOURCE_PROFILE

    user_data = _find_chrome_user_data_dir()
    if not user_data:
        return False

    src_profile = user_data / HIVE_CHROME_SOURCE_PROFILE
    if not src_profile.exists():
        return False

    # If we've already snapshotted, don't clobber (keeps any new logins HIVE made)
    marker = dest_profile_dir / ".chrome_snapshot_done"
    if marker.exists():
        return True

    dest_default = dest_profile_dir / "Default"
    dest_default.mkdir(parents=True, exist_ok=True)

    # "Local State" (top-level) holds the DPAPI-wrapped cookie encryption key —
    # required to decrypt the copied cookies on Windows.
    try:
        ls = user_data / "Local State"
        if ls.exists():
            shutil.copy2(ls, dest_profile_dir / "Local State")
    except Exception:
        pass

    # Per-profile files that carry login state
    for name in ["Cookies", "Login Data", "Web Data", "Preferences",
                 "Network/Cookies", "Local Storage", "Session Storage"]:
        src = src_profile / name
        dst = dest_default / name
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except Exception:
            # Locked file (Chrome open) — skip; partial snapshot still helps
            continue

    marker.write_text("ok", encoding="utf-8")
    return True


class BrowserPool:
    """Singleton pool of persistent Playwright browser profiles."""

    def __init__(self):
        self._playwright = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}
        self._default_session = "default"
        base = _base_dir()
        self._profiles_dir = base / "profiles"
        self._sessions_dir = base / "sessions"  # exported storage_state JSON (portable)
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_playwright(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def get_page(self, session_id: str = None) -> Page:
        """Get or create a page for this session (persistent profile)."""
        sid = session_id or self._default_session
        if sid in self._pages and not self._pages[sid].is_closed():
            return self._pages[sid]
        return await self._create_session(sid)

    async def _create_session(self, sid: str, profile_name: str = None) -> Page:
        """Launch a persistent browser context for the given profile."""
        await self._ensure_playwright()

        profile = profile_name or sid
        user_data_dir = self._profiles_dir / profile
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Optionally seed this profile with the user's real Chrome login state
        from hive.config import HIVE_CHROME_PROFILE_REUSE
        if HIVE_CHROME_PROFILE_REUSE:
            try:
                if _snapshot_real_chrome_profile(user_data_dir):
                    logger.info("Seeded browser profile with real Chrome login state")
            except Exception as e:
                logger.warning("Chrome profile snapshot skipped: %s", e)

        from hive.config import HIVE_BROWSER_CHANNEL
        launch_kwargs = dict(_CONTEXT_KWARGS)
        # Use the real installed Chrome when requested (better fingerprint on
        # hard sites). Falls back to bundled Chromium if Chrome isn't found.
        if HIVE_BROWSER_CHANNEL and HIVE_BROWSER_CHANNEL != "chromium":
            launch_kwargs["channel"] = HIVE_BROWSER_CHANNEL

        try:
            context = await self._playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=False,
                args=_LAUNCH_ARGS,
                # Required for Spotify/Widevine DRM — Playwright disables component
                # updates by default which blocks protected content playback.
                ignore_default_args=["--disable-component-update"],
                **launch_kwargs,
            )
        except Exception as e:
            if "channel" in launch_kwargs:
                logger.warning("Chrome channel '%s' unavailable (%s); using bundled Chromium",
                               launch_kwargs["channel"], e)
                launch_kwargs.pop("channel", None)
                context = await self._playwright.chromium.launch_persistent_context(
                    str(user_data_dir),
                    headless=False,
                    args=_LAUNCH_ARGS,
                    ignore_default_args=["--disable-component-update"],
                    **launch_kwargs,
                )
            else:
                raise

        stealth = Stealth()
        try:
            await stealth.apply_stealth_async(context)
        except Exception:
            pass
        await context.add_init_script(_STEALTH_INIT_JS)

        page = context.pages[0] if context.pages else await context.new_page()

        self._contexts[sid] = context
        self._pages[sid] = page
        return page

    async def save_session(self, name: str, session_id: str = None) -> str:
        """Export current cookies+storage to a portable JSON file.

        (The persistent profile already keeps you logged in automatically;
        this export is for backup/portability and the list/load API.)
        """
        sid = session_id or self._default_session
        if sid not in self._contexts:
            return ""

        context = self._contexts[sid]
        try:
            storage = await context.storage_state()
        except Exception:
            return ""

        file_path = self._sessions_dir / f"{name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(storage, f, indent=2)
        return str(file_path)

    async def load_session(self, name: str) -> bool:
        """Restore cookies from a saved export into the live persistent context.

        Returns True if either a saved export was applied OR the named
        persistent profile already exists (i.e. we're already logged in).
        """
        file_path = self._sessions_dir / f"{name}.json"
        profile_exists = (self._profiles_dir / name).exists()

        # Ensure a live context exists to inject cookies into
        await self.get_page()

        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    storage = json.load(f)
                cookies = storage.get("cookies", [])
                if cookies:
                    await self._contexts[self._default_session].add_cookies(cookies)
                return True
            except Exception:
                return profile_exists

        return profile_exists

    async def list_sessions(self) -> list[str]:
        names = {f.stem for f in self._sessions_dir.glob("*.json")}
        names.update(p.name for p in self._profiles_dir.iterdir() if p.is_dir())
        return sorted(names)

    async def delete_session(self, name: str) -> bool:
        deleted = False
        file_path = self._sessions_dir / f"{name}.json"
        if file_path.exists():
            file_path.unlink()
            deleted = True
        profile_path = self._profiles_dir / name
        if profile_path.exists() and name != self._default_session:
            shutil.rmtree(profile_path, ignore_errors=True)
            deleted = True
        return deleted

    async def close_session(self, session_id: str = None):
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

    async def close_all(self):
        for sid in list(self._contexts.keys()):
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
