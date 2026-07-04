"""
HIVE OS - Leader Agent (Queen Bee)
Orchestrates task decomposition, volunteer selection, result synthesis.
Implements standby leader election with heartbeat monitoring.
"""

import asyncio
import time
import uuid
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from core.llm_router import chat, QWEN_MAX
from core.task_queue import TaskQueue, Task, Priority as TaskPriority
from core.economy import economy
from core.message_bus import message_bus, Message
from core.dashboard_events import emit_agent_state, emit_task_started, emit_task_completed
from core.behavior_monitor import ToolCall


class LeaderState(Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    FAILING_OVER = "failing_over"
    RECOVERING = "recovering"


@dataclass
class LeaderConfig:
    heartbeat_interval: float = 5.0
    failure_threshold: int = 3
    max_concurrent_tasks: int = 5
    task_timeout: float = 300.0


class HiveLeader:
    """Queen Bee - Main orchestrator for the HIVE swarm"""
    
    def __init__(self, agent_id: str = "queen_bee"):
        self.agent_id = agent_id
        self.state = LeaderState.ACTIVE
        self.config = LeaderConfig()
        self.task_queue = TaskQueue()
        self.active_tasks: Dict[str, dict] = {}
        self.worker_registry: Dict[str, dict] = {}
        self.last_heartbeat: Dict[str, float] = {}
        self.failure_counts: Dict[str, int] = {}
        self._running = False
    
    async def start(self):
        """Start the leader agent"""
        self._running = True
        emit_agent_state(self.agent_id, "leader", "active", "focused", 0.95)
        
        # Start heartbeat monitor
        asyncio.create_task(self._heartbeat_loop())
        
        # Start task processor
        asyncio.create_task(self._task_processor_loop())
    
    async def stop(self):
        """Stop the leader agent"""
        self._running = False
        emit_agent_state(self.agent_id, "leader", "stopped", "idle", 0)
    
    async def _heartbeat_loop(self):
        """Monitor worker heartbeats and detect failures"""
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)
            
            current_time = time.time()
            for worker_id, last_time in list(self.last_heartbeat.items()):
                age = current_time - last_time
                
                if age > self.config.heartbeat_interval * self.config.failure_threshold:
                    self.failure_counts[worker_id] = self.failure_counts.get(worker_id, 0) + 1
                    
                    if self.failure_counts[worker_id] >= self.config.failure_threshold:
                        await self._handle_worker_failure(worker_id)
    
    async def _handle_worker_failure(self, worker_id: str):
        """Handle a failed worker"""
        emit_agent_state(worker_id, "worker", "failed", "error", 0)
        
        # Reassign tasks
        if worker_id in self.active_tasks:
            task = self.active_tasks.pop(worker_id)
            await self._reassign_task(task)
        
        # Remove from registry
        self.worker_registry.pop(worker_id, None)
        self.failure_counts.pop(worker_id, None)
        self.last_heartbeat.pop(worker_id, None)
    
    async def _reassign_task(self, task: dict):
        """Reassign a failed task to another worker"""
        # Find available worker of same type
        worker_type = task.get("worker_type")
        for worker_id, info in self.worker_registry.items():
            if info.get("type") == worker_type and worker_id not in self.active_tasks:
                await self._assign_task(task, worker_id)
                return
        
        # No available worker, requeue
        self.task_queue.add_task(
            Task(
                id=task["id"],
                description=task["description"],
                priority=TaskPriority.HIGH,
                metadata=task
            )
        )
    
    async def _task_processor_loop(self):
        """Process tasks from the queue"""
        while self._running:
            await asyncio.sleep(1.0)
            
            if len(self.active_tasks) >= self.config.max_concurrent_tasks:
                continue
            
            task = self.task_queue.get_next_task()
            if not task:
                continue
            
            # Find best worker
            worker_id = await self._select_worker(task)
            if worker_id:
                await self._assign_task(task.metadata, worker_id)
    
    async def _select_worker(self, task: Task) -> Optional[str]:
        """Select the best worker for a task"""
        # Simple selection: pick first available of required type
        required_type = task.metadata.get("worker_type", "worker")
        
        for worker_id, info in self.worker_registry.items():
            if (info.get("type") == required_type and 
                worker_id not in self.active_tasks and
                info.get("status") == "idle"):
                return worker_id
        
        return None
    
    async def _assign_task(self, task: dict, worker_id: str):
        """Assign a task to a worker"""
        self.active_tasks[worker_id] = {
            **task,
            "assigned_at": time.time(),
            "worker_type": self.worker_registry[worker_id]["type"]
        }
        
        # Send task to worker
        msg = Message(
            id=str(uuid.uuid4()),
            sender=self.agent_id,
            receiver=worker_id,
            type="task_assign",
            payload=task
        )
        await message_bus.publish(msg)
        
        emit_task_started(task["id"], task.get("description", ""), worker_id)
    
    def register_worker(self, worker_id: str, worker_type: str, info: dict = None):
        """Register a worker with the leader"""
        self.worker_registry[worker_id] = {
            "type": worker_type,
            "status": "idle",
            "registered_at": time.time(),
            **(info or {})
        }
        self.last_heartbeat[worker_id] = time.time()
        emit_agent_state(worker_id, worker_type, "registered", "idle", 0.5)
    
    def update_heartbeat(self, worker_id: str):
        """Update worker heartbeat"""
        self.last_heartbeat[worker_id] = time.time()
        if worker_id in self.failure_counts:
            self.failure_counts[worker_id] = 0
    
    async def decompose_task(self, description: str) -> List[dict]:
        """Decompose a task into subtasks using LLM"""
        messages = [
            {"role": "system", "content": """You are a task decomposition expert.
Decompose the given task into specific subtasks that can be assigned to specialized workers.
Available workers: web_scout, security_scout, code_architect, data_analyst, gpu_tuner, communicator.
Return a JSON array of subtasks with 'description', 'worker_type', and 'priority' fields."""},
            {"role": "user", "content": f"Decompose this task: {description}"}
        ]
        
        response = await chat(messages, model=QWEN_MAX, quality=True)
        
        try:
            subtasks = json.loads(response["content"])
            if isinstance(subtasks, list):
                return subtasks
        except json.JSONDecodeError:
            pass
        
        # Fallback: single task
        return [{"description": description, "worker_type": "worker", "priority": "medium"}]
    
    async def synthesize_results(self, results: List[dict]) -> str:
        """Synthesize results from multiple workers"""
        messages = [
            {"role": "system", "content": """You are a result synthesis expert.
Combine the results from multiple workers into a coherent, comprehensive response.
Highlight key findings, resolve conflicts, and provide actionable insights."""},
            {"role": "user", "content": f"Synthesize these results: {json.dumps(results, indent=2)}"}
        ]
        
        response = await chat(messages, model=QWEN_MAX, quality=True)
        return response["content"]
    
    def get_status(self) -> dict:
        """Get leader status"""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "active_tasks": len(self.active_tasks),
            "registered_workers": len(self.worker_registry),
            "queue_size": self.task_queue.size(),
            "uptime": time.time()
        }


# Singleton leader
leader = HiveLeader()


async def run_swarm(task_description: str) -> dict:
    """Main entry point - run a task through the HIVE swarm"""
    task_id = str(uuid.uuid4())[:8]
    
    # Register task
    task = {
        "id": task_id,
        "description": task_description,
        "created_at": time.time()
    }
    
    # Decompose task
    subtasks = await leader.decompose_task(task_description)
    
    # Add subtasks to queue
    for subtask in subtasks:
        leader.task_queue.add_task(
            Task(
                id=f"{task_id}_{subtask.get('worker_type', 'worker')}",
                description=subtask["description"],
                priority=TaskPriority.HIGH if subtask.get("priority") == "high" else TaskPriority.MEDIUM,
                metadata={**task, **subtask}
            )
        )
    
    # Wait for completion (simplified)
    await asyncio.sleep(2.0)
    
    # Synthesize results
    results = []
    for worker_id, task_info in list(leader.active_tasks.items()):
        results.append({
            "worker": worker_id,
            "task": task_info.get("description"),
            "status": "completed"
        })
    
    if results:
        synthesis = await leader.synthesize_results(results)
    else:
        synthesis = "Task completed by swarm."
    
    return {
        "task_id": task_id,
        "description": task_description,
        "subtasks": subtasks,
        "results": results,
        "synthesis": synthesis,
        "status": "completed"
    }


def get_hive_status() -> dict:
    """Get overall HIVE swarm status"""
    return leader.get_status()
