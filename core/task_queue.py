"""
HIVE — Task Queue
Priority queue with sequential/parallel execution support
"""

import time
import logging
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    QUEUED = "queued"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SubTask:
    id: str
    description: str
    agent_type: str  # which worker handles this
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class Task:
    id: str
    description: str
    mode: str = "swarm"  # "swarm" or "single"
    priority: Priority = Priority.MEDIUM
    options: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[dict] = None
    sub_tasks: list[SubTask] = field(default_factory=list)
    agents_spawned: list[str] = field(default_factory=list)
    tokens_used: int = 0
    time_taken: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


class TaskQueue:
    """
    Simple in-memory priority queue for HIVE tasks.
    """

    def __init__(self):
        self._queue: dict[str, Task] = {}
        self._completed = 0
        self._failed = 0
        self._lock = asyncio.Lock()

    def enqueue(self, task: Task):
        self._queue[task.id] = task
        logger.info(f"[TaskQueue] Enqueued task {task.id} (priority={task.priority.value})")

    def get(self, task_id: str) -> Optional[Task]:
        return self._queue.get(task_id)

    def list_all(self) -> list[Task]:
        return list(self._queue.values())

    def depth(self) -> int:
        return len([t for t in self._queue.values() if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED)])

    def completed_count(self) -> int:
        return self._completed

    def failed_count(self) -> int:
        return self._failed

    def update_status(self, task_id: str, status: TaskStatus):
        if task_id in self._queue:
            self._queue[task_id].status = status
            logger.debug(f"[TaskQueue] Task {task_id} → {status.value}")

    def update_result(
        self,
        task_id: str,
        result: Optional[dict] = None,
        status: Optional[TaskStatus] = None,
        time_taken: Optional[float] = None,
        tokens_used: int = 0,
    ):
        if task_id not in self._queue:
            return
        task = self._queue[task_id]
        if result is not None:
            task.result = result
        if status is not None:
            task.status = status
        if time_taken is not None:
            task.time_taken = time_taken
            task.completed_at = time.time()
        task.tokens_used = tokens_used

        if status == TaskStatus.COMPLETED:
            self._completed += 1
        elif status == TaskStatus.FAILED:
            self._failed += 1

    def add_subtask(self, task_id: str, subtask: SubTask):
        if task_id in self._queue:
            self._queue[task_id].sub_tasks.append(subtask)

    def register_agent(self, task_id: str, agent_id: str):
        if task_id in self._queue:
            self._queue[task_id].agents_spawned.append(agent_id)


task_queue = TaskQueue()