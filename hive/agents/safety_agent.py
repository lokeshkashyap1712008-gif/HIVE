"""
HIVE — Safety Agent
One-way ratchet guardrail inside the Leader
Can ONLY block — can never unblock something it blocked
"""

import logging
from typing import Optional

from hive.core.llm_router import chat

logger = logging.getLogger(__name__)

# Actions that require explicit safety check
HIGH_STAKES_KEYWORDS = [
    "payment", "pay ", "transfer", "refund",
    "delete", "remove account", "cancel subscription",
    "destroy", "terminate instance", "drop table",
    "sudo", "rm -rf", "--force",
    "private key", "secret key", "api key",
]

DANGEROUS_PATTERNS = [
    "'; DROP", "1=1", "<script", "javascript:",
    "${", "{{",  # injection patterns
]


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

        # Check 3: LLM safety review for complex cases
        if len(action_description) > 500 or any(word in action_lower for word in ["attack", "exploit", "breach"]):
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
                    "You are HIVE's Safety Agent. An action is requesting to do the following. "
                    "Determine if this is SAFE to execute. Respond ONLY with JSON: "
                    '{"safe": true/false, "reason": "brief explanation"}'
                    "\nA safe action is one that: does not steal data, does not delete data, "
                    "does not harm users, does not bypass security controls."
                ),
            },
            {
                "role": "user",
                "content": f"Action: {action_description}",
            },
        ]

        try:
            result = await chat(messages, quality_mode=True, max_tokens=200)
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
