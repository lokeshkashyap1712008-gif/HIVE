"""
HIVE — Benchmark: Stress Test
Spawns up to 20 agents simultaneously to test swarm robustness.
"""

import asyncio
import time
import uuid
from core.memory_manager import memory_manager
from core.task_queue import task_queue, Task, SubTask, TaskStatus
from agents.agent_forge import agent_forge

async def _simulate_worker(subtask_id: str, delay: float = 0.5) -> dict:
    """Simulate a worker doing work."""
    await asyncio.sleep(delay)
    return {"subtask_id": subtask_id, "status": "success"}


async def run() -> dict:
    """Spawn maximum agents and verify swarm handles it."""
    print("[Benchmark] Running Stress Test (20 parallel agents)...")

    start = time.time()
    task_id = f"stress_{uuid.uuid4().hex[:8]}"
    task = Task(
        id=task_id,
        description="Stress test: spawn 20 agents simultaneously",
        mode="swarm",
        status=TaskStatus.PENDING,
    )
    task_queue.enqueue(task)

    # Create 20 subtasks
    subtasks = [
        SubTask(id=str(uuid.uuid4())[:8], description=f"Stress task {i}", agent_type="diagnostician")
        for i in range(20)
    ]

    # Spawn all at once
    spawn_tasks = [
        {"agent_type": st.agent_type, "subtask": st}
        for st in subtasks
    ]

    spawned = await agent_forge.spawn_batch(spawn_tasks, task_id=task_id, max_concurrent=20)

    # Run workers in parallel
    worker_tasks = [
        _simulate_worker(s["subtask_id"], delay=0.3 + (i % 3) * 0.1)
        for i, s in enumerate(spawned)
    ]

    results = await asyncio.gather(*worker_tasks, return_exceptions=True)

    elapsed = time.time() - start
    success = len([r for r in results if not isinstance(r, Exception)])
    failed = len([r for r in results if isinstance(r, Exception)])

    return {
        "benchmark": "stress",
        "agents_attempted": 20,
        "agents_spawned": len(spawned),
        "success": success,
        "failures": failed,
        "time_seconds": round(elapsed, 2),
        "max_concurrent_reached": memory_manager.active_agent_count(),
        "passed": success >= 18,  # At least 90% success
    }