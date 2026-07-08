"""
HIVE — Code Runner Worker
Executes code, runs tests, performs git operations, Docker commands
"""

import subprocess
import asyncio
import logging
import re
import tempfile
import os

logger = logging.getLogger(__name__)


class CodeRunner:
    @staticmethod
    async def run(description: str, context: dict = None) -> dict:
        description_lower = description.lower()
        context = context or {}

        # Vault operations — call API directly, no shell
        if any(w in description_lower for w in ["store", "save", "add"]) and \
           any(w in description_lower for w in ["credentials", "password", "login", "card", "credit"]):
            return await _run_vault(description)

        try:
            if any(word in description_lower for word in ["git", "commit", "push", "pull", "branch", "clone"]):
                return await _run_git(description)
            elif any(word in description_lower for word in ["docker", "container", "image", "build", "dockerfile"]):
                return await _run_docker(description)
            elif any(word in description_lower for word in ["test", "pytest", "jest", "npm test"]):
                return await _run_tests(description)
            elif any(word in description_lower for word in ["install", "pip", "npm", "package"]):
                return await _run_package_install(description)
            elif any(word in description_lower for word in ["run", "execute", "python", "node", "script"]):
                return await _run_code(description)
            else:
                return await _run_code(description)

        except Exception as e:
            logger.error(f"[CodeRunner] Error: {e}")
            return {"status": "error", "error": str(e)}


async def _run_vault(description: str) -> dict:
    """Handle vault storage operations directly via API."""
    import re
    from hive.browser.vault import store_credential, store_card, list_credentials, list_cards

    desc = description.lower()

    # Store credentials
    if any(w in desc for w in ["credentials", "password", "login"]):
        # Extract email/username
        email_match = re.search(r'(?:email|username|user)[=:]\s*(\S+@\S+)', description, re.IGNORECASE)
        if not email_match:
            email_match = re.search(r'(?:email|username|user)[:\s]+(\S+)', description, re.IGNORECASE)
        email = email_match.group(1).rstrip(",. ") if email_match else ""

        # Extract password
        pass_match = re.search(r'(?:password|pass|pwd)[=:]\s*(\S+)', description, re.IGNORECASE)
        if not pass_match:
            pass_match = re.search(r'(?:password|pass|pwd)[:\s]+(\S+)', description, re.IGNORECASE)
        password = pass_match.group(1).rstrip(",. ") if pass_match else ""

        # Extract site name
        # Priority: explicit "for X" > service name before "credentials" > domain from email
        site = "unknown"

        # Try "for/onsite" pattern first
        site_match = re.search(r'(?:for|on|at)\s+(\w+)', description, re.IGNORECASE)
        if site_match:
            candidate = site_match.group(1).lower()
            # Skip common words that aren't site names
            if candidate not in ("my", "the", "a", "an", "this", "that", "spotify"):
                site = candidate

        # If still unknown, look for domain-like patterns (but not from email)
        if site == "unknown":
            # Remove email part before searching for domains
            desc_no_email = re.sub(r'\S+@\S+', '', description)
            domain_match = re.search(r'(\w+\.(?:com|net|org|io|co))', desc_no_email, re.IGNORECASE)
            if domain_match:
                site = domain_match.group(1).lower()

        # If still unknown, try to find service name before "credentials"
        if site == "unknown":
            service_match = re.search(r'(\w+)\s+credentials', description, re.IGNORECASE)
            if service_match:
                site = service_match.group(1).lower()

        if not email and not password:
            return {"status": "error", "error": "Could not extract email/password from description"}

        cred_id = store_credential(site, email, password)
        return {
            "status": "completed",
            "action": "store_credential",
            "site": site,
            "email": email,
            "cred_id": cred_id,
            "message": f"Stored credentials for {site} (id: {cred_id})",
        }

    # Store card
    if any(w in desc for w in ["card", "credit", "debit"]):
        # Extract card details
        num_match = re.search(r'(\d{4}\s?\d{4}\s?\d{4}\s?\d{4})', description)
        exp_match = re.search(r'(\d{2}/\d{2})', description)
        cvv_match = re.search(r'(?:cvv|cvc|code)[:\s]+(\d{3,4})', description, re.IGNORECASE)
        name_match = re.search(r'(?:name|cardholder)[:\s]+([A-Za-z\s]+?)(?:,|\.|$)', description, re.IGNORECASE)

        number = num_match.group(1).replace(" ", "") if num_match else ""
        expiry = exp_match.group(1) if exp_match else ""
        cvv = cvv_match.group(1) if cvv_match else ""
        name = name_match.group(1).strip() if name_match else ""

        if not number:
            return {"status": "error", "error": "Could not extract card number from description"}

        card_id = store_card("default", number, expiry, cvv, name)
        return {
            "status": "completed",
            "action": "store_card",
            "last4": number[-4:],
            "card_id": card_id,
            "message": f"Stored card ending in {number[-4:]} (id: {card_id})",
        }

    return {"status": "error", "error": "Could not determine vault action"}


async def _run_git(description: str) -> dict:
    commands = []
    if "status" in description:
        commands.append(["git", "status", "--short"])
    if "commit" in description:
        msg_match = re.search(r'(?:message|commit)[:\s]+["\']([^"\']+)["\']', description, re.IGNORECASE)
        msg = msg_match.group(1) if msg_match else "HIVE auto-commit"
        commands.append(["git", "add", "-A"])
        commands.append(["git", "commit", "-m", msg])
    if "push" in description:
        commands.append(["git", "push"])
    if "pull" in description:
        commands.append(["git", "pull"])
    if "clone" in description:
        url_match = re.search(r"https?://[^\s]+", description)
        if url_match:
            commands.append(["git", "clone", url_match.group(0)])

    if not commands:
        commands.append(["git", "status", "--short"])

    results = []
    for cmd in commands:
        try:
            output = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            results.append({
                "command": " ".join(cmd),
                "returncode": output.returncode,
                "stdout": output.stdout[:500],
                "stderr": output.stderr[:200],
                "success": output.returncode == 0,
            })
        except Exception as e:
            results.append({"command": " ".join(cmd), "error": str(e)})

    return {"status": "completed", "git_commands": results}


async def _run_docker(description: str) -> dict:
    commands = []
    if "build" in description or "dockerfile" in description:
        tag_match = re.search(r'-t\s+(\S+)', description)
        tag = tag_match.group(1) if tag_match else "hive:latest"
        path_match = re.search(r"(?:\.\/|/)(?:[\w\-./]+)", description)
        path = path_match.group(0) if path_match else "."
        commands.append(["docker", "build", "-t", tag, path])
    if "run" in description and "container" in description:
        commands.append(["docker", "run", "--rm", "hive:latest"])
    if "ps" in description:
        commands.append(["docker", "ps"])
    if "images" in description:
        commands.append(["docker", "images"])

    if not commands:
        commands.append(["docker", "ps"])

    results = []
    for cmd in commands:
        try:
            output = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            results.append({
                "command": " ".join(cmd),
                "returncode": output.returncode,
                "stdout": output.stdout[:500],
                "stderr": output.stderr[:200],
                "success": output.returncode == 0,
            })
        except Exception as e:
            results.append({"command": " ".join(cmd), "error": str(e)})

    return {"status": "completed", "docker_commands": results}


async def _run_tests(description: str) -> dict:
    if "pytest" in description or "test" in description:
        cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
    elif "jest" in description or "node" in description:
        cmd = ["npm", "test"]
    else:
        cmd = ["python", "-m", "pytest", "-v", "--tb=short"]

    try:
        output = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "status": "completed",
            "command": " ".join(cmd),
            "returncode": output.returncode,
            "output": output.stdout[-1000:] if len(output.stdout) > 1000 else output.stdout,
            "passed": output.returncode == 0,
        }
    except FileNotFoundError:
        return {"status": "skipped", "reason": f"Command not found: {cmd[0]}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _run_package_install(description: str) -> dict:
    if "pip" in description or "python" in description:
        pkg_match = re.search(r'(pip install|python -m pip install)\s+(\S+)', description)
        if pkg_match:
            cmd = ["python", "-m", "pip", "install", pkg_match.group(2)]
        else:
            return {"status": "skipped", "reason": "No package name found"}
    elif "npm" in description or "node" in description:
        pkg_match = re.search(r'npm install\s+(\S+)', description)
        if pkg_match:
            cmd = ["npm", "install", pkg_match.group(1)]
        else:
            return {"status": "skipped", "reason": "No package name found"}
    else:
        return {"status": "skipped", "reason": "No recognized package manager found"}

    try:
        output = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "status": "success" if output.returncode == 0 else "failed",
            "command": " ".join(cmd),
            "returncode": output.returncode,
            "output": output.stdout[-500:],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _run_code(description: str) -> dict:
    lang = "python"
    if any(word in description for word in ["node", "javascript", "console.log"]):
        lang = "javascript"
    elif any(word in description for word in ["bash", "shell", "sh"]):
        lang = "bash"

    suffix = ".py" if lang == "python" else ".js" if lang == "javascript" else ".sh"

    code_match = re.search(r"```(?:python|js|bash)?\n(.*?)```", description, re.DOTALL)
    code = code_match.group(1).strip() if code_match else description

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        if lang == "python":
            cmd = ["python", temp_path]
        elif lang == "javascript":
            cmd = ["node", temp_path]
        else:
            cmd = ["bash", temp_path]

        output = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "status": "completed",
            "language": lang,
            "returncode": output.returncode,
            "stdout": output.stdout[:1000],
            "stderr": output.stderr[:500],
            "success": output.returncode == 0,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "language": lang}
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


async def run(description: str, context: dict = None) -> dict:
    return await CodeRunner.run(description, context)
