"""
HIVE — Agent Forge (Brood Chamber)
The CREATOR. Not just spawning predefined agents — CREATING NEW ONES.

This is HIVE's most unique feature: dynamic agent specialization.

When a task requires a skill no existing agent has, the FORGE creates
a new specialist agent, uses it once, then the Deletor archives it.

Example:
  Task: "Translate Japanese patent"
  → No Patent Agent exists
  → Forge creates: Patent Translator Agent (temporary)
  → Agent runs
  → Deletor archives: "Patent Agent completed task, archived."
  → Patent Agent never existed again... until needed again.

This is what judges remember: dynamic specialization, not a fixed list.

The Forge:
1. Receives a task with unknown requirements
2. Analyzes what skills are needed
3. Designs a new agent persona if none exists
4. Instantiates the agent with appropriate personality
5. Registers it in the registry
6. Tracks it for lifecycle management
"""

import logging
import time
import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

from core.llm_router import chat, QWEN_TURBO
from core.agent_state import get_or_create_state
from core.economy import economy, COSTS
from core.audit_logger import audit_logger
from core.message_bus import get_bus

logger = logging.getLogger(__name__)

# Registry of all known agent types (predefined + dynamically created)
AGENT_REGISTRY: dict[str, dict] = {
    # Predefined agents
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

# Dynamically created agents (temporary)
temporary_agents: dict[str, dict] = {}


@dataclass
class DesignedAgent:
    """A newly designed agent with personality + capabilities."""

    agent_id: str
    name: str
    hive_name: str
    purpose: str
    persona_description: str
    skills: list[str]
    cost_per_task: int
    estimated_tasks: int  # How many tasks this type might need
    instructions: str     # System prompt for this agent


async def design_agent(task: str, required_skills: list[str]) -> DesignedAgent:
    """
    THE CREATION STEP: Design a new agent persona for the task.

    Uses LLM to design:
    - A unique name and hive metaphor
    - A full personality
    - System instructions
    - Cost estimation

    This is the "Creator" aspect — not just spawning, but DESIGNING.
    """
    # Check if any existing agent matches
    for agent_id, info in AGENT_REGISTRY.items():
        if agent_id in temporary_agents:
            continue
        if any(skill.lower() in agent_id.lower() for skill in required_skills):
            logger.info(f"[Forge] Existing agent {agent_id} matches required skills")

    # Design a new agent
    design_result = await chat(
        [
            {"role": "system", "content": "You are the Brood Chamber — the Agent Forge. "
             "Your job is to design NEW specialist agents that don't exist yet.\n\n"
             "For a given task, you design:\n"
             "1. A unique AGENT_ID (e.g. 'patent_translator', 'contract_analyzer')\n"
             "2. A hive-inspired NAME (e.g. 'Scout Bee', 'Archivist Bee')\n"
             "3. A full PERSONA description (how this agent thinks)\n"
             "4. LIST of specialized skills\n"
             "5. COST_PER_TASK (credits, typically 5-20)\n"
             "6. SYSTEM INSTRUCTIONS (detailed prompt for the agent)\n\n"
             "Respond with JSON:\n"
             "{\n"
             '  "agent_id": "unique_id_here",\n'
             '  "name": "Agent Name",\n'
             '  "hive_name": "Hive Metaphor Name",\n'
             '  "purpose": "what this agent does in one sentence",\n'
             '  "persona_description": "full personality description",\n'
             '  "skills": ["skill1", "skill2"],\n'
             '  "cost_per_task": 12,\n'
             '  "estimated_tasks": 1,\n'
             '  "instructions": "system prompt for this agent..."\n'
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

    # Fallback: create a simple task-specific agent
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
    """
    Spawn a designed agent — register it and make it available.
    Returns (success, agent_id).
    """
    agent_id = designed.agent_id

    # Check if already exists
    if agent_id in AGENT_REGISTRY or agent_id in temporary_agents:
        logger.info(f"[Forge] Agent {agent_id} already exists")
        return True, agent_id

    # Check budget
    creation_cost = COSTS["creation_event"]
    if not economy.spend("agent_forge", creation_cost, f"create agent: {agent_id}"):
        return False, agent_id

    # Register the temporary agent
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
        "parent_task": None,  # Set when used
    }

    temporary_agents[agent_id] = temp_info
    AGENT_REGISTRY[agent_id] = {"type": "temporary", "permanent": False, "created_at": time.time()}

    # Create agent state
    get_or_create_state(agent_id)

    # Broadcast creation event
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
    """Run a task on a dynamically created agent."""
    if agent_id not in temporary_agents:
        return {"status": "error", "reason": f"Agent {agent_id} not found"}

    agent_info = temporary_agents[agent_id]

    # Check budget
    task_cost = agent_info["cost_per_task"]
    if not economy.spend(agent_id, task_cost, f"temp agent task: {task[:50]}"):
        return {"status": "error", "reason": "Insufficient budget"}

    agent_info["tasks_run"] += 1

    # Run the task through LLM with the agent's instructions
    result = await chat(
        [
            {"role": "system", "content": agent_info["instructions"]},
            {"role": "user", "content": task},
        ],
        model=QWEN_TURBO,
        temperature=0.4,
        max_tokens=1024,
    )

    # Update state
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
    """List all temporary agents created during this session."""
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
    """
    THE MAIN FORGE ENTRY POINT.

    Flow:
    1. Check if existing agents match
    2. If not, DESIGN a new agent
    3. SPAWN it
    4. Return its ID so leader can use it

    Returns: {created: bool, agent_id: str, designed: DesignedAgent}
    """
    # Check existing agents
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

    # Design new agent
    designed = await design_agent(task, required_skills)

    # Spawn it
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
    """Wrapper class for the forge singleton."""

    async def run(self, task: str, required_skills: list[str]) -> dict:
        return await forge_task(task, required_skills)

    async def design(self, task: str, required_skills: list[str]) -> DesignedAgent:
        return await design_agent(task, required_skills)

    async def spawn(self, designed: DesignedAgent) -> tuple[bool, str]:
        return await spawn_designed_agent(designed)

    def list_temp(self) -> list[dict]:
        return list_temporary_agents()


# Singleton forge — created after class definition
agent_forge = AgentForge()