"""
HIVE — Scheduler Agent
Cron parsing, task scheduling, retry logic with exponential backoff.
"""

import time
import uuid
import logging
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    cron_expr: Optional[str] = None
    scheduled_at: Optional[float] = None
    next_run: Optional[float] = None
    last_run: Optional[float] = None
    max_retries: int = 3
    current_retry: int = 0
    backoff_seconds: float = 1.0
    timeout_seconds: float = 300.0
    state: TaskState = TaskState.PENDING
    last_result: str = ""
    last_error: str = ""


class Scheduler:
    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}

    def schedule_once(self, description: str, run_at: Optional[float] = None,
                      timeout: float = 300.0, max_retries: int = 3) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = ScheduledTask(
            id=task_id,
            description=description,
            scheduled_at=run_at or time.time(),
            next_run=run_at or time.time(),
            timeout_seconds=timeout,
            max_retries=max_retries,
        )
        self._tasks[task_id] = task
        return task_id

    def schedule_cron(self, description: str, cron_expr: str,
                      timeout: float = 300.0) -> tuple[str, str]:
        try:
            from croniter import croniter
        except ImportError:
            return "", "croniter not installed. Run: pip install croniter"

        task_id = str(uuid.uuid4())[:8]
        now = time.time()
        cron = croniter(cron_expr, now)
        next_run = cron.get_next()

        task = ScheduledTask(
            id=task_id,
            description=description,
            cron_expr=cron_expr,
            next_run=next_run,
            timeout_seconds=timeout,
        )
        self._tasks[task_id] = task

        from datetime import datetime
        next_str = datetime.fromtimestamp(next_run).isoformat()
        return task_id, next_str

    def _retry_task(self, task: ScheduledTask) -> bool:
        if task.current_retry >= task.max_retries:
            task.state = TaskState.FAILED
            task.last_error = f"Max retries ({task.max_retries}) reached"
            return False

        task.current_retry += 1
        delay = task.backoff_seconds * (2 ** (task.current_retry - 1))
        task.next_run = time.time() + delay
        task.state = TaskState.RETRYING
        return True

    def mark_complete(self, task_id: str, result: str):
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.state = TaskState.COMPLETED
            task.last_result = result
            task.last_run = time.time()

            if task.cron_expr:
                try:
                    from croniter import croniter
                    cron = croniter(task.cron_expr, int(time.time()))
                    task.next_run = cron.get_next()
                    task.state = TaskState.PENDING
                    task.current_retry = 0
                except Exception:
                    pass

    def mark_failed(self, task_id: str, error: str):
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.last_error = error
            task.last_run = time.time()
            self._retry_task(task)

    def mark_running(self, task_id: str):
        if task_id in self._tasks:
            self._tasks[task_id].state = TaskState.RUNNING

    def cancel(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].state = TaskState.CANCELLED
            return True
        return False

    def get_ready_tasks(self) -> list[ScheduledTask]:
        now = time.time()
        ready = []
        for task in self._tasks.values():
            if task.state in (TaskState.PENDING, TaskState.RETRYING):
                if task.next_run and task.next_run <= now:
                    ready.append(task)
        return ready

    def get_status(self, task_id: str) -> Optional[dict]:
        if task_id not in self._tasks:
            return None
        t = self._tasks[task_id]
        from datetime import datetime
        return {
            "id": t.id,
            "description": t.description[:100],
            "state": t.state.value,
            "next_run": datetime.fromtimestamp(t.next_run).isoformat() if t.next_run else None,
            "last_run": datetime.fromtimestamp(t.last_run).isoformat() if t.last_run else None,
            "retry": f"{t.current_retry}/{t.max_retries}",
            "cron": t.cron_expr,
        }

    def list_all(self) -> list[dict]:
        return [self.get_status(tid) for tid in self._tasks]

    def is_timed_out(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        if task.state != TaskState.RUNNING:
            return False
        elapsed = time.time() - (task.last_run or time.time())
        return elapsed > task.timeout_seconds


scheduler = Scheduler()


async def run(task: str) -> dict:
    from hive.core.llm_router import chat, QWEN_TURBO

    task_lower = task.lower()

    if "schedule" in task_lower or "cron" in task_lower or "run at" in task_lower:
        result = await chat(
            [{"role": "system", "content": "Parse this scheduling request. Return JSON with: "
             "type (once|cron), description (what to run), time (ISO or cron expr), timeout_seconds (int), max_retries (int)."},
             {"role": "user", "content": task}],
            model=QWEN_TURBO,
            max_tokens=256,
        )

        import re, json
        json_match = re.search(r'\{[^}]+\}', result["content"], re.DOTALL)
        if not json_match:
            return {"status": "error", "message": "Could not parse scheduling request"}

        parsed = json.loads(json_match.group(0))

        desc = parsed.get("description", task)
        ptype = parsed.get("type", "once")

        if ptype == "cron" and parsed.get("time"):
            task_id, next_run = scheduler.schedule_cron(desc, parsed["time"], parsed.get("timeout_seconds", 300))
            return {"status": "ok", "scheduled": True, "task_id": task_id, "next_run": next_run, "type": "cron"}
        else:
            task_id = scheduler.schedule_once(desc, max_retries=parsed.get("max_retries", 3))
            return {"status": "ok", "scheduled": True, "task_id": task_id, "type": "once"}

    elif "list" in task_lower or "status" in task_lower:
        tasks = scheduler.list_all()
        return {"status": "ok", "tasks": tasks}

    elif "cancel" in task_lower:
        import re
        task_id_match = re.search(r'\b[a-z0-9]{8}\b', task)
        if task_id_match:
            task_id = task_id_match.group(0)
            success = scheduler.cancel(task_id)
            return {"status": "ok", "cancelled": success, "task_id": task_id}
        return {"status": "error", "message": "No task ID found"}

    else:
        return {"status": "ok", "message": "Scheduler: use 'schedule [task] at [time]' or 'list tasks' or 'cancel [id]'"}
