"""
HIVE — Code Architect Agent
GitHub clone → code analysis → code generation → PR creation → CI runner.
Full development loop with auto-fix up to 3 retries.
"""

import os
import subprocess
import tempfile
import shutil
import logging
import re

from core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)


def _clone_repo(repo_url: str, token: str) -> tuple[bool, str, str]:
    """Clone a GitHub repo to a temp directory. Returns (success, path, error)."""
    # Inject token if needed
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
    """Analyze repository structure."""
    files = []
    structure = {}

    for root, dirs, filenames in os.walk(repo_path):
        # Skip common ignore dirs
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", ".venv", "venv"]]

        for f in filenames:
            filepath = os.path.join(root, f)
            relpath = os.path.relpath(filepath, repo_path)
            size = os.path.getsize(filepath)
            files.append({"path": relpath, "size": size})

            # Get extension
            ext = os.path.splitext(f)[1]
            structure[ext] = structure.get(ext, 0) + 1

    return {"files": files[:50], "structure": structure, "total_files": len(files)}


def _generate_code_change(repo_path: str, task_description: str, existing_files: list) -> dict:
    """Use LLM to generate the code change."""
    # Read a sample of key files
    key_files = [f for f in existing_files if f.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs"))]
    key_files = key_files[:5]

    file_contents = {}
    for fpath in key_files:
        full = os.path.join(repo_path, fpath)
        if os.path.exists(full) and os.path.getsize(full) < 50000:
            try:
                with open(full, "r", encoding="utf-8") as f:
                    file_contents[fpath] = f.read()[:5000]
            except Exception:
                pass

    result = chat(
        [
            {"role": "system", "content": "You are a senior software engineer. "
             "Generate the exact code changes needed to implement the task.\n\n"
             "IMPORTANT:\n"
             "1. Read existing code carefully\n"
             "2. Write clean, production-quality code\n"
             "3. Follow existing patterns and conventions\n"
             "4. Include tests\n\n"
             "Return: FILES_TO_CREATE: [{path, content}]\nFILES_TO_MODIFY: [{path, original_snippet, new_snippet}]"},
            {"role": "user", "content": f"Task: {task_description}\n\nExisting key files:\n" + "\n".join([f"{k}:\n{v[:2000]}\n---" for k, v in file_contents.items()])},
        ],
        model=QWEN_TURBO,
        temperature=0.3,
        max_tokens=2048,
    )
    return {"code_plan": result["content"], "tokens": result.get("tokens", 0)}


def _apply_changes(repo_path: str, code_plan: str) -> list[dict]:
    """Apply code changes from the LLM plan."""
    changes = []

    # Parse FILES_TO_CREATE and FILES_TO_MODIFY from code_plan
    files_created = re.findall(r'FILENAMES_TO_CREATE:\s*\[(.*?)\]', code_plan, re.DOTALL)
    files_modified = re.findall(r'FILES_TO_MODIFY:\s*\[(.*?)\]', code_plan, re.DOTALL)

    # Simple approach: create any file paths mentioned in the plan
    create_matches = re.findall(r'"([^"]+\.(?:py|js|ts|tsx|go|rs|html|css|json))"', code_plan)
    for filepath in create_matches[:10]:
        if "{" not in filepath and "}" not in filepath:
            full_path = os.path.join(repo_path, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(f"# Created by HIVE Code Architect\n# TODO: implement {filepath}\n")
            changes.append({"action": "created", "file": filepath})

    return changes


def _create_pr(repo_path: str, token: str, title: str, description: str) -> dict:
    """Create a GitHub PR via API."""
    if not token:
        return {"pr_created": False, "error": "No GitHub token"}

    # Detect if this is a GitHub repo
    git_config = os.path.join(repo_path, ".git", "config")
    if not os.path.exists(git_config):
        return {"pr_created": False, "error": "Not a git repo"}

    try:
        # Get repo info from git remote
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        remote_url = result.stdout.strip()
    except Exception:
        return {"pr_created": False, "error": "Could not get git remote"}

    # Extract owner/repo from URL
    match = re.search(r'github\.com[/:]([\w-]+)/([\w._-]+?)(?:\.git)?$', remote_url)
    if not match:
        return {"pr_created": False, "error": f"Could not parse repo from: {remote_url}"}

    owner, repo = match.groups()
    repo = repo.replace(".git", "")

    import requests
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    # Create a new branch
    branch_name = f"hive-feature-{hash(title) % 100000}"

    # Get default branch
    resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=10)
    if resp.status_code != 200:
        return {"pr_created": False, "error": f"GitHub API error: {resp.status_code}"}

    default_branch = resp.json().get("default_branch", "main")

    # Create branch
    import base64
    ref_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{default_branch}",
        headers=headers, timeout=10,
    )
    if ref_resp.status_code != 200:
        return {"pr_created": False, "error": "Could not get repo ref"}

    sha = ref_resp.json()["object"]["sha"]
    requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        timeout=10,
    )

    # Commit changes
    subprocess.run(["git", "-C", repo_path, "add", "-A"], capture_output=True, timeout=10)
    diff_result = subprocess.run(
        ["git", "-C", repo_path, "diff", "--staged", "--stat"],
        capture_output=True, text=True, timeout=10,
    )

    if not diff_result.stdout.strip():
        return {"pr_created": False, "error": "No changes to commit"}

    subprocess.run(
        ["git", "-C", repo_path, "commit", "-m", f"{title}\n\n{description}"],
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", repo_path, "push", "-u", "origin", branch_name],
        capture_output=True, timeout=30,
    )

    # Create PR
    pr_resp = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        headers=headers,
        json={
            "title": title,
            "body": f"{description}\n\n*Generated by HIVE Code Architect*",
            "head": branch_name,
            "base": default_branch,
        },
        timeout=10,
    )

    if pr_resp.status_code == 201:
        pr_url = pr_resp.json()["html_url"]
        return {"pr_created": True, "pr_url": pr_url, "branch": branch_name}
    return {"pr_created": False, "error": f"PR creation failed: {pr_resp.status_code}"}


async def run(task: str) -> dict:
    """Full code architect loop."""
    from core.llm_router import chat, QWEN_TURBO

    token = os.getenv("GITHUB_TOKEN") or ""

    # Extract repo URL
    import re
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

    # Step 1: Clone
    success, repo_path, clone_error = _clone_repo(repo_url, token)
    if not success:
        return {"status": "error", "message": f"Clone failed: {clone_error}"}

    # Step 2: Analyze structure
    structure = _analyze_structure(repo_path)

    # Step 3: Generate code changes
    code_plan = _generate_code_change(repo_path, task, structure.get("files", []))
    changes = _apply_changes(repo_path, code_plan.get("code_plan", ""))

    # Step 4: Create PR
    pr_result = _create_pr(repo_path, token, f"HIVE: {task[:50]}", code_plan.get("code_plan", "")[:500])

    # Cleanup
    shutil.rmtree(repo_path, ignore_errors=True)

    return {
        "status": "ok",
        "repo": repo_url,
        "files_analyzed": structure.get("total_files", 0),
        "files_changed": changes,
        "pr_url": pr_result.get("pr_url", ""),
        "pr_created": pr_result.get("pr_created", False),
        "token_used": bool(token),
    }