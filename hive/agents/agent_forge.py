"""
HIVE — Agent Forge (Brood Chamber)
The CREATOR. Not just spawning predefined agents — CREATING NEW ONES.

When a task requires a skill no existing agent has, the FORGE creates
a new specialist agent, uses it once, then the Deletor archives it.
"""

import logging
import time
import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

from hive.core.llm_router import chat, QWEN_TURBO
from hive.core.agent_state import get_or_create_state
from hive.core.economy import economy, COSTS
from hive.core.audit_logger import audit_logger
from hive.core.message_bus import get_bus

logger = logging.getLogger(__name__)

AGENT_REGISTRY: dict[str, dict] = {
    "leader": {"type": "core", "permanent": True, "created_at": 0},
    "agent_forge": {"type": "core", "permanent": True, "created_at": 0},
    "cleanup_crew": {"type": "core", "permanent": True, "created_at": 0},
    "web_scout": {"type": "worker", "permanent": True, "created_at": 0},
    "account_manager": {"type": "worker", "permanent": True, "created_at": 0},
    "payment_agent": {"type": "worker", "permanent": True, "created_at": 0},
    "cloud_tester": {"type": "worker", "permanent": True, "created_at": 0},
    "code_runner": {"type": "worker", "permanent": True, "created_at": 0},
    "diagnostician": {"type": "worker", "permanent": True, "created_at": 0},
    "security_scout": {"type": "worker", "permanent": True, "created_at": 0},
    "code_architect": {"type": "worker", "permanent": True, "created_at": 0},
    "report_agent": {"type": "worker", "permanent": True, "created_at": 0},
    "red_team": {"type": "worker", "permanent": True, "created_at": 0},
    "data_analyst": {"type": "worker", "permanent": True, "created_at": 0},
    "gpu_tuner": {"type": "worker", "permanent": True, "created_at": 0},
    "scheduler": {"type": "worker", "permanent": True, "created_at": 0},
    "communicator": {"type": "worker", "permanent": True, "created_at": 0},
    "judge": {"type": "core", "permanent": True, "created_at": 0},
    "safety_agent": {"type": "core", "permanent": True, "created_at": 0},
}

temporary_agents: dict[str, dict] = {}


@dataclass
class DesignedAgent:
    agent_id: str
    name: str
    hive_name: str
    purpose: str
    persona_description: str
    skills: list[str]
    cost_per_task: int
    estimated_tasks: int
    instructions: str


async def design_agent(task: str, required_skills: list[str]) -> DesignedAgent:
    design_result = await chat(
        [
            {"role": "system", "content": "You are the Brood Chamber — the Agent Forge. "
             "Your job is to design NEW specialist agents that don't exist yet.\n\n"
             "For a given task, you design:\n"
             "1. A unique AGENT_ID\n"
             "2. A hive-inspired NAME\n"
             "3. A full PERSONA description\n"
             "4. LIST of specialized skills\n"
             "5. COST_PER_TASK (credits, typically 5-20)\n"
             "6. SYSTEM INSTRUCTIONS (detailed prompt)\n\n"
             "Respond with JSON:\n"
             "{\n"
             '  "agent_id": "unique_id_here",\n'
             '  "name": "Agent Name",\n'
             '  "hive_name": "Hive Metaphor Name",\n'
             '  "purpose": "what this agent does",\n'
             '  "persona_description": "full personality description",\n'
             '  "skills": ["skill1", "skill2"],\n'
             '  "cost_per_task": 12,\n'
             '  "estimated_tasks": 1,\n'
             '  "instructions": "system prompt..."\n'
             "}"},
            {"role": "user", "content": f"Design a specialist agent for this task:\n{task}\n\nRequired skills: {', '.join(required_skills)}"},
        ],
        model=QWEN_TURBO,
        temperature=0.5,
        max_tokens=1024,
    )

    import re, json
    json_match = re.search(r'\{.*\}', design_result["content"], re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return DesignedAgent(
                agent_id=data["agent_id"],
                name=data["name"],
                hive_name=data["hive_name"],
                purpose=data["purpose"],
                persona_description=data["persona_description"],
                skills=data["skills"],
                cost_per_task=data.get("cost_per_task", 10),
                estimated_tasks=data.get("estimated_tasks", 1),
                instructions=data["instructions"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[Forge] Could not parse design: {e}")

    agent_id = f"temp_{uuid.uuid4().hex[:8]}"
    return DesignedAgent(
        agent_id=agent_id,
        name=task[:30],
        hive_name="Specialist Bee",
        purpose=task[:100],
        persona_description="Task specialist designed for this specific job.",
        skills=required_skills,
        cost_per_task=10,
        estimated_tasks=1,
        instructions=f"You are a specialist agent. Task: {task}\n\nBe thorough and report back.",
    )


async def spawn_designed_agent(designed: DesignedAgent) -> tuple[bool, str]:
    agent_id = designed.agent_id

    if agent_id in AGENT_REGISTRY or agent_id in temporary_agents:
        return True, agent_id

    creation_cost = COSTS["creation_event"]
    if not economy.spend("agent_forge", creation_cost, f"create agent: {agent_id}"):
        return False, agent_id

    temp_info = {
        "type": "temporary",
        "permanent": False,
        "created_at": time.time(),
        "name": designed.name,
        "hive_name": designed.hive_name,
        "purpose": designed.purpose,
        "persona": designed.persona_description,
        "skills": designed.skills,
        "cost_per_task": designed.cost_per_task,
        "tasks_run": 0,
        "tasks_succeeded": 0,
        "instructions": designed.instructions,
        "parent_task": None,
    }

    temporary_agents[agent_id] = temp_info
    AGENT_REGISTRY[agent_id] = {"type": "temporary", "permanent": False, "created_at": time.time()}

    get_or_create_state(agent_id)

    bus = get_bus()
    bus.publish("hive", "creation_event", {
        "agent_id": agent_id,
        "name": designed.name,
        "hive_name": designed.hive_name,
        "purpose": designed.purpose,
    })

    audit_logger.log(
        decision_type="AGENT_CREATED",
        reason=f"Created dynamic agent: {agent_id} ({designed.name})",
        metadata={
            "agent_id": agent_id,
            "name": designed.name,
            "purpose": designed.purpose,
            "cost": creation_cost,
        },
    )

    logger.info(f"[Forge] Created agent: {agent_id} ({designed.name})")
    return True, agent_id


async def run_designed_agent(agent_id: str, task: str) -> dict:
    if agent_id not in temporary_agents:
        return {"status": "error", "reason": f"Agent {agent_id} not found"}

    agent_info = temporary_agents[agent_id]

    task_cost = agent_info["cost_per_task"]
    if not economy.spend(agent_id, task_cost, f"temp agent task: {task[:50]}"):
        return {"status": "error", "reason": "Insufficient budget"}

    agent_info["tasks_run"] += 1

    result = await chat(
        [
            {"role": "system", "content": agent_info["instructions"]},
            {"role": "user", "content": task},
        ],
        model=QWEN_TURBO,
        temperature=0.4,
        max_tokens=1024,
    )

    state = get_or_create_state(agent_id)
    state.task_completed(success=True)

    agent_info["tasks_succeeded"] += 1
    agent_info["parent_task"] = task[:100]

    return {
        "status": "ok",
        "agent_id": agent_id,
        "result": result["content"],
        "tokens_used": result.get("tokens", 0),
        "confidence": result.get("confidence", 0.7),
        "cost": task_cost,
    }


def list_temporary_agents() -> list[dict]:
    return [
        {
            "agent_id": aid,
            "name": info["name"],
            "hive_name": info["hive_name"],
            "purpose": info["purpose"],
            "tasks_run": info["tasks_run"],
            "tasks_succeeded": info["tasks_succeeded"],
            "cost_per_task": info["cost_per_task"],
            "age_seconds": round(time.time() - info["created_at"], 1),
        }
        for aid, info in temporary_agents.items()
    ]


async def forge_task(task: str, required_skills: list[str]) -> dict:
    existing = [
        aid for aid in AGENT_REGISTRY
        if aid not in temporary_agents and
        any(s.lower() in aid.lower() for s in required_skills)
    ]

    if existing:
        return {
            "created": False,
            "agent_id": existing[0],
            "reason": "Existing agent available",
        }

    designed = await design_agent(task, required_skills)
    success, agent_id = await spawn_designed_agent(designed)

    if not success:
        return {
            "created": False,
            "agent_id": None,
            "reason": "Insufficient budget for creation",
        }

    return {
        "created": True,
        "agent_id": agent_id,
        "designed": {
            "name": designed.name,
            "hive_name": designed.hive_name,
            "purpose": designed.purpose,
            "skills": designed.skills,
        },
    }


class AgentForge:
    async def run(self, task: str, required_skills: list[str]) -> dict:
        return await forge_task(task, required_skills)

    async def design(self, task: str, required_skills: list[str]) -> DesignedAgent:
        return await design_agent(task, required_skills)

    async def spawn(self, designed: DesignedAgent) -> tuple[bool, str]:
        return await spawn_designed_agent(designed)

    def list_temp(self) -> list[dict]:
        return list_temporary_agents()


agent_forge = AgentForge()
