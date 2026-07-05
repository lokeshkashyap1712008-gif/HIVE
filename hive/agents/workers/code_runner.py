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
    async def run(description: str, context: dict = None) -> dict:
        description = description.lower()
        context = context or {}

        try:
            if any(word in description for word in ["git", "commit", "push", "pull", "branch", "clone"]):
                return await _run_git(description)
            elif any(word in description for word in ["docker", "container", "image", "build", "dockerfile"]):
                return await _run_docker(description)
            elif any(word in description for word in ["test", "pytest", "jest", "npm test"]):
                return await _run_tests(description)
            elif any(word in description for word in ["install", "pip", "npm", "package"]):
                return await _run_package_install(description)
            elif any(word in description for word in ["run", "execute", "python", "node", "script"]):
                return await _run_code(description)
            else:
                return await _run_code(description)

        except Exception as e:
            logger.error(f"[CodeRunner] Error: {e}")
            return {"status": "error", "error": str(e)}


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
