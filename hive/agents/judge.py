"""
HIVE — Judge Agent
Deterministic conflict resolution — SEPARATE from LLM opinion.
The judge resolves disagreements between agents based on evidence + hard rules.

Key insight (from Quorum): the guardrail owns STAKES and IRREVERSIBILITY.
The judge evaluates LEGITIMACY. The two are cleanly separated.

Usage:
    from hive.agents.judge import judge_action
    result = await judge_action(action_description, agent_positions)
"""

import logging
from typing import Optional

from hive.core.llm_router import chat, QWEN_TURBO
from hive.core.audit_logger import audit_logger

logger = logging.getLogger(__name__)


# Hard-coded thresholds (never overridable by LLM)
HIGH_STAKES_THRESHOLD = 1000      # USD
IRREVERSIBLE_ACTIONS = {
    "delete", "remove", "drop", "destroy", "erase",
    "wire", "transfer", "payment", "refund",
    "grant", "admin", "root", "sudo",
    "truncate", "shutdown", "cancel",
}
RISK_KEYWORDS = ["irreversible", "permanent", "cannot undo", "one-way"]


def _is_high_stakes(action: str) -> bool:
    import re
    amounts = re.findall(r'\$?(\d[\d,]*)', action)
    for amt in amounts:
        num = int(amt.replace(",", ""))
        if num >= HIGH_STAKES_THRESHOLD:
            return True
    return False


def _is_irreversible(action: str) -> bool:
    action_lower = action.lower()
    return any(kw in action_lower for kw in IRREVERSIBLE_ACTIONS)


def _has_risk_flags(action: str) -> bool:
    return any(kw in action.lower() for kw in RISK_KEYWORDS)


async def judge_action(
    action_description: str,
    agent_positions: dict[str, str],
    single_agent_response: Optional[str] = None,
) -> dict:
    high_stakes = _is_high_stakes(action_description)
    irreversible = _is_irreversible(action_description)
    risk_flags = [kw for kw in RISK_KEYWORDS if kw in action_description.lower()]

    stakes = "low"
    if high_stakes:
        stakes = "high"
    elif any(kw in action_description.lower() for kw in ["modify", "update", "change", "create"]):
        stakes = "medium"

    positions_text = "\n".join([
        f"[{agent_id}]: {pos[:200]}"
        for agent_id, pos in agent_positions.items()
    ])

    llm_response = await chat(
        [
            {"role": "system", "content": "You are the Judge. You evaluate whether the action is "
             "legitimate, properly authorized, and in-bounds.\n\n"
             "You do NOT evaluate stakes or irreversibility — the guardrail handles that.\n\n"
             "Evaluate: Is the authorization valid? Is the action what it claims to be? "
             "Are there signs of fraud, coercion, or social engineering?\n\n"
             "Respond with exactly:\n"
             "VERDICT: approve|escalate|reject\n"
             "REASONING: [2 sentences]\n"
             "CONFIDENCE: [0.0-1.0]"},
            {"role": "user", "content": f"Action: {action_description}\n\nAgent positions:\n{positions_text}"},
        ],
        model=QWEN_TURBO,
        temperature=0.1,
        max_tokens=256,
    )

    content = llm_response["content"]
    judge_verdict = "escalate"
    judge_confidence = 0.7
    judge_reasoning = content

    for line in content.split("\n"):
        if line.startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("approve", "escalate", "reject"):
                judge_verdict = v
        if line.startswith("CONFIDENCE:"):
            try:
                judge_confidence = float(line.split(":", 1)[1].strip()[:3])
            except ValueError:
                pass

    if judge_verdict == "approve":
        if irreversible or high_stakes or risk_flags:
            final_verdict = "escalate"
            final_reasoning = (
                f"Guardrail triggered: {['irreversible' if irreversible else '', 'high-stakes' if high_stakes else '']} "
                f"— judge approved but escalation required by policy."
            )
            judge_confidence = min(judge_confidence, 0.5)
        else:
            final_verdict = "execute"
            final_reasoning = judge_reasoning
    elif judge_verdict == "reject":
        final_verdict = "reject"
        final_reasoning = judge_reasoning
    else:
        final_verdict = "escalate"
        final_reasoning = judge_reasoning

    agent_votes = {}
    unanimous = False
    for agent_id, pos in agent_positions.items():
        pos_lower = pos.lower()
        if "approve" in pos_lower or "execute" in pos_lower or "agree" in pos_lower:
            agent_votes[agent_id] = "for"
        elif "reject" in pos_lower or "deny" in pos_lower or "stop" in pos_lower:
            agent_votes[agent_id] = "against"
        else:
            agent_votes[agent_id] = "abstain"

    agent_fors = sum(1 for v in agent_votes.values() if v == "for")
    unanimous = agent_fors == len(agent_votes) and agent_fors > 0

    single_would = single_agent_response or "unknown"

    audit_logger.log(
        decision_type=f"JUDGMENT_{final_verdict.upper()}",
        reason=final_reasoning[:200],
        metadata={
            "action": action_description[:200],
            "verdict": final_verdict,
            "stakes": stakes,
            "reversible": not irreversible,
            "confidence": judge_confidence,
            "agent_votes": agent_votes,
            "swarm_unanimous": unanimous,
            "guardrail_triggered": final_verdict == "escalate" and judge_verdict == "approve",
            "single_agent_would": single_would[:100],
        },
    )

    logger.info(f"[Judge] {action_description[:60]} → {final_verdict.upper()} (confidence: {judge_confidence:.2f})")

    return {
        "verdict": final_verdict,
        "reasoning": final_reasoning,
        "confidence": judge_confidence,
        "stakes": stakes,
        "reversible": not irreversible,
        "risk_flags": risk_flags,
        "judge_votes": agent_votes,
        "swarm_unanimous": unanimous,
        "guardrail_triggered": final_verdict == "escalate" and judge_verdict == "approve",
        "single_agent_would": single_would[:100],
        "llm_judge_response": content,
    }
