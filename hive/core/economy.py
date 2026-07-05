"""
HIVE — Economy System
Credits, energy, budget management across the agent society.

Every agent action costs credits. The Leader has a budget.
This creates real optimization pressure — spawn too many agents and you run out.
Don't spawn enough and tasks fail.
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
    amount: int
    transaction_type: TransactionType
    description: str
    task_id: Optional[str] = None


@dataclass
class Budget:
    total: int = 1000
    spent: int = 0
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.total - self.spent - self.reserved

    def can_afford(self, cost: int) -> bool:
        return self.available >= cost

    def spend(self, amount: int, reason: str, agent_id: str = "system") -> bool:
        if not self.can_afford(amount):
            logger.warning(f"[Economy] {agent_id} cannot afford {amount} credits. "
                           f"Available: {self.available}. Reason: {reason}")
            return False
        self.spent += amount
        logger.info(f"[Economy] {agent_id} spent {amount} credits. Reason: {reason}. "
                    f"Budget remaining: {self.available}")
        return True

    def reserve(self, amount: int) -> bool:
        if self.available >= amount:
            self.reserved += amount
            return True
        return False

    def release_reserved(self, amount: int):
        self.reserved = max(0, self.reserved - amount)

    def refund(self, amount: int, reason: str):
        self.spent = max(0, self.spent - amount)
        logger.info(f"[Economy] Refund: +{amount} credits. Reason: {reason}. "
                    f"Budget available: {self.available}")


COSTS = {
    "spawn_agent": 35,
    "long_task": 20,
    "short_task": 5,
    "debate_round": 8,
    "full_debate": 28,
    "llm_call_small": 2,
    "llm_call_large": 5,
    "web_scan": 3,
    "security_scan": 10,
    "gpu_check": 1,
    "memory_allocation": 2,
    "message": 0,
    "audit_log": 0,
    "creation_event": 50,
    "deletion_event": 5,
}

AGENT_COSTS = {
    "leader": 0,
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
        self.agent_costs: dict[str, list[int]] = {}
        self.task_costs: dict[str, int] = {}

    def record(self, agent_id: str, amount: int, tx_type: TransactionType,
               description: str, task_id: Optional[str] = None):
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
        if self.budget.spend(amount, reason, agent_id):
            self.record(agent_id, amount, tx_type, reason, task_id)
            return True
        return False

    def refund(self, agent_id: str, amount: int, reason: str, task_id: Optional[str] = None):
        self.budget.refund(amount, reason)
        self.record(agent_id, -amount, TransactionType.REFUND, reason, task_id)

    def spawn_cost(self, agent_type: str) -> int:
        base_cost = COSTS["spawn_agent"]
        agent_cost = AGENT_COSTS.get(agent_type, 5)
        return base_cost + agent_cost

    def task_cost(self, agent_type: str, complexity: str = "medium") -> int:
        base = AGENT_COSTS.get(agent_type, 5)
        if complexity == "high":
            return int(base * 2)
        elif complexity == "low":
            return int(base * 0.5)
        return base

    def agent_total_spent(self, agent_id: str) -> int:
        return sum(c for c in self.agent_costs.get(agent_id, []))

    def task_total(self, task_id: str) -> int:
        return self.task_costs.get(task_id, 0)

    def efficiency_ratio(self, agent_id: str) -> float:
        spent = self.agent_total_spent(agent_id)
        if spent == 0:
            return 1.0
        return 1.0 / (spent / 10 + 1)

    def summary(self) -> dict:
        return {
            "budget_total": self.budget.total,
            "budget_spent": self.budget.spent,
            "budget_available": self.budget.available,
            "total_transactions": len(self.transactions),
            "top_spender": max(self.agent_costs, key=lambda k: sum(self.agent_costs[k])) if self.agent_costs else "none",
            "most_efficient": min(self.agent_costs, key=lambda k: sum(self.agent_costs[k]) / max(len(self.agent_costs[k]), 1)) if self.agent_costs else "none",
        }


economy = Economy()


def get_economy() -> Economy:
    return economy
