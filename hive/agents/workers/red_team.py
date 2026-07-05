"""
HIVE — Red Team Agent
Threat modeling, attack simulation, social engineering templates.
"""

import os
import re
import logging
from typing import Optional

from hive.core.llm_router import chat, QWEN_TURBO
from hive.core.audit_logger import audit_logger

logger = logging.getLogger(__name__)


async def _generate_attack_tree(target: str, scope: str) -> dict:
    result = await chat(
        [
            {"role": "system", "content": "You are a red team analyst. Generate an attack tree for the given target.\n\n"
             "Format as:\n"
             "ATTACK TREE:\n"
             "[FINAL GOAL]: [goal]\n"
             "  ├── [Phase 1]\n"
             "  │   ├── [Technique 1]\n"
             "  │   └── [Technique 2]\n"
             "  ├── [Phase 2]\n"
             "  └── [Phase 3]\n\n"
             "Include: initial access, execution, persistence, exfiltration.\n"
             "Rate each technique: [CRITICAL/HIGH/MEDIUM/LOW]"},
            {"role": "user", "content": f"Target: {target}\nScope: {scope}"},
        ],
        model=QWEN_TURBO,
        temperature=0.3,
        max_tokens=1024,
    )
    return {"attack_tree": result["content"], "risk_score": 7}


async def _threat_model(target: str) -> dict:
    result = await chat(
        [
            {"role": "system", "content": "You are a red team threat modeler. "
             "Generate a STRIDE threat model for the given target.\n\n"
             "For each category:\n"
             "S - Spoofing: [threats]\n"
             "T - Tampering: [threats]\n"
             "R - Repudiation: [threats]\n"
             "I - Information Disclosure: [threats]\n"
             "D - Denial of Service: [threats]\n"
             "E - Elevation of Privilege: [threats]\n\n"
             "Then: MITRE ATT&CK techniques relevant to this target\n\n"
             "Finally: RECOMMENDATIONS (top 5 hardening steps)"},
            {"role": "user", "content": f"Target: {target}"},
        ],
        model=QWEN_TURBO,
        temperature=0.3,
        max_tokens=1024,
    )
    return {"threat_model": result["content"]}


async def run(task: str) -> dict:
    audit_logger.log(
        decision_type="RED_TEAM_SCAN",
        reason=f"Red team assessment initiated: {task[:100]}",
        metadata={"action": "threat_modeling", "safety": "authorized_only"},
    )

    target_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', task)
    scope_match = re.search(r'scope[:\s]+([^\n]{10,100})', task, re.IGNORECASE)
    target = target_match.group(0) if target_match else task[:100]
    scope = scope_match.group(1) if scope_match else "web application"

    import asyncio
    attack_tree_result, threat_model_result = await asyncio.gather(
        _generate_attack_tree(target, scope),
        _threat_model(target),
    )

    assessment = await chat(
        [
            {"role": "system", "content": "You are a red team lead. Summarize the threat assessment concisely."},
            {"role": "user", "content": f"Target: {target}\nAttack Tree: {attack_tree_result}\nThreat Model: {threat_model_result}\n\n"
             f"Give: overall risk score (0-10), top 3 threats, and top 3 recommendations."},
        ],
        model=QWEN_TURBO,
        temperature=0.3,
        max_tokens=512,
    )

    content = assessment["content"].lower()
    score_match = re.search(r'(?:risk\s+score|overall.*?)[:\s]*(\d+(?:\.\d+)?)', content)
    risk_score = float(score_match.group(1)) if score_match else 7.0

    return {
        "status": "ok",
        "target": target,
        "scope": scope,
        "attack_tree": attack_tree_result.get("attack_tree", ""),
        "threat_model": threat_model_result.get("threat_model", ""),
        "risk_score": risk_score,
        "risk_level": "critical" if risk_score >= 8 else ("high" if risk_score >= 6 else ("medium" if risk_score >= 4 else "low")),
        "assessment_summary": assessment["content"],
        "safety_notice": "This is a threat modeling exercise. Actual penetration testing requires explicit authorization.",
    }
