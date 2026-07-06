"""
HIVE — Debate Protocol
4-round structured inter-agent debate (Qwen Council style).
Round 1: Individual Analysis
Round 2: Cross-Debate (agents respond to each other)
Round 3: Refinement (agents refine based on challenges)
Round 4: Negotiation (reach consensus or escalate)
"""

import asyncio
import logging
from typing import Optional

from hive.core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)


DEBATE_AGENTS = {
    "proposer": {
        "role": "Proposer",
        "instruction": "You argue the strongest good-faith case FOR the proposed action. "
                       "Present the benefits, necessity, and why it should be executed. "
                       "Be thorough but honest — don't hide real concerns.",
    },
    "skeptic": {
        "role": "Skeptic",
        "instruction": "You hunt for what could go wrong: irreversibility, missing authorization, "
                       "fraud, disproportionate stakes, abuse patterns, unintended consequences. "
                       "Be rigorous — this is the safety layer. Find every weakness.",
    },
    "architect": {
        "role": "Architect",
        "instruction": "You evaluate the technical soundness: system design, scalability, "
                       "security implications, long-term maintainability. "
                       "Look for technical debt, coupling issues, and architectural smells.",
    },
    "guardian": {
        "role": "Guardian",
        "instruction": "You evaluate ethics, compliance, and human impact. "
                       "Consider: privacy, consent, accessibility, fairness. "
                       "Flag anything that could harm users, employees, or bystanders.",
    },
}


async def _run_round1_individual(task: str, agents: list[str]) -> dict[str, str]:
    tasks = []
    for agent_id in agents:
        persona = DEBATE_AGENTS.get(agent_id, DEBATE_AGENTS["proposer"])
        system_msg = {
            "role": "system",
            "content": persona["instruction"] + "\n\nFormat your response as:\n" +
                      "FINDING: [Your conclusion in one sentence]\n... Detail: [Evidence, specifics]\n... Impact: [Critical/High/Medium/Low]\n... Proposal: [If applicable, concrete recommendation]",
        }
        tasks.append(chat(
            [
                system_msg,
                {"role": "user", "content": f"Analyze this action: {task}\n\nGive your analysis in INVERTED PYRAMID format: conclusion first, then supporting evidence."},
            ],
            model=QWEN_TURBO,
            temperature=0.3,
            max_tokens=1024,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    round1 = {}
    for i, agent_id in enumerate(agents):
        r = results[i]
        round1[agent_id] = r["content"] if not isinstance(r, Exception) else f"Error: {r}"
    return round1


async def _run_round2_cross_debate(task: str, round1_findings: dict[str, str], agents: list[str]) -> dict[str, str]:
    tasks = []
    for agent_id in agents:
        persona = DEBATE_AGENTS.get(agent_id, DEBATE_AGENTS["proposer"])
        others = [a for a in agents if a != agent_id]
        others_text = "\n".join([
            f"[{DEBATE_AGENTS.get(o, {}).get('role', o.upper())}]: {round1_findings.get(o, 'No finding')}"
            for o in others
        ])

        system_msg = {
            "role": "system",
            "content": persona["instruction"] + "\n\nYou are in ROUND 2: Cross-Debate. "
                       "You must respond to the other agents' findings. "
                       "When referencing another agent, use: 'Agreeing with [Role]...' or 'Challenging [Role]...' format. "
                       "You may strengthen your own position, challenge others, or concede points. "
                       "The goal is truth, not winning.",
        }
        tasks.append(chat(
            [
                system_msg,
                {"role": "user", "content": f"Action: {task}\n\nOther agents' findings:\n{others_text}\n\nYour previous finding: {round1_findings.get(agent_id, '')}\n\nGive your cross-debate response:"},
            ],
            model=QWEN_TURBO,
            temperature=0.4,
            max_tokens=1024,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    round2 = {}
    for i, agent_id in enumerate(agents):
        r = results[i]
        round2[agent_id] = r["content"] if not isinstance(r, Exception) else f"Error: {r}"
    return round2


async def _run_round3_refinement(task: str, round1: dict, round2: dict, agents: list[str]) -> dict[str, str]:
    all_debate_text = "\n\n".join([
        f"[{DEBATE_AGENTS.get(a, {}).get('role', a)}] R1: {r1}\n\nR2: {r2}"
        for a, (r1, r2) in zip(agents, [(round1.get(a, ""), round2.get(a, "")) for a in agents])
    ])

    tasks = []
    for agent_id in agents:
        persona = DEBATE_AGENTS.get(agent_id, DEBATE_AGENTS["proposer"])
        system_msg = {
            "role": "system",
            "content": persona["instruction"] + "\n\nYou are in ROUND 3: Refinement. "
                       "Based on the full debate, refine your final position. "
                       "Concede what you got wrong. Strengthen what held up. "
                       "Give your REVISED, FINAL position.",
        }
        tasks.append(chat(
            [
                system_msg,
                {"role": "user", "content": f"Action: {task}\n\nFull debate so far:\n{all_debate_text}\n\nGive your refined final position:"},
            ],
            model=QWEN_TURBO,
            temperature=0.2,
            max_tokens=768,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    round3 = {}
    for i, agent_id in enumerate(agents):
        r = results[i]
        round3[agent_id] = r["content"] if not isinstance(r, Exception) else f"Error: {r}"
    return round3


async def _run_round4_negotiation(task: str, round1: dict, round2: dict, round3_findings: dict[str, str], agents: list[str]) -> dict:
    findings_text = "\n\n".join([
        f"[{DEBATE_AGENTS.get(a, {}).get('role', a)}]: {f}"
        for a, f in round3_findings.items()
    ])

    result = await chat(
        [
            {"role": "system", "content": "You are the Negotiation Moderator. "
             "Analyze the debate and produce a final verdict.\n\n"
             "VERDICT options:\n"
             "  execute = all concerns addressed, safe to proceed\n"
             "  escalate = uncertain, needs human review\n"
             "  reject = significant unresolvable concerns\n\n"
             "IMPORTANT: consensus (all agreeing) is necessary but NEVER sufficient. "
             "High-stakes and irreversible actions must ESCALATE even with consensus.\n\n"
             "Respond with exactly:\nVERDICT: [execute/escalate/reject]\nREASONING: [2-3 sentences explaining your decision]\nCONFIDENCE: [0.0-1.0]"},
            {"role": "user", "content": f"Action under debate: {task}\n\nDebate summary:\n{findings_text}"},
        ],
        model=QWEN_TURBO,
        temperature=0.1,
        max_tokens=512,
    )

    content = result["content"]
    verdict = "escalate"
    reasoning = content
    confidence = 0.7

    for line in content.split("\n"):
        if line.startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("execute", "escalate", "reject"):
                verdict = v
        if line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip()[:3])
            except ValueError:
                pass

    return {
        "verdict": verdict,
        "reasoning": reasoning,
        "confidence": confidence,
        "all_findings": round3_findings,
        "debate_rounds": {
            "round_1_individual": round1,
            "round_2_cross_debate": round2,
            "round_3_refinement": round3_findings,
            "round_4_negotiation": {"verdict": verdict, "reasoning": reasoning},
        },
    }


async def run_debate(task: str, agent_ids: Optional[list[str]] = None) -> dict:
    import time
    start = time.time()

    if agent_ids is None:
        agent_ids = list(DEBATE_AGENTS.keys())

    logger.info(f"[Debate] Starting debate on: {task[:80]}...")

    r1 = await _run_round1_individual(task, agent_ids)
    r2 = await _run_round2_cross_debate(task, r1, agent_ids)
    r3 = await _run_round3_refinement(task, r1, r2, agent_ids)
    r4 = await _run_round4_negotiation(task, r1, r2, r3, agent_ids)

    elapsed_ms = (time.time() - start) * 1000

    return {
        "task": task,
        "rounds": {
            "round_1_individual": r1,
            "round_2_cross_debate": r2,
            "round_3_refinement": r3,
            "round_4_negotiation": r4,
        },
        "final_position": r4.get("reasoning", ""),
        "consensus_reached": r4.get("verdict") == "execute",
        "verdict": r4.get("verdict", "escalate"),
        "confidence": r4.get("confidence", 0.5),
        "debate_duration_ms": round(elapsed_ms, 1),
        "agents_used": agent_ids,
    }
