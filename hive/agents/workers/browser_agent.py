"""
HIVE — Browser Agent (On-the-Fly)
Autonomous browser automation specialist.
Created by agent_forge when a browser task is detected.
Deleted after task complete.
"""

import os
import re
import json
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum steps before giving up
MAX_STEPS = 30
# Maximum retry approaches per step
MAX_RETRIES = 3
# Track recent actions to detect loops
RECENT_ACTIONS_SIZE = 5


def _load_credentials_from_env() -> dict:
    """Load any saved credentials from .env file."""
    creds = {}
    env_path = Path(".env")
    if env_path.exists():
        content = env_path.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("HIVE_BROWSER_"):
                key_val = line.split("=", 1)
                if len(key_val) == 2:
                    key = key_val[0].replace("HIVE_BROWSER_", "").lower()
                    val = key_val[1].strip().strip('"').strip("'")
                    creds[key] = val
    return creds


def _save_credentials_to_env(creds: dict):
    """Save credentials to .env file for future use."""
    env_path = Path(".env")
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    
    for key, val in creds.items():
        env_key = f"HIVE_BROWSER_{key.upper()}"
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(env_key + "="):
                lines[i] = f'{env_key}={val}'
                found = True
                break
        if not found:
            lines.append(f'{env_key}={val}')
    
    env_path.write_text("\n".join(lines) + "\n")


def _extract_credentials_from_task(task: str) -> dict:
    """Extract credentials from task description."""
    creds = {}
    
    # Match patterns like "email X", "username X", "password Y"
    email_match = re.search(r"(?:email|username|user)[:\s]+(\S+@\S+|\w+)", task, re.IGNORECASE)
    pass_match = re.search(r"(?:password|pass|pwd)[:\s]+(\S+)", task, re.IGNORECASE)
    
    if email_match:
        creds["email"] = email_match.group(1)
    if pass_match:
        creds["password"] = pass_match.group(1)
    
    return creds


def _is_2fa_page(elements: list) -> bool:
    """Detect if the page has a 2FA/OTP input field."""
    for el in elements:
        placeholder = (el.get("placeholder", "") or "").lower()
        text = (el.get("text", "") or "").lower()
        aria = (el.get("ariaLabel", "") or "").lower()
        
        indicators = ["otp", "code", "2fa", "verification", "authenticator", "token", "verify"]
        for indicator in indicators:
            if indicator in placeholder or indicator in text or indicator in aria:
                return True
        if el.get("tag") == "input" and el.get("type") == "text":
            # Could be OTP field if near "code" or "verify" text
            for other in elements:
                other_text = (other.get("text", "") or "").lower()
                if "code" in other_text or "verify" in other_text:
                    return True
    return False


def _is_task_complete(task: str, page_elements: list, page_url: str) -> bool:
    """Check if the browser task appears to be complete."""
    task_lower = task.lower()
    
    # Check for "star" task completion
    if "star" in task_lower:
        # Look for "unstar" button or "starred" indicator
        for el in page_elements:
            text = (el.get("text", "") or "").lower()
            if "unstar" in text or "starred" in text:
                return True
    
    # Check for login completion
    if "login" in task_lower or "sign in" in task_lower:
        # Look for logout, dashboard, profile indicators
        for el in page_elements:
            text = (el.get("text", "") or "").lower()
            if any(ind in text for ind in ["logout", "sign out", "dashboard", "profile", "settings"]):
                return True
    
    return False


async def _decide_next_action(task: str, page_state: dict, credentials: dict, step: int, retry: int) -> dict:
    """Ask LLM what to do next based on current page state."""
    from hive.llm import QwenClient
    from hive.config import DASHSCOPE_API_KEY, QWEN_MODEL
    
    llm = QwenClient(
        api_key=DASHSCOPE_API_KEY,
        model=QWEN_MODEL,
    )
    
    elements = page_state.get("elements", [])
    elements_text = json.dumps(elements[:15], indent=2)
    
    retry_text = ""
    if retry > 0:
        retry_text = f"\n\nPREVIOUS ATTEMPT FAILED (retry {retry}/{MAX_RETRIES}). Try a DIFFERENT approach."
    
    prompt = f"""You are an autonomous browser automation agent. You control a web browser to complete tasks.

TASK: {task}

CURRENT PAGE URL: {page_state.get('url', 'unknown')}
PAGE TITLE: {page_state.get('title', 'unknown')}

PAGE ELEMENTS (index, tag, type, text, placeholder):
{elements_text}

CREDENTIALS AVAILABLE (use ${{key}} placeholders): {list(credentials.keys())}

What should I do next? Reply with ONLY a JSON object:
{{
    "action": "type" | "click" | "open" | "read" | "screenshot" | "done" | "wait_for_2fa" | "help",
    "index": <element index for type/click>,
    "text": "<text to type>",
    "url": "<url to open>",
    "sensitive_data": {{"key": "value"}},
    "reasoning": "<brief explanation>"
}}

RULES:
- Use index numbers from the PAGE ELEMENTS list
- For credentials, use ${{email}} or ${{password}} placeholders with sensitive_data
- If you see a 2FA/code input, reply: {{"action": "wait_for_2fa", "reasoning": "2FA detected"}}
- If the task is complete, reply: {{"action": "done", "reasoning": "task done"}}
- If you need help, reply: {{"action": "help", "reasoning": "what went wrong"}}
- Only ONE action per response
- For GitHub login: first type email in index with "login" or "Email" field, then type password, then click submit
{retry_text}"""

    messages = [
        {"role": "system", "content": "You are a browser automation agent. Reply ONLY with valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    response = await llm.chat(messages, temperature=0.3, max_tokens=512)
    
    # Parse JSON response - handle OpenAI response format
    content = ""
    if isinstance(response, dict):
        # Try direct content field
        content = response.get("content", "")
        # Try OpenAI format: choices[0].message.content
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
    """Execute a browser action using tools."""
    from hive.tools import execute_tool
    
    action_type = action.get("action", "")
    
    if action_type == "type":
        index = action.get("index", -1)
        text = action.get("text", "")
        sensitive_data = action.get("sensitive_data", {})
        
        # Replace placeholders with actual credentials
        for key, val in credentials.items():
            text = text.replace(f"${{{key}}}", val)
        
        if sensitive_data:
            for key, val in sensitive_data.items():
                if isinstance(val, str) and val.startswith("${"):
                    cred_key = val.strip("${}").strip("}")
                    sensitive_data[key] = credentials.get(cred_key, val)
        
        # Use browser_type tool with press_enter for better compatibility
        press_enter = action.get("press_enter", False)
        return await execute_tool("browser_type", index=index, text=text, 
                                   press_enter=press_enter)
    
    elif action_type == "click":
        index = action.get("index", -1)
        return await execute_tool("browser_click", index=index)
    
    elif action_type == "open":
        url = action.get("url", "")
        return await execute_tool("browser_open", url=url)
    
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


async def run(description: str, context: dict = None) -> dict:
    """
    Main entry point for browser agent.
    
    Args:
        description: Task description (e.g., "Login to GitHub with email X and password Y")
        context: Optional context dict with credentials, etc.
    
    Returns:
        dict with status, result, steps taken, etc.
    """
    context = context or {}
    total_retries = 0
    recent_actions = []  # Track recent actions to detect loops
    
    try:
        # Extract credentials from task description
        credentials = _extract_credentials_from_task(description)
        
        # Also load from .env
        env_creds = _load_credentials_from_env()
        credentials.update(env_creds)
        
        # If credentials in context, use those
        if "credentials" in context:
            credentials.update(context["credentials"])
        
        # Save credentials to .env for future use
        if credentials:
            _save_credentials_to_env(credentials)
        
        logger.info(f"[BrowserAgent] Starting task: {description[:80]}...")
        logger.info(f"[BrowserAgent] Credentials available: {list(credentials.keys())}")
        
        # Check if we need to open a URL first
        url_match = re.search(r"https?://[^\s]+", description)
        if url_match:
            url = url_match.group(0).rstrip(".,;")
            from hive.tools import execute_tool
            await execute_tool("browser_open", url=url)
        elif "github" in description.lower():
            from hive.tools import execute_tool
            await execute_tool("browser_open", url="https://github.com/login")
        
        # Main execution loop
        for step in range(MAX_STEPS):
            # 1. Inspect current page
            from hive.tools import execute_tool
            page_state = await execute_tool("browser_inspect")
            
            if "error" in page_state:
                logger.warning(f"[BrowserAgent] Inspect failed: {page_state['error']}")
                continue
            
            logger.info(f"[BrowserAgent] Step {step + 1}: URL={page_state.get('url', 'unknown')[:60]}, Elements={page_state.get('count', 0)}")
            
            # 2. Check if task is complete
            if _is_task_complete(description, page_state.get("elements", []), page_state.get("url", "")):
                return {
                    "status": "completed",
                    "result": f"Task completed in {step + 1} steps",
                    "steps": step + 1,
                    "url": page_state.get("url", ""),
                }
            
            # 3. Check for 2FA
            if _is_2fa_page(page_state.get("elements", [])):
                return {
                    "status": "waiting_for_2fa",
                    "message": "I detected a 2FA/verification code input. Please provide the code.",
                    "steps": step + 1,
                    "url": page_state.get("url", ""),
                }
            
            # 4. Ask LLM what to do next
            for retry in range(MAX_RETRIES):
                action = await _decide_next_action(description, page_state, credentials, step, retry)
                
                # Handle special actions
                if action.get("action") == "done":
                    return {
                        "status": "completed",
                        "result": action.get("reasoning", "Task complete"),
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                    }
                
                if action.get("action") == "wait_for_2fa":
                    return {
                        "status": "waiting_for_2fa",
                        "message": "I detected a 2FA/verification code input. Please provide the code.",
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
                
                # 5. Execute the action
                result = await _execute_action(action, credentials)
                logger.info(f"[BrowserAgent] Action: {action.get('action')} index={action.get('index', 'N/A')} -> {'OK' if 'error' not in result else result.get('error', 'unknown error')[:50]}")
                
                # Track action for loop detection
                action_key = f"{action.get('action')}:{action.get('index', '')}:{action.get('text', '')[:20]}"
                recent_actions.append(action_key)
                if len(recent_actions) > RECENT_ACTIONS_SIZE:
                    recent_actions.pop(0)
                
                # Check for loops (same action 3 times in a row)
                if len(recent_actions) >= 3 and len(set(recent_actions[-3:])) == 1:
                    logger.warning(f"[BrowserAgent] Loop detected: {action_key}")
                    # Force a different approach by adding to retries
                    total_retries += 1
                    if total_retries >= MAX_RETRIES * MAX_STEPS:
                        return {
                            "status": "help_needed",
                            "message": "Stuck in a loop. Same action repeated 3 times.",
                            "steps": step + 1,
                            "url": page_state.get("url", ""),
                            "total_retries": total_retries,
                        }
                    continue  # Try again with different approach
                
                if "error" not in result:
                    # Action succeeded, move to next step
                    break
                
                # Action failed, retry with different approach
                total_retries += 1
                logger.warning(f"[BrowserAgent] Action failed (retry {retry + 1}): {result.get('error')}")
                
                if retry == MAX_RETRIES - 1:
                    # All retries exhausted for this step
                    return {
                        "status": "help_needed",
                        "message": f"Failed after {MAX_RETRIES} attempts. Last error: {result.get('error')}",
                        "steps": step + 1,
                        "url": page_state.get("url", ""),
                        "total_retries": total_retries,
                    }
            
            # Small delay between steps
            await asyncio.sleep(0.5)
        
        # Max steps reached
        return {
            "status": "max_steps_reached",
            "message": f"Task did not complete within {MAX_STEPS} steps",
            "steps": MAX_STEPS,
            "total_retries": total_retries,
        }
    
    except Exception as e:
        logger.error(f"[BrowserAgent] Error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "steps": 0,
            "total_retries": total_retries,
        }


# For agent_forge compatibility
async def run_browser_agent(task: str, context: dict = None) -> dict:
    """Alias for run() — used by agent_forge."""
    return await run(task, context)
