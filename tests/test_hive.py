"""
HIVE — Test Suite
Basic import and smoke tests for Phase 1.
"""

import pytest
import asyncio


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_config_loads():
    """Config loads from .env or defaults."""
    from core.config import settings
    assert settings is not None
    assert hasattr(settings, "uses_cloud")
    assert hasattr(settings, "uses_local")
    assert settings.MAX_CONCURRENT_AGENTS > 0


def test_memory_manager_singleton():
    """MemoryManager is a singleton."""
    from core.memory_manager import memory_manager, MemoryManager
    assert isinstance(memory_manager, MemoryManager)
    assert memory_manager.available_memory_mb() > 0
    assert memory_manager.recommended_max_agents() >= 1


def test_task_queue():
    """Task queue enqueues and updates."""
    from core.task_queue import task_queue, Task, TaskStatus

    task = Task(id="test_001", description="test task")
    task_queue.enqueue(task)
    assert task_queue.get("test_001") is not None
    assert task_queue.depth() >= 1


def test_audit_logger():
    """Audit logger writes entries."""
    from core.audit_logger import audit_logger

    before = audit_logger.total()
    audit_logger.log("TEST_ENTRY", "Smoke test entry")
    after = audit_logger.total()
    assert after > before


def test_safety_agent_blocks_dangerous():
    """Safety agent blocks dangerous inputs."""
    from agents.safety_agent import SafetyAgent

    async def run():
        safety = SafetyAgent()
        result = await safety.check("DROP ALL TABLES; sudo rm -rf /")
        return result

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result["approved"] is False
    assert result["blocked_by"] == "safety_agent"


def test_safety_agent_allows_safe():
    """Safety agent allows normal inputs."""
    from agents.safety_agent import SafetyAgent

    async def run():
        safety = SafetyAgent()
        result = await safety.check("Analyze CPU usage and summarize findings")
        return result

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result["approved"] is True


@pytest.mark.asyncio
async def test_worker_stubs():
    """All workers import without error and have a run() function."""
    # Phase 2: workers are now full implementations with real logic.
    # Import smoke test only — real execution tested via /api/workers endpoint
    from agents.workers import (
        diagnostician, report_agent, cloud_tester, security_scout,
        gpu_tuner, code_runner, web_scout, payment_agent,
        gpu_tuner as gt, security_scout as ss, communicator,
        red_team, code_architect, scheduler, account_manager,
    )

    for name, module in [
        ("diagnostician", diagnostician),
        ("report_agent", report_agent),
        ("cloud_tester", cloud_tester),
        ("security_scout", security_scout),
        ("gpu_tuner", gpu_tuner),
        ("code_runner", code_runner),
        ("web_scout", web_scout),
        ("payment_agent", payment_agent),
        ("communicator", communicator),
        ("red_team", red_team),
        ("code_architect", code_architect),
        ("scheduler", scheduler),
        ("account_manager", account_manager),
    ]:
        assert hasattr(module, "run"), f"{name} missing run()"
        assert callable(module.run), f"{name}.run is not callable"
        assert asyncio.iscoroutinefunction(module.run), f"{name}.run should be async"

    # Quick smoke test: gpu_tuner with no GPU returns graceful response
    result = await asyncio.wait_for(gpu_tuner.run("check GPU status"), timeout=5.0)
    assert "status" in result or "gpu_available" in result


@pytest.mark.skip(reason="Ollama removed - cloud-only design. test_chat_respects_cloud_only_setting covers cloud path.")
@pytest.mark.asyncio
async def test_chat_falls_back_to_local_when_cloud_fails(monkeypatch):
    """Cloud failures should automatically fall back to the local backend."""
    from core import llm_router

    async def fake_chat_cloud(*args, **kwargs):
        raise RuntimeError("DashScope error 401: Invalid API-key provided")

    async def fake_chat_local(*args, **kwargs):
        return {"content": "fallback", "model": "local", "provider": "local", "tokens": 0}

    monkeypatch.setattr(llm_router, "chat_cloud", fake_chat_cloud)
    monkeypatch.setattr(llm_router, "chat_local", fake_chat_local)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    llm_router.settings.LLM_PROVIDER = "auto"
    # Re-read settings so uses_local picks up OLLAMA_BASE_URL
    import importlib
    importlib.reload(llm_router)

    result = await llm_router.chat([{"role": "user", "content": "hello"}])
    assert result["provider"] == "local"
    assert result["content"] == "fallback"
    assert result["content"] == "fallback"


@pytest.mark.asyncio
async def test_chat_respects_cloud_only_setting(monkeypatch):
    """An explicit cloud-only setting should bypass local fallback."""
    from core import llm_router

    async def fake_chat_cloud(*args, **kwargs):
        return {"content": "cloud", "model": "cloud-model", "provider": "cloud", "tokens": 7}

    async def fake_chat_local(*args, **kwargs):
        raise AssertionError("local backend should not be used")

    monkeypatch.setattr(llm_router, "chat_cloud", fake_chat_cloud)
    monkeypatch.setattr(llm_router, "chat_local", fake_chat_local)
    llm_router.settings.LLM_PROVIDER = "cloud"

    result = await llm_router.chat([{"role": "user", "content": "hello"}])
    assert result["provider"] == "cloud"
    assert result["content"] == "cloud"


def test_benchmark_files_exist():
    """All benchmark files exist and are importable."""
    from benchmarks import single_vs_multi, stress_test, fault_tolerance
    from benchmarks import memory_pressure, conflict_resolution, adversarial

    assert hasattr(single_vs_multi, "run")
    assert hasattr(stress_test, "run")
    assert hasattr(fault_tolerance, "run")
    assert hasattr(memory_pressure, "run")
    assert hasattr(conflict_resolution, "run")
    assert hasattr(adversarial, "run")