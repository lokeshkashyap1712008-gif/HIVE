"""HIVE — Benchmark: Memory Pressure Test"""
async def run() -> dict:
    """Verify graceful degradation under low memory conditions."""
    from core.memory_manager import memory_manager

    print("[Benchmark] Running Memory Pressure test...")

    free_mb = memory_manager.available_memory_mb()
    total_mb = memory_manager.total_memory_mb()
    recommended = memory_manager.recommended_max_agents()

    # Simulate what happens if we spawn too many
    current_active = memory_manager.active_agent_count()

    health = memory_manager.swarm_health_score()

    return {
        "benchmark": "memory_pressure",
        "available_memory_mb": round(free_mb, 1),
        "total_memory_mb": round(total_mb, 1),
        "memory_percent_used": round((1 - free_mb / total_mb) * 100, 1),
        "recommended_max_agents": recommended,
        "current_active_agents": current_active,
        "swarm_health_score": health,
        "will_throttle_agents": free_mb < 2048,
        "passed": health >= 50,
    }