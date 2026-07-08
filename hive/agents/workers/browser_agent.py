"""
HIVE — Browser Agent (On-the-Fly)
Autonomous browser automation specialist using Playwright.
"""

import re
import json
import asyncio
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_STEPS = 40
MAX_RETRIES = 3
RECENT_ACTIONS_SIZE = 5


def _extract_site_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().replace("www.", "")
    except Exception:
        return "unknown"


def _load_credentials(task: str, context: dict) -> dict:
    """Load credentials from vault, context, or task text — never from plaintext .env."""
    from hive.browser.vault import get_credentials_dict

    creds = {}

    # From vault by site mentioned in task/url
    url_match = re.search(r"https?://[^\s]+", task)
    if url_match:
        site = _extract_site_from_url(url_match.group(0))
        creds.update(get_credentials_dict(site))

    # From context
    if context.get("credentials"):
        creds.update(context["credentials"])
    if context.get("sensitive_data"):
        creds.update(context["sensitive_data"])

    # Extract from task text as fallback
    email_match = re.search(r"(?:email|username|user)[:\s]+(\S+@\S+|\w+)", task, re.IGNORECASE)
    pass_match = re.search(r"(?:password|pass|pwd)[:\s]+(\S+)", task, re.IGNORECASE)
    if email_match:
        creds["email"] = email_match.group(1)
    if pass_match:
        creds["password"] = pass_match.group(1)

    return creds


def _is_2fa_page(elements: list) -> bool:
    for el in elements:
        placeholder = (el.get("placeholder", "") or "").lower()
        text = (el.get("text", "") or "").lower()
        aria = (el.get("ariaLabel", "") or "").lower()
        indicators = ["otp", "code", "2fa", "verification", "authenticator", "token", "verify", "one-time"]
        for indicator in indicators:
            if indicator in placeholder or indicator in text or indicator in aria:
                return True
    return False


def _is_captcha_page(elements: list) -> bool:
    indicators = ["captcha", "recaptcha", "hcaptcha", "verify you are human", "i'm not a robot"]
    for el in elements:
        combined = " ".join([
            el.get("text", ""), el.get("placeholder", ""), el.get("ariaLabel", ""),
        ]).lower()
        if any(ind in combined for ind in indicators):
            return True
    return False


def _is_task_complete(task: str, page_elements: list, page_url: str) -> bool:
    task_lower = task.lower()
    page_text = " ".join((el.get("text") or "") for el in page_elements).lower()
    url_lower = page_url.lower()

    if "star" in task_lower:
        for el in page_elements:
            text = (el.get("text", "") or "").lower()
            if "unstar" in text or "starred" in text:
                return True

    if any(kw in task_lower for kw in ["login", "sign in", "log in", "authenticate"]):
        for el in page_elements:
            text = (el.get("text", "") or "").lower()
            if any(ind in text for ind in ["logout", "sign out", "log out", "dashboard", "profile", "settings", "my account"]):
                return True
        if any(ind in url_lower for ind in ["dashboard", "account", "home", "feed", "profile"]):
            if "login" not in url_lower and "signin" not in url_lower:
                return True

    if any(kw in task_lower for kw in ["sign up", "register", "create account"]):
        if any(ind in page_text for ind in ["welcome", "account created", "verify your email", "check your email"]):
            return True
        if "dashboard" in url_lower or "welcome" in url_lower:
            return True

    if any(kw in task_lower for kw in ["checkout", "purchase", "buy", "pay"]):
        if any(ind in page_text for ind in ["order confirmed", "thank you for your order", "payment successful", "order placed"]):
            return True

    if "add to cart" in task_lower:
        if any(ind in page_text for ind in ["added to cart", "item added", "cart updated"]):
            return True

    return False


async def _decide_next_action(task: str, page_state: dict, credentials: dict, step: int, retry: int, checkout_mode: bool = False) -> dict:
    from hive.llm import QwenClient
    from hive.config import DASHSCOPE_API_KEY, QWEN_MODEL

    llm = QwenClient(api_key=DASHSCOPE_API_KEY, model=QWEN_MODEL)

    elements = page_state.get("elements", [])
    elements_text = json.dumps(elements[:25], indent=2)

    retry_text = ""
    if retry > 0:
        retry_text = f"\n\nPREVIOUS ATTEMPT FAILED (retry {retry}/{MAX_RETRIES}). Try a DIFFERENT approach."

    checkout_rule = ""
    if checkout_mode:
        checkout_rule = """
CHECKOUT MODE:
- Use ${card_number}, ${card_expiry}, ${card_cvv}, ${card_name}, ${billing_zip} placeholders with sensitive_data
- Do NOT click "Place Order" / "Pay Now" / "Complete Purchase" unless human_confirmed is set
- If you reach the final purchase button, use action "done" and report the order total
"""

    prompt = f"""You are an autonomous browser automation agent.

TASK: {task}

CURRENT PAGE URL: {page_state.get('url', 'unknown')}
PAGE TITLE: {page_state.get('title', 'unknown')}

PAGE ELEMENTS (index, tag, type, text, placeholder):
{elements_text}

CREDENTIAL KEYS AVAILABLE (use ${{key}} placeholders): {list(credentials.keys())}

Reply with ONLY a JSON object:
{{
    "action": "type" | "click" | "open" | "read" | "screenshot" | "done" | "wait_for_2fa" | "help",
    "index": <element index for type/click>,
    "text": "<text to type>",
    "url": "<url to open>",
    "sensitive_data": {{"key": "value"}},
    "press_enter": false,
    "reasoning": "<brief explanation>"
}}

RULES:
- Use index numbers from PAGE ELEMENTS
- For credentials, use ${{email}} / ${{password}} placeholders with sensitive_data
- If 2FA/code input detected: {{"action": "wait_for_2fa"}}
- If task complete: {{"action": "done"}}
- Only ONE action per response
{checkout_rule}
{retry_text}"""

    messages = [
        {"role": "system", "content": "You are a browser automation agent. Reply ONLY with valid JSON."},
        {"role": "user", "content": prompt},
    ]

    response = await llm.chat(messages, temperature=0.3, max_tokens=512)

    content = ""
    if isinstance(response, dict):
        content = response.get("content", "")
        if not content:
            try:
                choices = response.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
            except (KeyError, IndexError, TypeError):
                pass

    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"action": "help", "reasoning": "Could not parse LLM response"}


async def _execute_action(action: dict, credentials: dict) -> dict:
    from hive.tools import execute_tool

    action_type = action.get("action", "")

    if action_type == "type":
        index = action.get("index", -1)
        text = action.get("text", "")
        sensitive_data = dict(action.get("sensitive_data", {}))

        for key, val in credentials.items():
            text = text.replace(f"${{{key}}}", str(val))
            if key not in sensitive_data:
                sensitive_data[key] = val

        for key, val in list(sensitive_data.items()):
            if isinstance(val, str) and val.startswith("${"):
                cred_key = val.strip("${}")
                sensitive_data[key] = credentials.get(cred_key, val)

        return await execute_tool(
            "browser_type", index=index, text=text,
            press_enter=action.get("press_enter", False),
            sensitive_data=sensitive_data if sensitive_data else None,
        )

    elif action_type == "click":
        return await execute_tool("browser_click", index=action.get("index", -1))

    elif action_type == "open":
        return await execute_tool("browser_open", url=action.get("url", ""))

    elif action_type == "read":
        return await execute_tool("browser_read")

    elif action_type == "screenshot":
        return await execute_tool("browser_screenshot", filename=f"step_{int(asyncio.get_event_loop().time())}.png")

    elif action_type == "done":
        return {"status": "completed"}

    elif action_type == "wait_for_2fa":
        return {"status": "waiting_for_2fa", "message": "2FA code required"}

    elif action_type == "help":
        return {"status": "help_needed", "reasoning": action.get("reasoning", "Unknown error")}

    return {"error": f"Unknown action: {action_type}"}


async def _try_load_session(site: str) -> bool:
    """Try to load a saved browser session for the site."""
    from hive.tools import execute_tool

    # Prefer session name stored in playbook (more robust than domain-based naming).
    from hive.playbooks import load_playbook, site_key

    sk = site_key(site)
    pb = load_playbook(sk)
    session_name = (
        (pb.get("login") or {}).get("session_name")
        or (pb.get("signup") or {}).get("session_name")
        or site.replace(".", "_")
    )
    result = await execute_tool("browser_session_load", name=session_name)
    return result.get("status") == "loaded"


async def _save_session_after_login(site: str, flow: str = "login") -> str:
    from hive.tools import execute_tool

    from hive.playbooks import load_playbook, record_success, site_key

    sk = site_key(site)
    pb = load_playbook(sk)
    # Reuse existing session name for this flow, if any.
    session_name = (pb.get(flow) or {}).get("session_name") or site.replace(".", "_")
    await execute_tool("browser_session_save", name=session_name)
    logger.info("Saved browser session: %s", session_name)
    # Note: we record last_url at completion (we don't have it here).
    record_success(sk, flow=flow, session_name=session_name, trust_delta=2, note="session_saved")
    return session_name


async def run(description: str, context: dict = None) -> dict:
    """Main entry point for browser agent."""
    context = context or {}
    total_retries = 0
    recent_actions = []
    checkout_mode = context.get("checkout_mode", False)
    human_confirmed = context.get("human_confirmed", False)

    try:
        credentials = _load_credentials(description, context)
        logger.info("[BrowserAgent] Starting: %s...", description[:80])
        logger.info("[BrowserAgent] Credential keys: %s", list(credentials.keys()))

        url_match = re.search(r"https?://[^\s]+", description)
        site = _extract_site_from_url(url_match.group(0)) if url_match else "unknown"

        from hive.tools import execute_tool

        # Try loading saved session first for login tasks
        desc_lower = description.lower()
        flow_guess = (
            "checkout"
            if checkout_mode or any(k in desc_lower for k in ["checkout", "purchase", "buy", "pay"])
            else "signup"
            if any(k in desc_lower for k in ["sign up", "signup", "register", "create account"])
            else "login"
        )

        if any(kw in desc_lower for kw in ["login", "sign in", "log in"]) and site != "unknown":
            loaded = await _try_load_session(site)
            if loaded:
                logger.info("[BrowserAgent] Loaded saved session for %s", site)

        if url_match:
            url = url_match.group(0).rstrip(".,;")
            await execute_tool("browser_open", url=url)
        elif "github" in description.lower():
            await execute_tool("browser_open", url="https://github.com/login")

        for step in range(MAX_STEPS):
            page_state = await execute_tool("browser_inspect")

            if "error" in page_state:
                logger.warning("[BrowserAgent] Inspect failed: %s", page_state["error"])
                await asyncio.sleep(1)
                continue

            logger.info(
                "[BrowserAgent] Step %d: URL=%s, Elements=%d",
                step + 1, page_state.get("url", "")[:60], page_state.get("count", 0),
            )

            if _is_captcha_page(page_state.get("elements", [])):
                from hive.interactive import prompt_captcha_handoff
                site = _extract_site_from_url(page_state.get("url", ""))
                solved = await prompt_captcha_handoff(site or "unknown", page_state.get("url", ""))
                if solved:
                    await asyncio.sleep(2)
                    continue
                return {
                    "status": "captcha_required",
                    "message": "CAPTCHA detected. Solve it in the browser and retry.",
                    "steps": step + 1,
                    "url": page_state.get("url", ""),
                    "requires_human": True,
                }

            if _is_task_complete(description, page_state.get("elements", []), page_state.get("url", "")):
                if site != "unknown":
                    session_name = await _save_session_after_login(site, flow=flow_guess)
                    from hive.playbooks import record_success, site_key
                    sk = site_key(site)
                    record_success(
                        sk,
                        flow=flow_guess,
                        session_name=session_name,
                        last_url=page_state.get("url", ""),
                        trust_delta=10,
                        note="task_completed",
                    )
                return {
                    "status": "completed",
                    "result": f"Task completed in {step + 1} steps",
                    "steps": step + 1,
                    "url": page_state.get("url", ""),
                }

            if _is_2fa_page(page_state.get("elements", [])):
                code = None
                # Try disposable email first
                code_result = await execute_tool("browser_wait_for_code", timeout=15)
                if "code" in code_result:
                    code = code_result["code"]
                else:
                    from hive.interactive import prompt_2fa_code
                    code = await prompt_2fa_code(
                        site,
                        "Enter the verification code from your authenticator or SMS.",
                    )

                if code:
                    otp_action = {"action": "type", "text": code, "press_enter": True}
                    for el in page_state.get("elements", []):
                        ph = (el.get("placeholder") or "").lower()
                        aria = (el.get("ariaLabel") or "").lower()
                        if any(k in ph + aria for k in ["code", "otp", "verify", "digit"]):
                            otp_action["index"] = el.get("index", 0)
                            break
                    if "index" not in otp_action:
                        otp_action["index"] = 0
                    await _execute_action(otp_action, credentials)
                    await asyncio.sleep(2)
                    continue

                return {
                    "status": "waiting_for_2fa",
                    "message": "2FA/verification code required.",
                    "steps": step + 1,
                    "url": page_state.get("url", ""),
                    "requires_human": True,
                }

            for retry in range(MAX_RETRIES):
                action = await _decide_next_action(
                    description, page_state, credentials, step, retry, checkout_mode,
                )

                if action.get("action") == "done":
                    if site != "unknown":
                        session_name = await _save_session_after_login(site, flow=flow_guess)
                        from hive.playbooks import record_success, site_key
                        sk = site_key(site)
                        record_success(
                            sk,
                            flow=flow_guess,
                            session_name=session_name,
                            last_url=page_state.get("url", ""),
                            trust_delta=10,
                            note="llm_marked_done",
                        )
                    return {
                        "status": "completed",
                        "result": action.get("reasoning", "Task complete"),
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                    }

                if action.get("action") == "wait_for_2fa":
                    code_result = await execute_tool("browser_wait_for_code", timeout=45)
                    if "code" in code_result:
                        otp_action = {"action": "type", "text": code_result["code"], "press_enter": True, "index": 0}
                        await _execute_action(otp_action, credentials)
                        break
                    return {
                        "status": "waiting_for_2fa",
                        "message": "2FA code required",
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                    }

                if action.get("action") == "help":
                    return {
                        "status": "help_needed",
                        "message": action.get("reasoning", "Need help"),
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                    }

                # Block final purchase click in checkout mode without confirmation
                if checkout_mode and not human_confirmed and action.get("action") == "click":
                    el_idx = action.get("index", -1)
                    elements = page_state.get("elements", [])
                    if 0 <= el_idx < len(elements):
                        btn_text = (elements[el_idx].get("text") or "").lower()
                        if any(kw in btn_text for kw in ["place order", "pay now", "complete purchase", "submit order", "buy now"]):
                            await execute_tool("browser_screenshot", filename="checkout_review.png")
                            return {
                                "status": "pending_confirmation",
                                "message": "Checkout ready. Review screenshot and confirm purchase.",
                                "steps": step + 1,
                                "url": page_state.get("url", ""),
                                "requires_human": True,
                            }

                result = await _execute_action(action, credentials)
                logger.info(
                    "[BrowserAgent] Action: %s -> %s",
                    action.get("action"),
                    "OK" if "error" not in result else result.get("error", "")[:50],
                )

                action_key = f"{action.get('action')}:{action.get('index', '')}:{action.get('text', '')[:20]}"
                recent_actions.append(action_key)
                if len(recent_actions) > RECENT_ACTIONS_SIZE:
                    recent_actions.pop(0)

                if len(recent_actions) >= 3 and len(set(recent_actions[-3:])) == 1:
                    total_retries += 1
                    if total_retries >= MAX_RETRIES * MAX_STEPS:
                        return {
                            "status": "help_needed",
                            "message": "Stuck in a loop.",
                            "steps": step + 1,
                            "url": page_state.get("url", ""),
                        }
                    continue

                if "error" not in result:
                    break

                total_retries += 1
                if retry == MAX_RETRIES - 1:
                    return {
                        "status": "help_needed",
                        "message": f"Failed after {MAX_RETRIES} attempts: {result.get('error')}",
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                    }

            await asyncio.sleep(0.5)

        return {
            "status": "max_steps_reached",
            "message": f"Task did not complete within {MAX_STEPS} steps",
            "steps": MAX_STEPS,
        }

    except Exception as e:
        logger.error("[BrowserAgent] Error: %s", e)
        return {"status": "error", "message": str(e), "steps": 0}


async def run_browser_agent(task: str, context: dict = None) -> dict:
    return await run(task, context)
