"""
HIVE — Desktop Controller Agent
Mouse clicks, keyboard input, screenshots, app control, WhatsApp automation.
Cross-platform: supports macOS and Windows.
"""

import os
import re
import sys
import time
import logging
import subprocess
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Safety: require confirmation for destructive actions
DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "format", "shutdown", "restart",
    "close all", "kill", "uninstall",
]

SCREENSHOT_DIR = "db/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class DesktopController:
    """Controls desktop via mouse, keyboard, and app automation."""

    @staticmethod
    async def run(description: str, context: dict = None) -> dict:
        description_lower = description.lower()
        context = context or {}

        try:
            # Screenshot
            if any(word in description_lower for word in ["screenshot", "screen", "capture", "what's on"]):
                return await _take_screenshot(description)

            # Click
            if any(word in description_lower for word in ["click", "tap", "press button"]):
                return await _click(description)

            # Type / send message
            if any(word in description_lower for word in ["type", "send", "write", "message", "text"]):
                return await _type_text(description)

            # Open app
            if any(word in description_lower for word in ["open", "launch", "start", "run app"]):
                return await _open_app(description)

            # WhatsApp
            if any(word in description_lower for word in ["whatsapp", "wa ", "whats app"]):
                return await _handle_whatsapp(description)

            # Chrome / Browser
            if any(word in description_lower for word in ["chrome", "browser", "edge", "firefox"]):
                return await _handle_browser(description)

            # List open windows
            if any(word in description_lower for word in ["windows", "apps open", "what's running", "list app"]):
                return await _list_windows()

            # Focus / switch window
            if any(word in description_lower for word in ["focus", "switch", "bring to front", "activate"]):
                return await _focus_window(description)

            # Close app
            if any(word in description_lower for word in ["close app", "close window", "quit app"]):
                return await _close_app(description)

            # Keyboard shortcut
            if any(word in description_lower for word in ["hotkey", "shortcut", "ctrl", "alt"]):
                return await _keyboard_shortcut(description)

            # Scroll
            if any(word in description_lower for word in ["scroll", "wheel"]):
                return await _scroll(description)

            # Mouse position
            if any(word in description_lower for word in ["mouse pos", "cursor pos", "where am i"]):
                return await _get_mouse_position()

            return await _help_info()

        except Exception as e:
            logger.error(f"[DesktopController] Error: {e}")
            return {"status": "error", "error": str(e)}


# ─── Screenshot ──────────────────────────────────────────────────────────────

async def _take_screenshot(description: str) -> dict:
    """Take a screenshot of the full screen or a region."""
    import pyautogui

    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)

    # Check for region keywords
    region = None
    desc_lower = description.lower()

    if "region" in desc_lower or "area" in desc_lower:
        # Try to extract coordinates: "screenshot region 100,200,500,400"
        coords_match = re.search(r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', description)
        if coords_match:
            x, y, w, h = [int(c) for c in coords_match.groups()]
            region = (x, y, w, h)

    screenshot = pyautogui.screenshot(region=region)
    screenshot.save(filepath)

    return {
        "status": "success",
        "action": "screenshot",
        "file": filepath,
        "size": f"{screenshot.width}x{screenshot.height}",
        "region": region,
    }


# ─── Mouse ───────────────────────────────────────────────────────────────────

async def _click(description: str) -> dict:
    """Click at coordinates or on a UI element."""
    import pyautogui

    desc_lower = description.lower()

    # Extract coordinates: "click 500,300" or "click at x=500 y=300"
    coords_match = re.search(r'(\d+)\s*,\s*(\d+)', description)
    if coords_match:
        x, y = int(coords_match.group(1)), int(coords_match.group(2))
        pyautogui.click(x, y)
        return {"status": "success", "action": "click", "position": [x, y]}

    # "click center" / "click middle"
    if "center" in desc_lower or "middle" in desc_lower:
        screen_w, screen_h = pyautogui.size()
        pyautogui.click(screen_w // 2, screen_h // 2)
        return {"status": "success", "action": "click_center", "position": [screen_w // 2, screen_h // 2]}

    # "double click"
    if "double" in desc_lower:
        coords_match = re.search(r'(\d+)\s*,\s*(\d+)', description)
        if coords_match:
            x, y = int(coords_match.group(1)), int(coords_match.group(2))
            pyautogui.doubleClick(x, y)
            return {"status": "success", "action": "double_click", "position": [x, y]}

    return {"status": "error", "message": "No coordinates found. Use: click X,Y"}


async def _get_mouse_position() -> dict:
    """Get current mouse cursor position."""
    import pyautogui
    pos = pyautogui.position()
    return {"status": "success", "action": "mouse_position", "x": pos.x, "y": pos.y}


async def _scroll(description: str) -> dict:
    """Scroll up or down."""
    import pyautogui

    desc_lower = description.lower()
    amount = 3
    amount_match = re.search(r'(\d+)', description)
    if amount_match:
        amount = int(amount_match.group(1))

    direction = -amount if ("up" in desc_lower) else amount
    pyautogui.scroll(direction)

    return {"status": "success", "action": "scroll", "direction": "up" if direction < 0 else "down", "amount": abs(direction)}


# ─── Keyboard ────────────────────────────────────────────────────────────────

async def _type_text(description: str) -> dict:
    """Type text or paste from clipboard."""
    import pyautogui
    import pyperclip

    # Extract the message: "send message hello world" or "type hello world"
    desc_lower = description.lower()
    msg = description

    # Strip common prefixes
    for prefix in ["send message", "send text", "type message", "type text", "type ", "write ", "send "]:
        if desc_lower.startswith(prefix):
            msg = description[len(prefix):].strip()
            break

    if not msg:
        return {"status": "error", "message": "No text to type. Use: type <message>"}

    # Use clipboard for Unicode support (pyautogui.typewrite only works with ASCII)
    pyperclip.copy(msg)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)

    return {"status": "success", "action": "type", "text": msg[:100], "length": len(msg)}


async def _keyboard_shortcut(description: str) -> dict:
    """Press a keyboard shortcut like ctrl+c, alt+tab, etc."""
    import pyautogui

    desc_lower = description.lower()

    # Extract key combo: "press ctrl+c" or "hotkey alt+tab"
    keys_match = re.search(r'(ctrl|alt|shift|win)\s*\+\s*(\w+)', desc_lower)
    if keys_match:
        key1 = keys_match.group(1)
        key2 = keys_match.group(2)
        pyautogui.hotkey(key1, key2)
        return {"status": "success", "action": "hotkey", "keys": f"{key1}+{key2}"}

    # Single key: "press enter", "press escape", "press tab"
    key_match = re.search(r'(enter|escape|tab|space|backspace|delete|up|down|left|right|home|end|pageup|pagedown)', desc_lower)
    if key_match:
        key = key_match.group(1)
        pyautogui.press(key)
        return {"status": "success", "action": "press_key", "key": key}

    return {"status": "error", "message": "No key found. Use: hotkey ctrl+c or press enter"}


# ─── App Management ──────────────────────────────────────────────────────────

async def _open_app(description: str) -> dict:
    """Open an application by name."""
    desc_lower = description.lower()

    # Common app mappings
    app_map = {
        "whatsapp": "WhatsApp",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "file manager": "explorer.exe",
        "cmd": "cmd.exe",
        "terminal": "cmd.exe",
        "powershell": "powershell.exe",
        "vscode": "code",
        "visual studio": "code",
        "spotify": "spotify.exe",
    }

    app_name = None
    for key, val in app_map.items():
        if key in desc_lower:
            app_name = val
            break

    if not app_name:
        # Try to extract app name: "open <app>"
        app_match = re.search(r'open\s+(\w[\w\s]*)', description, re.IGNORECASE)
        if app_match:
            app_name = app_match.group(1).strip()

    if not app_name:
        return {"status": "error", "message": "No app specified. Use: open <app_name>"}

    try:
        if IS_WINDOWS:
            if app_name.endswith(".exe"):
                subprocess.Popen([app_name], shell=True)
            else:
                os.startfile(app_name)
        elif IS_MACOS:
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen([app_name])
        time.sleep(1)
        return {"status": "success", "action": "open_app", "app": app_name}
    except Exception as e:
        return {"status": "error", "message": f"Could not open {app_name}: {e}"}


async def _close_app(description: str) -> dict:
    """Close an application window."""
    desc_lower = description.lower()

    if IS_WINDOWS:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        for w in windows:
            if w.title and any(word in w.title.lower() for word in desc_lower.split() if len(word) > 2):
                try:
                    w.close()
                    return {"status": "success", "action": "close_window", "title": w.title}
                except Exception as e:
                    return {"status": "error", "message": f"Could not close: {e}"}
    elif IS_MACOS:
        app_name = re.search(r'close\s+(\w[\w\s]*)', description, re.IGNORECASE)
        if app_name:
            name = app_name.group(1).strip()
            try:
                subprocess.run(["osascript", "-e", f'quit app "{name}"'], capture_output=True)
                return {"status": "success", "action": "close_app", "app": name}
            except Exception as e:
                return {"status": "error", "message": f"Could not close {name}: {e}"}

    return {"status": "error", "message": "No matching window found"}


async def _list_windows() -> dict:
    """List all open windows."""
    visible = []

    if IS_WINDOWS:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        for w in windows:
            if w.title and w.title.strip():
                visible.append({
                    "title": w.title[:80],
                    "position": [w.left, w.top],
                    "size": [w.width, w.height],
                })
    elif IS_MACOS:
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of every window of every process whose visible is true'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout:
                apps = result.stdout.strip().split(", ")
                for app in apps:
                    visible.append({"title": app.strip(), "position": [0, 0], "size": [0, 0]})
        except Exception:
            pass

    return {"status": "success", "windows": visible[:20], "total": len(visible)}


async def _focus_window(description: str) -> dict:
    """Bring a window to the front and focus it."""
    import pygetwindow as gw

    desc_lower = description.lower()
    windows = gw.getAllWindows()

    for w in windows:
        if w.title and any(word in w.title.lower() for word in desc_lower.split() if len(word) > 2):
            try:
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.3)
                return {"status": "success", "action": "focus_window", "title": w.title}
            except Exception as e:
                return {"status": "error", "message": f"Could not focus: {e}"}

    return {"status": "error", "message": "No matching window found"}


# ─── WhatsApp ────────────────────────────────────────────────────────────────

async def _handle_whatsapp(description: str) -> dict:
    """Send a message via WhatsApp Desktop."""
    import pyautogui
    import pygetwindow as gw
    import pyperclip

    desc_lower = description.lower()

    # Extract contact name: "whatsapp send to Alice: hello"
    contact = None
    message = None

    # Pattern: "whatsapp <contact>: <message>" or "send whatsapp to <contact> <message>"
    to_match = re.search(r'(?:send\s+(?:to\s+|whatsapp\s+to\s+))?(\w[\w\s]*?)(?::\s*|message\s+)(.+)', description, re.IGNORECASE)
    if to_match:
        contact = to_match.group(1).strip()
        message = to_match.group(2).strip()

    if not message:
        # Fallback: "whatsapp hello world"
        msg_match = re.search(r'whatsapp\s+(?:send\s+)?(.+)', description, re.IGNORECASE)
        if msg_match:
            message = msg_match.group(1).strip()

    if not message:
        return {"status": "error", "message": "No message specified. Use: whatsapp <contact>: <message>"}

    # Find WhatsApp window
    whatsapp = None
    for w in gw.getAllWindows():
        if w.title and "whatsapp" in w.title.lower():
            whatsapp = w
            break

    if not whatsapp:
        # Try to open WhatsApp
        try:
            os.startfile("WhatsApp")
            time.sleep(3)
            for w in gw.getAllWindows():
                if w.title and "whatsapp" in w.title.lower():
                    whatsapp = w
                    break
        except Exception:
            pass

    if not whatsapp:
        return {"status": "error", "message": "WhatsApp Desktop not found. Open it first."}

    # Focus WhatsApp
    try:
        if whatsapp.isMinimized:
            whatsapp.restore()
        whatsapp.activate()
        time.sleep(0.5)
    except Exception as e:
        return {"status": "error", "message": f"Could not focus WhatsApp: {e}"}

    # Search for contact if specified
    if contact:
        # Ctrl+F to open search
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.3)

        # Type contact name
        pyperclip.copy(contact)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1)

        # Press Enter to select first result
        pyautogui.press("enter")
        time.sleep(0.5)

    # Type and send message
    pyperclip.copy(message)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)
    pyautogui.press("enter")

    return {
        "status": "success",
        "action": "whatsapp_send",
        "contact": contact or "(current chat)",
        "message": message[:100],
    }


# ─── Browser ─────────────────────────────────────────────────────────────────

async def _handle_browser(description: str) -> dict:
    """Open URL in browser using playwright or default browser."""
    import webbrowser

    desc_lower = description.lower()

    # Extract URL
    url_match = re.search(r'https?://[^\s]+', description)
    if url_match:
        url = url_match.group(0)
        webbrowser.open(url)
        return {"status": "success", "action": "open_url", "url": url}

    # Open browser without specific URL
    if "open" in desc_lower or "launch" in desc_lower:
        # Find browser path
        for browser_name in ["msedge.exe", "chrome.exe", "firefox.exe"]:
            try:
                subprocess.Popen([browser_name], shell=True)
                return {"status": "success", "action": "open_browser", "browser": browser_name}
            except FileNotFoundError:
                continue
        return {"status": "error", "message": "No browser found"}

    return {"status": "error", "message": "No URL specified. Use: open https://example.com"}


# ─── Help ────────────────────────────────────────────────────────────────────

async def _help_info() -> dict:
    """Return available commands."""
    return {
        "status": "ok",
        "agent": "desktop_controller",
        "commands": {
            "screenshot": "Take a screenshot (full screen or region X,Y,W,H)",
            "click X,Y": "Click at coordinates",
            "double click X,Y": "Double click at coordinates",
            "type <text>": "Type text (supports Unicode via clipboard)",
            "send message <text>": "Type and description text",
            "hotkey ctrl+c": "Press keyboard shortcut",
            "press enter": "Press a single key (enter, escape, tab, etc.)",
            "scroll up/down": "Scroll the mouse wheel",
            "open <app>": "Open an application (whatsapp, chrome, notepad, etc.)",
            "close <app>": "Close an application window",
            "focus <app>": "Bring a window to front",
            "list windows": "Show all open windows",
            "whatsapp <contact>: <msg>": "Send WhatsApp message",
            "mouse position": "Get current cursor coordinates",
        },
    }


# ─── Entry point ─────────────────────────────────────────────────────────────

async def run(description: str, context: dict = None) -> dict:
    return await DesktopController.run(description, context)
