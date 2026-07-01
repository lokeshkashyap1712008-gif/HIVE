"""
HIVE — Economy System
Credits, energy, budget management across the agent society.

Every agent action costs credits. The Leader has a budget.
This creates real optimization pressure — spawn too many agents and you run out.
Don't spawn enough and tasks fail.

Budget decisions become strategic:
- Do I spawn another agent, or work with what I have?
- Do I trust a cheap fast scan or pay for a thorough one?
- Is this task worth the cost of a full 4-round debate?

The economy forces the society to self-organize optimally.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TransactionType(str, Enum):
    SPAWN = "spawn"
    TASK = "task"
    DEBATE = "debate"
    MESSAGE = "message"
    MEMORY = "memory"
    REFUND = "refund"
    PENALTY = "penalty"


@dataclass
class Transaction:
    timestamp: float
    agent_id: str
    amount: int  # positive = cost, negative = refund
    transaction_type: TransactionType
    description: str
    task_id: Optional[str] = None


@dataclass
class Budget:
    total: int = 1000          # Leader starts with 1000 credits
    spent: int = 0
    reserved: int = 0        # Committed but not yet spent

    @property
    def available(self) -> int:
        return self.total - self.spent - self.reserved

    def can_afford(self, cost: int) -> bool:
        return self.available >= cost

    def spend(self, amount: int, reason: str, agent_id: str = "system") -> bool:
        """Attempt to spend credits. Returns False if insufficient budget."""
        if not self.can_afford(amount):
            logger.warning(f"[Economy] {agent_id} cannot afford {amount} credits. "
                           f"Available: {self.available}. Reason: {reason}")
            return False
        self.spent += amount
        logger.info(f"[Economy] {agent_id} spent {amount} credits. Reason: {reason}. "
                    f"Budget remaining: {self.available}")
        return True

    def reserve(self, amount: int) -> bool:
        """Reserve credits for an upcoming expense."""
        if self.available >= amount:
            self.reserved += amount
            return True
        return False

    def release_reserved(self, amount: int):
        self.reserved = max(0, self.reserved - amount)

    def refund(self, amount: int, reason: str):
        """Refund credits back to budget."""
        self.spent = max(0, self.spent - amount)
        logger.info(f"[Economy] Refund: +{amount} credits. Reason: {reason}. "
                    f"Budget available: {self.available}")


# Standard costs for actions
COSTS = {
    "spawn_agent": 35,       # Spawning a worker
    "long_task": 20,         # Complex task with multiple steps
    "short_task": 5,         # Quick single-step task
    "debate_round": 8,       # Each debate round costs credits
    "full_debate": 28,       # 4-round debate
    "llm_call_small": 2,     # Quick LLM call
    "llm_call_large": 5,      # Complex LLM call
    "web_scan": 3,           # Web/URL scan
    "security_scan": 10,     # Full security scan
    "gpu_check": 1,          # GPU status check
    "memory_allocation": 2,  # Per-agent memory reservation
    "message": 0,            # Agent-to-agent messages are free
    "audit_log": 0,          # Audit logging is free
    "creation_event": 50,    # Creating a new agent type
    "deletion_event": 5,    # Deleting an agent
}

# Agent operational costs (per task)
AGENT_COSTS = {
    "leader": 0,            # Leader's cost is born by the hive
    "web_scout": 8,
    "account_manager": 5,
    "payment_agent": 5,
    "cloud_tester": 8,
    "code_runner": 6,
    "diagnostician": 10,
    "security_scout": 12,
    "code_architect": 15,
    "report_agent": 5,
    "red_team": 12,
    "data_analyst": 10,
    "gpu_tuner": 5,
    "scheduler": 3,
    "communicator": 4,
}


class Economy:
    """Central economy manager. Tracks credits across the hive."""

    def __init__(self, initial_budget: int = 1000):
        self.budget = Budget(total=initial_budget)
        self.transactions: list[Transaction] = []
        self.agent_costs: dict[str, list[int]] = {}  # agent_id -> list of costs paid
        self.task_costs: dict[str, int] = {}  # task_id -> total cost

    def record(self, agent_id: str, amount: int, tx_type: TransactionType,
               description: str, task_id: Optional[str] = None):
        """Record a transaction."""
        self.transactions.append(Transaction(
            timestamp=time.time(),
            agent_id=agent_id,
            amount=amount,
            transaction_type=tx_type,
            description=description,
            task_id=task_id,
        ))

        if agent_id not in self.agent_costs:
            self.agent_costs[agent_id] = []
        if amount > 0:
            self.agent_costs[agent_id].append(amount)

        if task_id:
            self.task_costs[task_id] = self.task_costs.get(task_id, 0) + amount

    def spend(self, agent_id: str, amount: int, reason: str,
              tx_type: TransactionType = TransactionType.TASK,
              task_id: Optional[str] = None) -> bool:
        """Attempt to spend credits. Returns False if can't afford."""
        if self.budget.spend(amount, reason, agent_id):
            self.record(agent_id, amount, tx_type, reason, task_id)
            return True
        return False

    def refund(self, agent_id: str, amount: int, reason: str, task_id: Optional[str] = None):
        """Refund credits."""
        self.budget.refund(amount, reason)
        self.record(agent_id, -amount, TransactionType.REFUND, reason, task_id)

    def spawn_cost(self, agent_type: str) -> int:
        """Calculate cost to spawn an agent of given type."""
        base_cost = COSTS["spawn_agent"]
        agent_cost = AGENT_COSTS.get(agent_type, 5)
        return base_cost + agent_cost

    def task_cost(self, agent_type: str, complexity: str = "medium") -> int:
        """Calculate cost for an agent task."""
        base = AGENT_COSTS.get(agent_type, 5)
        if complexity == "high":
            return int(base * 2)
        elif complexity == "low":
            return int(base * 0.5)
        return base

    def agent_total_spent(self, agent_id: str) -> int:
        """Total credits spent by a specific agent."""
        return sum(c for c in self.agent_costs.get(agent_id, []))

    def task_total(self, task_id: str) -> int:
        """Total credits spent on a task."""
        return self.task_costs.get(task_id, 0)

    def efficiency_ratio(self, agent_id: str) -> float:
        """Tasks completed per credit spent. Higher = more efficient."""
        spent = self.agent_total_spent(agent_id)
        if spent == 0:
            return 1.0
        # Normalize: lower cost per task = higher efficiency
        return 1.0 / (spent / 10 + 1)

    def summary(self) -> dict:
        """Get economy summary for dashboard."""
        return {
            "budget_total": self.budget.total,
            "budget_spent": self.budget.spent,
            "budget_available": self.budget.available,
            "total_transactions": len(self.transactions),
            "top_spender": max(self.agent_costs, key=lambda k: sum(self.agent_costs[k])) if self.agent_costs else "none",
            "most_efficient": min(self.agent_costs, key=lambda k: sum(self.agent_costs[k]) / max(len(self.agent_costs[k]), 1)) if self.agent_costs else "none",
        }


# Singleton
economy = Economy()


def get_economy() -> Economy:
    return economy