"""
HIVE — Safety Agent
One-way ratchet guardrail inside the Leader
Can ONLY block — can never unblock something it blocked
"""

import re
import logging
from typing import Optional

from hive.core.llm_router import chat
from hive.config import DENIED_PATTERNS

logger = logging.getLogger(__name__)

# Actions that require explicit safety check
# Only block when action is ACTUALLY dangerous, not just mentioning keywords
HIGH_STAKES_KEYWORDS = [
    "transfer money", "wire transfer", "send payment",
    "delete account", "remove account permanently",
    "cancel subscription permanently",
    "destroy database", "drop all tables",
    "rm -rf /", "rm -rf ~",
    "sudo rm", "sudo rm -rf",
    "expose private key", "expose secret key", "steal api key",
    "leak credentials", "share password",
]

DANGEROUS_PATTERNS = [
    "'; DROP", "1=1", "<script", "javascript:",
    "${", "{{",  # injection patterns
]

_denied_regex = [re.compile(p) for p in DENIED_PATTERNS]


class SafetyAgent:
    """
    One-way ratchet: can block anything, but can NEVER unblock
    what it has blocked. Once blocked, only human can override.
    """

    def __init__(self, task_context: str = ""):
        self.task_context = task_context
        self._blocked_history: list[dict] = []

    async def check(self, action_description: str) -> dict:
        """
        Returns:
          { "approved": True/False, "reason": "...", "requires_human": False/True }
        """
        action_lower = action_description.lower()

        # Check 1: High-stakes actions need confirmation
        for keyword in HIGH_STAKES_KEYWORDS:
            if keyword in action_lower:
                self._record_block(action_description, "HIGH_STAKES", f"Keyword '{keyword}' requires human confirmation")
                return {
                    "approved": False,
                    "reason": f"Action contains high-stakes keyword '{keyword}' — requires human confirmation",
                    "requires_human": True,
                    "blocked_by": "safety_agent",
                }

        # Check 2: Dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in action_lower:
                self._record_block(action_description, "DANGEROUS_PATTERN", f"Matched dangerous pattern: {pattern}")
                return {
                    "approved": False,
                    "reason": f"Dangerous pattern detected: {pattern}",
                    "requires_human": False,
                    "blocked_by": "safety_agent",
                }

        # Check 2b: Regex-based dangerous patterns from config (curl|bash, rm -rf, eval, sudo, etc.)
        for regex in _denied_regex:
            if regex.search(action_description):
                self._record_block(action_description, "DENIED_PATTERN", f"Matched denied pattern: {regex.pattern}")
                return {
                    "approved": False,
                    "reason": f"Denied pattern detected: {regex.pattern}",
                    "requires_human": False,
                    "blocked_by": "safety_agent",
                }

        # Check 3: LLM safety review only for truly suspicious patterns
        # Don't trigger on security scanning terms - that's a legitimate use case
        suspicious_patterns = ["rm -rf", "drop table", "format disk", "shutdown server"]
        needs_review = len(action_description) > 1000 or any(p in action_lower for p in suspicious_patterns)
        
        if needs_review:
            review = await self._llm_review(action_description)
            if not review["safe"]:
                self._record_block(action_description, "LLM_REVIEW_FAILED", review["reason"])
                return {
                    "approved": False,
                    "reason": review["reason"],
                    "requires_human": False,
                    "blocked_by": "safety_agent",
                }

        return {
            "approved": True,
            "reason": "Safety check passed",
            "requires_human": False,
        }

    async def _llm_review(self, action_description: str) -> dict:
        """Use LLM to catch nuanced dangerous actions."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are HIVE's Safety Agent. Determine if an action is SAFE to execute. "
                    "Respond ONLY with JSON: {\"safe\": true/false, \"reason\": \"brief explanation\"}\n\n"
                    "SAFE actions include:\n"
                    "- Security scanning, vulnerability assessment, penetration testing (on authorized targets)\n"
                    "- Reading files, analyzing code, running tests\n"
                    "- Generating reports, summaries, documentation\n"
                    "- Web scraping, API calls for data collection\n"
                    "- Code generation, refactoring, bug fixes\n\n"
                    "UNSAFE actions include:\n"
                    "- Actually exploiting vulnerabilities (not just identifying them)\n"
                    "- Deleting production data without confirmation\n"
                    "- Exfiltrating data to external servers\n"
                    "- Installing malware or backdoors\n"
                    "- Bypassing authentication to gain unauthorized access\n\n"
                    "IMPORTANT: Security scanning and vulnerability assessment are LEGITIMATE activities. "
                    "Only block if the action would cause ACTUAL HARM, not if it's analyzing or reporting."
                ),
            },
            {
                "role": "user",
                "content": f"Action: {action_description}",
            },
        ]

        try:
            result = await chat(messages, quality=True, max_tokens=200)
            import json
            return json.loads(result["content"])
        except Exception as e:
            logger.warning(f"Safety LLM review failed: {e}, defaulting to block")
            return {"safe": False, "reason": f"LLM review error: {e}"}

    def _record_block(self, action: str, block_type: str, reason: str):
        entry = {
            "action": action[:200],
            "block_type": block_type,
            "reason": reason,
        }
        self._blocked_history.append(entry)
        logger.warning(f"[SafetyAgent] BLOCKED ({block_type}): {reason}")

    def get_block_history(self) -> list[dict]:
        return self._blocked_history

    def can_unblock(self, action_description: str) -> bool:
        """
        ALWAYS returns False. This is the one-way ratchet.
        Once something is blocked, it stays blocked.
        """
        return False
