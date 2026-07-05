"""Creator Agent — generates Python agent code via Qwen."""

import json
from pathlib import Path
from hive.config import AGENTS_DIR
from hive.llm import QwenClient
from hive.permissions import validate_agent_code
from hive.storage import register_agent

CREATOR_PROMPT = """You are a code generator for HIVE OS. Generate a Python agent class.

The agent must:
1. Be a single class with an __init__(self) method and an execute(self, task, context) method
2. execute() takes a task string and context dict, returns a dict with results
3. Use only standard library imports (no subprocess, os.system, eval, exec)
4. Be self-contained — no external dependencies
5. Include a docstring at the top describing the agent

Context about the task: {task_description}
Tools available to the agent: {tools}

Return ONLY the Python code, no explanation."""


class CreatorAgent:
    """Generates new agents via Qwen code generation."""

    def __init__(self, llm: QwenClient):
        self.llm = llm

    async def create_agent(self, name: str, description: str,
                           task_description: str,
                           tools: list[str] = None,
                           risk_tier: str = "moderate") -> dict:
        """Generate, validate, and save a new agent."""
        if tools is None:
            tools = ["read_file", "list_directory", "edit_file"]

        prompt = CREATOR_PROMPT.format(
            task_description=task_description,
            tools=", ".join(tools),
        )

        # Generate code
        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.chat(messages)
        code = self.llm.extract_response(result)

        # Clean up — extract just the Python code
        code = self._extract_code(code)

        # Validate
        valid, reason = validate_agent_code(code)
        if not valid:
            return {"error": f"Code validation failed: {reason}", "code": code}

        # Save to disk
        agent_path = AGENTS_DIR / f"{name}.py"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        header = f'"""Agent: {name} — {description}"""\n\n'
        agent_path.write_text(header + code, encoding="utf-8")

        return {
            "name": name,
            "path": str(agent_path),
            "code": code,
            "risk_tier": risk_tier,
        }

    def _extract_code(self, text: str) -> str:
        """Extract Python code from LLM response."""
        # Try to extract from markdown code block
        if "```python" in text:
            start = text.index("```python") + 9
            end = text.index("```", start)
            return text[start:end].strip()
        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()
        return text.strip()

    async def load_agent(self, name: str) -> str | None:
        """Load agent code from disk."""
        agent_path = AGENTS_DIR / f"{name}.py"
        if agent_path.exists():
            return agent_path.read_text(encoding="utf-8")
        return None

    def list_agents(self) -> list[str]:
        """List all generated agents."""
        if not AGENTS_DIR.exists():
            return []
        return [f.stem for f in AGENTS_DIR.glob("*.py")]
