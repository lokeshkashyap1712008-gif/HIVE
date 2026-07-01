"""
HIVE — Autonomous Hierarchical Agent Swarm
FastAPI entry point — Phase 2 with economy, emotions, arena, and live dashboard.

Qwen Cloud Hackathon | Track 3: Agent Society
"""

import sys
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

# Defensive imports: provide actionable guidance if required packages are missing
try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    from typing import Optional
except ModuleNotFoundError as e:
    print("ERROR: Missing Python dependency:", e)
    print("Interpreter:", sys.executable)
    print()
    print("To fix:")
    print("  1) Install requirements into the current interpreter:")
    print("       python -m pip install -r requirements.txt")
    print("  2) Or run with the Python that already has the deps:")
    print("       C:/Users/lokes/AppData/Local/Programs/Python/Python313/python.exe main.py")
    print()
    print("Alternatively, run run_server.bat which uses the known-good interpreter.")
    sys.exit(1)

from core.config import settings
from core.llm_router import chat, initialize
from core.memory_manager import memory_manager
from core.audit_logger import audit_logger
from core.task_queue import task_queue, Task, TaskStatus
from core.economy import economy, get_economy
from core.agent_state import get_all_states, get_or_create_state
from core.dashboard_events import get_event_stream, emit_artifact
from core.arena import arena, ArenaMode, run_arena_demo
from agents.leader import run_swarm, get_hive_status
from agents.cleanup_crew import cleanup_crew

# ===== LOGGING =====
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [HIVE] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HIVE starting up — Phase 2...")
    logger.info(f"LLM Mode: {'Cloud (DashScope)' if settings.uses_cloud else 'Local (Ollama)'}")
    logger.info(f"Max concurrent agents: {settings.MAX_CONCURRENT_AGENTS}")

    await initialize()

    # Start background loops
    cleanup_task = asyncio.create_task(_cleanup_loop())
    event_snapshot_task = asyncio.create_task(_event_snapshot_loop())

    yield

    cleanup_task.cancel()
    event_snapshot_task.cancel()
    logger.info("HIVE shutting down...")
    
app = FastAPI(
    title="HIVE — Agent Operating System",
    description="An operating system where AI agents form temporary societies to solve problems.",
    version="2.0.0",
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
    priority: int = 2  # 1=low, 2=medium, 3=high
    options: Optional[dict] = None


class ArenaRequest(BaseModel):
    task: str
    mode: str = "single_vs_society"  # "single_vs_society" or "society_a_vs_society_b"


# ===== SSE DASHBOARD EVENTS =====
@app.get("/events")
async def events():
    """
    Server-Sent Events stream for live dashboard.
    Subscribe to see real-time: agent states, messages, debates, budget changes.
    """
    async def event_generator():
        stream = get_event_stream()
        queue = stream.subscribe()
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event.to_sse()
        except asyncio.TimeoutError:
            # Send keepalive
            yield f": keepalive\n\n"
        except GeneratorExit:
            stream.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/events/alerts")
async def alerts():
    """Get unacknowledged dashboard alerts."""
    return {"alerts": get_event_stream().get_alerts()}


# ===== API ROUTES =====

@app.get("/")
async def root():
    return {
        "name": "HIVE — Agent Operating System",
        "version": "2.0.0",
        "status": "running",
        "thesis": "An operating system where AI agents form temporary societies to solve problems.",
        "llm_mode": "cloud" if settings.uses_cloud else "local",
        "active_agents": memory_manager.active_agent_count(),
        "api_docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "memory_mb": memory_manager.available_memory_mb(),
        "active_agents": memory_manager.active_agent_count(),
        "queue_depth": task_queue.depth(),
        "swarm_health": memory_manager.swarm_health_score(),
        "budget_available": economy.budget.available,
        "budget_total": economy.budget.total,
    }


# ── SWARM TASK EXECUTION ────────────────────────────────────────────────────

@app.post("/api/tasks")
async def create_task(req: TaskRequest):
    """
    Submit a natural language task to the HIVE swarm.

    The swarm will:
    1. Safety-check the task
    2. Optionally debate if high-stakes
    3. Ask agents to volunteer
    4. Execute with emotional state tracking
    5. Synthesize and return results
    """
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

    # Emit task started
    get_event_stream().publish("task_queued", {
        "task_id": task_id,
        "task": req.task[:100],
        "mode": req.mode,
        "priority": req.priority,
    })

    # Execute asynchronously
    asyncio.create_task(execute_task(task))

    return {"task_id": task_id, "status": "queued"}


@app.post("/api/tasks/sync")
async def create_task_sync(req: TaskRequest):
    """
    Submit a task and WAIT for the result (synchronous).
    Returns full result with agent states and debate findings.
    """
    task_id = str(uuid.uuid4())[:8]

    get_event_stream().publish("task_started", {
        "task_id": task_id,
        "task": req.task[:100],
        "mode": req.mode,
    })

    if req.mode == "swarm":
        result = await run_swarm(req.task)
    else:
        result = await chat([
            {"role": "system", "content": "You are HIVE's single agent mode. Be thorough."},
            {"role": "user", "content": req.task},
        ])
        result = {"status": "ok", "result": result["content"]}

    result["task_id"] = task_id

    # Emit completion
    get_event_stream().publish("task_completed", {
        "task_id": task_id,
        "status": result.get("status"),
        "total_cost": result.get("total_cost", 0),
        "leader_mood": result.get("leader_mood", "calm"),
    })

    return result


@app.get("/api/tasks")
async def list_tasks():
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


# ── AGENT MANAGEMENT ────────────────────────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    agents = memory_manager.list_agents()
    return {"agents": agents, "count": len(agents)}


@app.get("/api/agents/states")
async def list_agent_states():
    """Get ALL agent emotional states — the full hive status."""
    states = get_all_states()
    hive = get_hive_status()

    # Group by emotional state
    by_emotion = {}
    for agent_id, state in states.items():
        emo = state.get("emotional_state", "unknown")
        if emo not in by_emotion:
            by_emotion[emo] = []
        by_emotion[emo].append({
            "agent_id": agent_id,
            "confidence": state.get("confidence"),
            "reputation": state.get("reputation"),
            "workload": state.get("workload"),
            "mood": state.get("mood"),
        })

    return {
        "agents": states,
        "by_emotion": by_emotion,
        "hive_status": hive,
        "total": len(states),
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = memory_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/api/agents/{agent_id}/kill")
async def kill_agent(agent_id: str):
    success = memory_manager.kill_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found or cannot be killed")
    audit_logger.log("FORCE_KILL", f"Killed agent {agent_id}", agents_affected=[agent_id])
    get_event_stream().publish("agent_deleted", {"agent_id": agent_id, "reason": "force_kill"})
    return {"status": "killed", "agent_id": agent_id}


# ── ECONOMY ─────────────────────────────────────────────────────────────────

@app.get("/api/economy")
async def get_economy_status():
    """Get full economy status with top spenders and efficiency ratings."""
    econ = get_economy()

    # Per-agent spend breakdown
    agent_spend = {}
    for tx in econ.transactions[-200:]:  # Last 200 transactions
        aid = tx.agent_id
        if tx.amount > 0:
            if aid not in agent_spend:
                agent_spend[aid] = {"total": 0, "count": 0}
            agent_spend[aid]["total"] += tx.amount
            agent_spend[aid]["count"] += 1

    return {
        **econ.summary(),
        "budget_available": econ.budget.available,
        "budget_pct": round(econ.budget.available / econ.budget.total * 100, 1),
        "agent_spend": agent_spend,
        "recent_transactions": [
            {"agent": tx.agent_id, "amount": tx.amount, "type": tx.transaction_type.value, "desc": tx.description}
            for tx in econ.transactions[-20:]
        ],
    }


# ── ARENA (Single vs Society) ────────────────────────────────────────────────

@app.post("/api/arena")
async def run_arena(req: ArenaRequest):
    """
    Run a Single Agent vs Society match.
    Both sides get the SAME task. Live scoring reveals which wins.

    This is the hackathon demo moment.
    """
    mode = ArenaMode.SINGLE_VS_SOCIETY if req.mode == "single_vs_society" else ArenaMode.SOCIETY_A_VS_SOCIETY_B

    get_event_stream().publish("arena", {
        "phase": "match_requested",
        "task_preview": req.task[:80],
        "mode": req.mode,
    })

    match = await arena.run_match(req.task, mode)

    return match.summary()


@app.post("/api/arena/demo")
async def run_arena_demo_endpoint():
    """
    Run the curated hackathon demo — shows the full arena with scoring.
    Returns the demo match result.
    """
    match = await run_arena_demo()
    return match.summary()


@app.get("/api/arena/status")
async def get_arena_status():
    """Get arena status and leaderboard."""
    return arena.get_arena_status()


# ── HIVE STATUS ─────────────────────────────────────────────────────────────

@app.get("/api/hive")
async def get_hive():
    """Get full hive status — the dashboard overview."""
    return await get_hive_status()


# ── CLEANUP ─────────────────────────────────────────────────────────────────

@app.post("/api/cleanup")
async def run_cleanup():
    """Manually trigger the cleanup crew."""
    result = cleanup_crew.run_full_cleanup()
    return result


@app.get("/api/cleanup/status")
async def get_cleanup_status():
    """Get cleanup crew status."""
    return cleanup_crew.get_cleanup_status()


# ── BENCHMARKS ──────────────────────────────────────────────────────────────

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
    valid = ["single_vs_multi", "stress", "fault_tolerance", "memory", "conflict", "adversarial"]
    if benchmark_type not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown benchmark. Must be one of {valid}")

    try:
        if benchmark_type == "single_vs_multi":
            from core.single_vs_multi import run_benchmark as run_bm
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
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Benchmark not yet implemented: {e}")


# ── AUDIT & METRICS ─────────────────────────────────────────────────────────

@app.get("/api/audit")
async def get_audit_log(limit: int = 50, offset: int = 0):
    entries = audit_logger.get_entries(limit=limit, offset=offset)
    return {"entries": entries, "total": audit_logger.total()}


@app.get("/api/metrics")
async def get_metrics():
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
        "budget_available": economy.budget.available,
    }


# ── WEBSOCKET ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "task":
                result = await handle_task(data["task"], data.get("mode", "swarm"))
                await ws.send_json({"type": "result", "data": result})
            elif data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif data.get("type") == "arena":
                result = await arena.run_match(data["task"], ArenaMode.SINGLE_VS_SOCIETY)
                await ws.send_json({"type": "arena_result", "data": result.summary()})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── BACKGROUND LOOPS ────────────────────────────────────────────────────────

async def _cleanup_loop():
    """Run cleanup crew every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        try:
            result = cleanup_crew.run_full_cleanup()
            if result.get("agents_deleted", 0) > 0:
                logger.info(f"Cleanup: freed {result.get('total_memory_freed_mb', 0)}MB, "
                            f"deleted {result['agents_deleted']} agents")
        except Exception as e:
            logger.error(f"Cleanup crew error: {e}")


async def _event_snapshot_loop():
    """Send hive status snapshots to dashboard every 5 seconds."""
    while True:
        await asyncio.sleep(5)
        try:
            from core.dashboard_events import emit_hive_status_snapshot
            emit_hive_status_snapshot()
        except Exception as e:
            logger.error(f"Event snapshot error: {e}")


# ── TASK EXECUTION ───────────────────────────────────────────────────────────

async def execute_task(task: Task):
    task_queue.update_status(task.id, TaskStatus.IN_PROGRESS)
    start_time = time.time()

    get_event_stream().publish("task_started", {
        "task_id": task.id,
        "description": task.description[:100],
    })

    try:
        if task.mode == "single":
            result = await chat([
                {"role": "system", "content": "You are HIVE single agent mode."},
                {"role": "user", "content": task.description},
            ])
            result = {"status": "ok", "result": result["content"]}
        else:
            result = await run_swarm(task.description)

        elapsed = time.time() - start_time

        task_queue.update_result(
            task.id,
            result=result,
            status=TaskStatus.COMPLETED,
            time_taken=elapsed,
            tokens_used=result.get("tokens_used", 0),
        )

        get_event_stream().publish("task_completed", {
            "task_id": task.id,
            "status": result.get("status"),
            "duration_s": elapsed,
            "total_cost": result.get("total_cost", 0),
            "leader_mood": result.get("leader_mood"),
        })

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

        get_event_stream().publish("task_failed", {
            "task_id": task.id,
            "error": str(e),
        })

        await ws_manager.broadcast({
            "type": "task_failed",
            "task_id": task.id,
            "error": str(e),
        })


async def handle_task(task_description: str, mode: str = "swarm"):
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