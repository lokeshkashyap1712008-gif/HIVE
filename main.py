"""
HIVE — Autonomous Hierarchical Agent Swarm
FastAPI entry point
Qwen Cloud Hackathon | Track 3: Agent Society
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import time

from core.config import settings
from core.llm_router import chat, initialize
from core.memory_manager import memory_manager
from core.audit_logger import audit_logger
from core.task_queue import task_queue, Task, TaskStatus
from agents.leader import HiveCore

# ===== LOGGING =====
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [HIVE] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HIVE starting up...")
    logger.info(f"LLM Mode: {'Cloud (DashScope)' if settings.uses_cloud else 'Local (Ollama)'}")
    logger.info(f"Max concurrent agents: {settings.MAX_CONCURRENT_AGENTS}")
    
    # Initialize LLM router
    await initialize()
    
    # Start cleanup crew background task
    cleanup_task = asyncio.create_task(cleanup_crew_loop())
    
    yield
    
    # Shutdown
    cleanup_task.cancel()
    logger.info("HIVE shutting down...")


# ===== APP =====
app = FastAPI(
    title="HIVE — Autonomous Agent Swarm",
    description="A hierarchical multi-agent system with Creator + Deletor agents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== WEBSOCKET MANAGER =====
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
    
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Total: {len(self.active)}")
    
    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Total: {len(self.active)}")
    
    async def broadcast(self, data: dict):
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                pass

ws_manager = ConnectionManager()


# ===== PYDANTIC MODELS =====
class TaskRequest(BaseModel):
    task: str
    mode: str = "swarm"  # "swarm" or "single"
    options: Optional[dict] = None


class BenchmarkRequest(BaseModel):
    benchmark_type: str  # "single_vs_multi", "stress", "fault_tolerance", "memory", "conflict", "adversarial"


# ===== API ROUTES =====

@app.get("/")
async def root():
    return {
        "name": "HIVE",
        "version": "1.0.0",
        "status": "running",
        "llm_mode": "cloud" if settings.uses_cloud else "local",
        "active_agents": memory_manager.active_agent_count(),
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "memory_mb": memory_manager.available_memory_mb(),
        "active_agents": memory_manager.active_agent_count(),
        "queue_depth": task_queue.depth(),
        "swarm_health": memory_manager.swarm_health_score(),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            # Handle incoming messages (e.g., task submissions via WS)
            if data.get("type") == "task":
                result = await handle_task(data["task"], data.get("mode", "swarm"))
                await ws.send_json({"type": "result", "data": result})
            elif data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.post("/api/tasks")
async def create_task(req: TaskRequest):
    """Submit a natural language task for the swarm to execute."""
    task_id = str(uuid.uuid4())[:8]
    task = Task(
        id=task_id,
        description=req.task,
        mode=req.mode,
        options=req.options or {},
        status=TaskStatus.PENDING,
        created_at=time.time(),
    )
    task_queue.enqueue(task)
    logger.info(f"Task {task_id}: submitted — '{req.task[:80]}'")
    
    # Execute asynchronously
    asyncio.create_task(execute_task(task))
    
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/tasks")
async def list_tasks():
    """List all tasks."""
    tasks = task_queue.list_all()
    return {
        "tasks": [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status.value,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
                "tokens_used": t.tokens_used,
                "time_taken": t.time_taken,
            }
            for t in tasks
        ]
    }


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    t = task_queue.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": t.id,
        "description": t.description,
        "status": t.status.value,
        "result": t.result,
        "sub_tasks": t.sub_tasks,
        "agents_spawned": t.agents_spawned,
        "tokens_used": t.tokens_used,
        "time_taken": t.time_taken,
        "created_at": t.created_at,
        "completed_at": t.completed_at,
    }


@app.get("/api/agents")
async def list_agents():
    """List active agents."""
    agents = memory_manager.list_agents()
    return {"agents": agents, "count": len(agents)}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = memory_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/api/agents/{agent_id}/kill")
async def kill_agent(agent_id: str):
    """Force kill an agent."""
    success = memory_manager.kill_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found or cannot be killed")
    audit_logger.log("FORCE_KILL", f"Killed agent {agent_id}", agents_affected=[agent_id])
    return {"status": "killed", "agent_id": agent_id}


@app.get("/api/benchmark")
async def list_benchmarks():
    return {
        "benchmarks": [
            {"id": "single_vs_multi", "name": "Single vs Multi Comparison", "description": "Run 20 tasks as single vs swarm"},
            {"id": "stress", "name": "Swarm Stress Test", "description": "Spawn 20 agents simultaneously"},
            {"id": "fault_tolerance", "name": "Fault Tolerance", "description": "Kill worker mid-task, verify recovery"},
            {"id": "memory", "name": "Memory Pressure", "description": "Low RAM graceful degradation"},
            {"id": "conflict", "name": "Conflict Resolution", "description": "Two agents disagree, Judge resolves"},
            {"id": "adversarial", "name": "Adversarial Robustness", "description": "Malformed input, Safety Agent blocks"},
        ]
    }


@app.post("/api/benchmark/{benchmark_type}")
async def run_benchmark(benchmark_type: str):
    """Run a specific benchmark."""
    valid = ["single_vs_multi", "stress", "fault_tolerance", "memory", "conflict", "adversarial"]
    if benchmark_type not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown benchmark. Must be one of {valid}")
    
    # Import benchmark dynamically
    try:
        if benchmark_type == "single_vs_multi":
            from benchmarks.single_vs_multi import run as run_bm
        elif benchmark_type == "stress":
            from benchmarks.stress_test import run as run_bm
        elif benchmark_type == "fault_tolerance":
            from benchmarks.fault_tolerance import run as run_bm
        elif benchmark_type == "memory":
            from benchmarks.memory_pressure import run as run_bm
        elif benchmark_type == "conflict":
            from benchmarks.conflict_resolution import run as run_bm
        elif benchmark_type == "adversarial":
            from benchmarks.adversarial import run as run_bm
        
        result = await run_bm()
        return {"benchmark": benchmark_type, "result": result}
    except ImportError:
        raise HTTPException(status_code=501, detail="Benchmark not yet implemented")


@app.get("/api/audit")
async def get_audit_log(limit: int = 50, offset: int = 0):
    """Get audit log entries."""
    entries = audit_logger.get_entries(limit=limit, offset=offset)
    return {"entries": entries, "total": audit_logger.total()}


@app.get("/api/metrics")
async def get_metrics():
    """Real-time metrics dashboard data."""
    return {
        "active_agents": memory_manager.active_agent_count(),
        "queued_tasks": task_queue.depth(),
        "memory_mb": memory_manager.available_memory_mb(),
        "memory_percent": memory_manager.memory_percent(),
        "gpu_util": memory_manager.gpu_utilization(),
        "gpu_temp": memory_manager.gpu_temperature(),
        "swarm_health": memory_manager.swarm_health_score(),
        "total_tasks_completed": task_queue.completed_count(),
        "total_tasks_failed": task_queue.failed_count(),
    }


# ===== TASK EXECUTION =====

async def execute_task(task: Task):
    """Execute a task through the Hive Core leader."""
    task_queue.update_status(task.id, TaskStatus.IN_PROGRESS)
    start_time = time.time()
    
    # Broadcast task started
    await ws_manager.broadcast({
        "type": "task_started",
        "task_id": task.id,
        "description": task.description,
    })
    
    try:
        # Initialize Hive Core leader
        leader = HiveCore(task)
        
        # Execute based on mode
        if task.mode == "single":
            result = await leader.execute_single()
        else:
            result = await leader.execute_swarm()
        
        elapsed = time.time() - start_time
        
        task_queue.update_result(
            task.id,
            result=result,
            status=TaskStatus.COMPLETED,
            time_taken=elapsed,
            tokens_used=result.get("tokens_used", 0),
        )
        
        # Broadcast task completed
        await ws_manager.broadcast({
            "type": "task_completed",
            "task_id": task.id,
            "result": result,
            "time_taken": elapsed,
        })
        
        logger.info(f"Task {task.id}: completed in {elapsed:.1f}s")
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Task {task.id} failed: {e}")
        task_queue.update_result(
            task.id,
            result={"error": str(e)},
            status=TaskStatus.FAILED,
            time_taken=elapsed,
        )
        
        await ws_manager.broadcast({
            "type": "task_failed",
            "task_id": task.id,
            "error": str(e),
        })


async def cleanup_crew_loop():
    """Background task that runs cleanup crew every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        try:
            from agents.cleanup_crew import CleanupCrew
            crew = CleanupCrew()
            cleaned = await crew.run()
            if cleaned:
                logger.info(f"Cleanup Crew: removed {cleaned} zombie agents")
        except Exception as e:
            logger.error(f"Cleanup crew error: {e}")


# ===== NATURAL LANGUAGE TASK HANDLER =====
async def handle_task(task_description: str, mode: str = "swarm"):
    """Process a natural language task (used by WebSocket)."""
    task_id = str(uuid.uuid4())[:8]
    task = Task(
        id=task_id,
        description=task_description,
        mode=mode,
        status=TaskStatus.PENDING,
        created_at=time.time(),
    )
    task_queue.enqueue(task)
    asyncio.create_task(execute_task(task))
    return {"task_id": task_id, "status": "queued"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)