"""
HIVE — Code Architect Agent
GitHub clone → code analysis → code generation → PR creation.
"""

import os
import subprocess
import tempfile
import shutil
import logging
import re

from hive.core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)


def _clone_repo(repo_url: str, token: str) -> tuple[bool, str, str]:
    if token and "github.com" in repo_url and not repo_url.startswith("https://"):
        repo_url = repo_url.replace("git@github.com:", "https://").replace("git://", "https://")
    if token and "github.com" in repo_url and "@" not in repo_url.split("//")[1]:
        repo_url = repo_url.replace("https://", f"https://{token}@")

    tmp_dir = tempfile.mkdtemp(prefix="hive_clone_")

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True, tmp_dir, ""
        return False, "", result.stderr[:200]
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False, "", str(e)


def _analyze_structure(repo_path: str) -> dict:
    files = []
    structure = {}

    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", ".venv", "venv"]]

        for f in filenames:
            filepath = os.path.join(root, f)
            relpath = os.path.relpath(filepath, repo_path)
            size = os.path.getsize(filepath)
            files.append({"path": relpath, "size": size})

            ext = os.path.splitext(f)[1]
            structure[ext] = structure.get(ext, 0) + 1

    return {"files": files[:50], "structure": structure, "total_files": len(files)}


async def run(task: str) -> dict:
    token = os.getenv("GITHUB_TOKEN") or ""

    repo_match = re.search(r'https?://github\.com/[^\s<>"{}|\\^`\[\]]+|github\.com:[^\s<>"{}|\\^`\[\]]+', task)
    if not repo_match:
        result = await chat(
            [{"role": "system", "content": "Extract any GitHub repository URL from the text."},
             {"role": "user", "content": task}],
            model=QWEN_TURBO,
            max_tokens=128,
        )
        repo_match = re.search(r'https?://github\.com/[^\s<>"{}|\\^`\[\]]+', result["content"])

    if not repo_match:
        return {"status": "error", "message": "No GitHub repo URL found"}

    repo_url = repo_match.group(0)

    success, repo_path, clone_error = _clone_repo(repo_url, token)
    if not success:
        return {"status": "error", "message": f"Clone failed: {clone_error}"}

    structure = _analyze_structure(repo_path)

    code_plan_result = await chat(
        [
            {"role": "system", "content": "You are a senior software engineer. Analyze the repo structure and suggest code changes for the task."},
            {"role": "user", "content": f"Task: {task}\n\nRepo structure:\n{structure}"},
        ],
        model=QWEN_TURBO,
        temperature=0.3,
        max_tokens=2048,
    )

    shutil.rmtree(repo_path, ignore_errors=True)

    return {
        "status": "ok",
        "repo": repo_url,
        "files_analyzed": structure.get("total_files", 0),
        "code_plan": code_plan_result["content"],
        "token_used": bool(token),
    }
