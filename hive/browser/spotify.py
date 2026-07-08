"""HIVE — Spotify Web Player control.

Deterministic helpers for the Spotify web player (open.spotify.com), driven
through the shared browser pool (real Chrome, persistent logged-in profile).

These use Spotify's stable data-testid / aria-label selectors instead of
relying on the generic LLM agent to reverse-engineer the SPA every time, so
"play X" is reliable. Requires the pool profile to be logged into Spotify.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from urllib.parse import quote

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://open.spotify.com/search/{q}"

# JS that scores every "Play <name>" button against the query and marks the
# best one with data-hive-play="1". Sidebar/library buttons are excluded so we
# don't accidentally play one of the user's playlists.
_LIST_SIDEBAR_PLAYLISTS_JS = r"""
() => {
    const inSidebar = el => !!el.closest('aside, nav, [data-testid="left-sidebar"], [aria-label="Your Library"]');
    const names = [];
    const seen = new Set();
    document.querySelectorAll('button[aria-label^="Play "], button[aria-label^="play "]').forEach(btn => {
        const r = btn.getBoundingClientRect();
        if (!r.width && !r.height) return;
        if (!inSidebar(btn)) return;
        const name = btn.getAttribute('aria-label').slice(5).trim();
        if (!name || seen.has(name.toLowerCase())) return;
        seen.add(name.toLowerCase());
        names.push(name);
    });
    return names;
}
"""

_RESOLVE_PLAYLIST_ID_JS = r"""
(query) => {
    const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean).join(' ');
    const q = norm(query);
    const qTokens = new Set(q.split(' ').filter(Boolean));

    let best = null;
    let bestScore = -1;
    document.querySelectorAll('[aria-describedby*="spotify:playlist"]').forEach(btn => {
        const hint = btn.getAttribute('aria-describedby') || '';
        const m = hint.match(/spotify:playlist:([A-Za-z0-9]+)/);
        if (!m) return;

        let name = '';
        const labelled = btn.getAttribute('aria-labelledby') || '';
        for (const id of labelled.split(/\s+/)) {
            const el = document.getElementById(id);
            if (el && id.includes('listrow-title')) {
                name = (el.textContent || '').trim();
                break;
            }
        }
        if (!name) {
            const row = btn.closest('[data-testid="rootlist-item-row"], [role="gridcell"], [role="row"]');
            name = ((row?.textContent || btn.textContent || '').split('\n')[0] || '').trim();
        }
        const n = norm(name);
        if (!n) return;

        let score = 0;
        if (n === q) score = 100;
        else if (n.includes(q) || q.includes(n)) score = 85;
        else {
            let overlap = 0;
            for (const t of n.split(' ')) if (qTokens.has(t)) overlap++;
            score = qTokens.size ? (overlap / qTokens.size) * 70 : 0;
        }
        if (score > bestScore) {
            bestScore = score;
            best = { id: m[1], name };
        }
    });
    return best && bestScore > 0 ? best : null;
}
"""

_JS_CLICK_PLAYLIST_PLAY = r"""
() => {
    const btn = document.querySelector('[data-testid="action-bar"] button[data-testid="play-button"]')
        || document.querySelector('main button[data-testid="play-button"]');
    if (!btn) return null;
    // Spotify React handlers need a real DOM .click(), not Playwright mouse coords
    btn.click();
    return btn.getAttribute('aria-label');
}
"""

_MARK_SIDEBAR_PLAYLIST_JS = r"""
(query) => {
    document.querySelectorAll('[data-hive-play]').forEach(e => e.removeAttribute('data-hive-play'));
    const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean).join(' ');
    const q = norm(query);
    const inSidebar = el => !!el.closest('aside, nav, [data-testid="left-sidebar"], [aria-label="Your Library"]');

    let best = null;
    let bestScore = -1;
    document.querySelectorAll('button[aria-label^="Play "], button[aria-label^="play "]').forEach(btn => {
        const r = btn.getBoundingClientRect();
        if (!r.width && !r.height) return;
        if (!inSidebar(btn)) return;
        const name = btn.getAttribute('aria-label').slice(5).trim();
        const n = norm(name);
        let score = 0;
        if (n === q) score = 100;
        else if (n.includes(q) || q.includes(n)) score = 80;
        else {
            const qTokens = new Set(q.split(' '));
            const nTokens = n.split(' ');
            let overlap = 0;
            for (const t of nTokens) if (qTokens.has(t)) overlap++;
            score = qTokens.size ? (overlap / qTokens.size) * 60 : 0;
        }
        if (score > bestScore) {
            bestScore = score;
            best = { btn, name, score };
        }
    });
    if (!best || bestScore <= 0) return null;
    best.btn.setAttribute('data-hive-play', '1');
    return best.name;
}
"""

_RESOLVE_TRACK_ID_JS = r"""
(query) => {
    const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean).join(' ');
    const qTokens = new Set(norm(query).split(' ').filter(Boolean));

    let best = null;
    let bestScore = -1;
    document.querySelectorAll('a[href*="/track/"]').forEach(a => {
        const href = a.getAttribute('href') || '';
        const m = href.match(/\/track\/([A-Za-z0-9]+)/);
        if (!m) return;
        const text = norm(a.textContent || a.getAttribute('aria-label') || '');
        if (!text) return;
        let overlap = 0;
        for (const t of text.split(' ')) if (qTokens.has(t)) overlap++;
        let score = qTokens.size ? overlap / qTokens.size : 0;
        if (text.includes(norm(query))) score = Math.max(score, 0.9);
        if (score > bestScore) {
            bestScore = score;
            best = { id: m[1], name: (a.textContent || '').trim().split('\n')[0] };
        }
    });
    return best && bestScore > 0 ? best : null;
}
"""

_MARK_BEST_PLAY_JS = r"""
(query) => {
    document.querySelectorAll('[data-hive-play]').forEach(e => e.removeAttribute('data-hive-play'));
    const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean);
    const qTokens = new Set(norm(query));

    const inSidebar = el => !!el.closest('aside, nav, [data-testid="left-sidebar"], [aria-label="Your Library"]');

    const candidates = [];
    // Individual track/entity play buttons carry aria-label="Play <name>"
    document.querySelectorAll('button[aria-label^="Play "], button[aria-label^="play "]').forEach(btn => {
        const r = btn.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (inSidebar(btn)) return;
        const name = btn.getAttribute('aria-label').slice(5);
        const nTokens = norm(name);
        let overlap = 0;
        for (const t of nTokens) if (qTokens.has(t)) overlap++;
        // Fraction of query tokens matched (favors exact song matches)
        const score = qTokens.size ? overlap / qTokens.size : 0;
        candidates.push({ btn, score, name });
    });

    candidates.sort((a, b) => b.score - a.score);

    let chosen = null;
    if (candidates.length && candidates[0].score > 0) {
        chosen = candidates[0];
    } else {
        // Fallback: the "Top result" card play button (aria-label just "Play")
        const top = document.querySelector('button[data-testid="play-button"][aria-label="Play"]');
        if (top && !inSidebar(top)) chosen = { btn: top, name: 'Top result' };
    }
    if (!chosen) return null;
    chosen.btn.setAttribute('data-hive-play', '1');
    return chosen.name;
}
"""


async def _page():
    from hive.browser.pool import get_pool
    return await get_pool().get_page()


async def _is_logged_in(page) -> bool:
    try:
        widget = await page.locator('[data-testid="user-widget-link"], [data-testid="user-widget-avatar"]').count()
        login = await page.locator('[data-testid="login-button"]').count()
        return widget > 0 and login == 0
    except Exception:
        return False


_NONSIDEBAR_PLAY_COUNT_JS = r"""
() => {
    const inSidebar = el => !!el.closest('aside, nav, [data-testid="left-sidebar"], [aria-label="Your Library"]');
    let n = 0;
    document.querySelectorAll('button[aria-label^="Play "], button[aria-label^="play "]').forEach(b => {
        const r = b.getBoundingClientRect();
        if ((r.width || r.height) && !inSidebar(b)) n++;
    });
    return n;
}
"""


async def _wait_for_results(page, timeout_ms: int = 15000) -> bool:
    """Wait until the search RESULTS (not just sidebar playlists) have rendered."""
    try:
        await page.wait_for_function(_NONSIDEBAR_PLAY_COUNT_JS + " > 0", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _playpause_state(page) -> str:
    """Return 'playing', 'paused', 'nothing_playing', or 'unknown'."""
    try:
        btn = page.locator('[data-testid="control-button-playpause"]').first
        if await btn.count() == 0:
            return "unknown"
        # Empty player renders a DISABLED button — nothing is loaded/playing
        if await btn.is_disabled():
            return "nothing_playing"
        label = (await btn.get_attribute("aria-label") or "").lower()
        if "pause" in label:
            return "playing"
        if "play" in label:
            return "paused"
    except Exception:
        pass
    return "unknown"


async def now_playing(page=None) -> dict:
    """Read the currently playing track/artist from the now-playing bar."""
    page = page or await _page()
    try:
        track = ""
        artist = ""
        if await page.locator('[data-testid="context-item-info-title"]').count():
            track = (await page.locator('[data-testid="context-item-info-title"]').first.text_content() or "").strip()
        if await page.locator('[data-testid="context-item-info-subtitles"]').count():
            artist = (await page.locator('[data-testid="context-item-info-subtitles"]').first.text_content() or "").strip()
        state = await _playpause_state(page)
        if not track and state in ("nothing_playing", "unknown"):
            return {"status": "nothing_playing"}
        label = ""
        widget = page.locator('[data-testid="now-playing-widget"]').first
        if await widget.count():
            label = (await widget.get_attribute("aria-label") or "").replace("Now playing: ", "").strip()
        return {
            "status": "ok",
            "state": state,
            "track": track,
            "artist": artist,
            "widget": label,
        }
    except Exception as e:
        return {"error": str(e)}


async def _ensure_logged_in(page) -> bool:
    if await _is_logged_in(page):
        return True
    await page.goto("https://open.spotify.com", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)
    return await _is_logged_in(page)


async def list_playlists(page=None) -> dict:
    """List playlists visible in the left sidebar (Your Library)."""
    page = page or await _page()
    if not await _ensure_logged_in(page):
        return {"status": "not_logged_in",
                "message": "Not logged into Spotify. Run a Spotify login first."}
    await page.goto("https://open.spotify.com", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)
    names = await page.evaluate(_LIST_SIDEBAR_PLAYLISTS_JS)
    return {"status": "ok", "playlists": names or []}


async def _is_drm_blocked(page) -> bool:
    try:
        body = (await page.locator("body").inner_text(timeout=5000) or "").lower()
        return "protected content" in body or "playback of protected" in body
    except Exception:
        return False


def _open_spotify_uri(uri: str) -> dict:
    """Hand off to Spotify desktop app or OS default handler (real audio)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'start "" "{uri}"', shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", uri])
        else:
            subprocess.Popen(["xdg-open", uri])
        return {"launched": True, "uri": uri}
    except Exception as e:
        logger.warning("Spotify URI launch failed: %s", e)
        return {"launched": False, "uri": uri, "error": str(e)}


async def _resume_if_paused(page) -> None:
    await page.evaluate("""() => {
        const b = document.querySelector('[data-testid="control-button-playpause"]');
        if (!b || b.disabled) return;
        const label = (b.getAttribute('aria-label') || '').toLowerCase();
        if (label.includes('play')) b.click();
    }""")


async def _click_play_and_wait(page, spotify_uri: str | None = None) -> dict:
    """Try web player; fall back to spotify: URI so music actually plays."""
    if await _is_drm_blocked(page):
        if spotify_uri:
            launch = _open_spotify_uri(spotify_uri)
            return {
                "status": "playing" if launch.get("launched") else "failed",
                "method": "spotify_app",
                "drm_blocked": True,
                **launch,
            }
        return {"status": "drm_blocked", "message": "Protected playback not enabled in this browser."}

    await _dismiss_cookies(page)
    clicked = await _wait_and_play_on_page(page)

    for _ in range(12):
        await page.wait_for_timeout(1500)
        np = await now_playing(page)
        if np.get("track"):
            if np.get("state") == "paused":
                await _resume_if_paused(page)
                await page.wait_for_timeout(2000)
                np = await now_playing(page)
            return {
                "status": "playing",
                "method": "web",
                "now_playing": np,
                "play_button": clicked,
            }

    if spotify_uri:
        launch = _open_spotify_uri(spotify_uri)
        return {
            "status": "playing" if launch.get("launched") else "failed",
            "method": "spotify_app",
            "now_playing": await now_playing(page),
            "play_button": clicked,
            **launch,
        }

    return {
        "status": "started",
        "method": "web",
        "now_playing": await now_playing(page),
        "play_button": clicked,
    }


async def _dismiss_cookies(page) -> None:
    for sel in ('button:has-text("Accept")', 'button:has-text("Reject")'):
        btn = page.locator(sel).first
        if await btn.count():
            try:
                await btn.click(timeout=2000)
                await page.wait_for_timeout(400)
                return
            except Exception:
                pass


async def _js_click_playlist_play(page) -> str | None:
    return await page.evaluate(_JS_CLICK_PLAYLIST_PLAY)


async def _wait_and_play_on_page(page) -> str | None:
    """Wait for the action-bar play button and JS-click it."""
    try:
        await page.wait_for_selector('[data-testid="action-bar"] [data-testid="play-button"], main [data-testid="play-button"]',
                                     timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(2000)
    label = await _js_click_playlist_play(page)
    if label and label.lower().startswith("play"):
        # Give Spotify a moment to attach the player after the first click
        await page.wait_for_timeout(2500)
        np = await now_playing(page)
        if not np.get("track"):
            label = await _js_click_playlist_play(page)
    return label


async def play_playlist(name: str) -> dict:
    """Open a sidebar playlist page and press Play (JS click — how Spotify automation works)."""
    page = await _page()
    if not await _ensure_logged_in(page):
        return {"status": "not_logged_in",
                "message": "Not logged into Spotify. Run a Spotify login first."}

    await page.goto("https://open.spotify.com", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)
    await _dismiss_cookies(page)

    playlists = await page.evaluate(_LIST_SIDEBAR_PLAYLISTS_JS)
    if not playlists:
        return {"status": "no_playlists",
                "message": "No playlists found in your sidebar. Pin a playlist in Spotify first."}

    resolved = await page.evaluate(_RESOLVE_PLAYLIST_ID_JS, name)
    if not resolved:
        return {
            "status": "playlist_not_found",
            "query": name,
            "playlists": playlists,
            "message": f"Couldn't find '{name}' in your library. Available: {', '.join(playlists)}",
        }

    playlist_name = resolved["name"]
    url = f"https://open.spotify.com/playlist/{resolved['id']}"
    spotify_uri = f"spotify:playlist:{resolved['id']}"
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)

    result = await _click_play_and_wait(page, spotify_uri)
    return {
        "playlist": playlist_name,
        "url": url,
        **result,
    }


async def play(query: str, *, prefer_playlist: bool = False) -> dict:
    """Search for a track, open its page, and play (JS click + Widevine-safe flow)."""
    page = await _page()
    if not await _ensure_logged_in(page):
        return {"status": "not_logged_in",
                "message": "Not logged into Spotify. Run a Spotify login first."}

    if prefer_playlist:
        result = await play_playlist(query)
        if result.get("status") not in ("playlist_not_found", "no_playlists"):
            return result

    await page.goto(f"https://open.spotify.com/search/{quote(query)}/tracks",
                    wait_until="domcontentloaded", timeout=45000)
    if not await _wait_for_results(page, 15000):
        await page.wait_for_timeout(4000)

    resolved = await page.evaluate(_RESOLVE_TRACK_ID_JS, query)
    if not resolved:
        return {"status": "no_results", "query": query,
                "message": f"Couldn't find a track for '{query}'."}

    url = f"https://open.spotify.com/track/{resolved['id']}"
    spotify_uri = f"spotify:track:{resolved['id']}"
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)

    result = await _click_play_and_wait(page, spotify_uri)
    return {
        "query": query,
        "track": resolved.get("name"),
        "url": url,
        **result,
    }


async def pause() -> dict:
    page = await _page()
    state = await _playpause_state(page)
    if state == "playing":
        await page.locator('[data-testid="control-button-playpause"]').first.click(timeout=5000)
        await page.wait_for_timeout(500)
        return {"status": "paused"}
    return {"status": "already_paused" if state == "paused" else "nothing_playing"}


async def resume() -> dict:
    page = await _page()
    state = await _playpause_state(page)
    if state == "paused":
        await page.locator('[data-testid="control-button-playpause"]').first.click(timeout=5000)
        await page.wait_for_timeout(500)
        return {"status": "playing"}
    return {"status": "already_playing" if state == "playing" else "nothing_playing"}


async def next_track() -> dict:
    page = await _page()
    try:
        await page.locator('[data-testid="control-button-skip-forward"]').first.click(timeout=5000)
        await page.wait_for_timeout(1500)
        return {"status": "skipped", "now_playing": await now_playing(page)}
    except Exception as e:
        return {"error": str(e)}


async def previous_track() -> dict:
    page = await _page()
    try:
        await page.locator('[data-testid="control-button-skip-back"]').first.click(timeout=5000)
        await page.wait_for_timeout(1500)
        return {"status": "previous", "now_playing": await now_playing(page)}
    except Exception as e:
        return {"error": str(e)}


async def control(action: str, query: str = "") -> dict:
    """Single entry point. action ∈ play|play_playlist|list_playlists|pause|resume|next|previous|now_playing."""
    action = (action or "").strip().lower()
    if action in ("list_playlists", "playlists"):
        return await list_playlists()
    if action in ("play_playlist", "playlist"):
        if not query:
            listed = await list_playlists()
            names = listed.get("playlists") or []
            if not names:
                return listed
            query = names[0]
        return await play_playlist(query)
    if action == "play":
        if not query:
            return {"error": "play requires a query (song/artist/playlist name)"}
        return await play(query)
    if action == "pause":
        return await pause()
    if action in ("resume", "unpause"):
        return await resume()
    if action in ("next", "skip"):
        return await next_track()
    if action in ("previous", "prev", "back"):
        return await previous_track()
    if action in ("now_playing", "status", "current"):
        return await now_playing()
    return {"error": f"unknown action '{action}'. Use play|pause|resume|next|previous|now_playing"}
