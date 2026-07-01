"""HIVE — Benchmark: Conflict Resolution"""
async def run() -> dict:
    """Two agents give different recommendations — test Judge resolution."""
    from core.llm_router import chat

    print("[Benchmark] Running Conflict Resolution test...")

    messages = [
        {"role": "system", "content": "You are HIVE's Judge. Two agents disagree on a decision. Resolve it and explain your reasoning."},
        {"role": "user", "content": "Agent A says: Use more GPU memory for faster inference. Agent B says: Reduce GPU memory to avoid OOM errors. Task: Run a large model on a 6GB GPU. What should we do?"},
    ]

    try:
        result = await chat(messages, quality_mode=True, max_tokens=300)
        resolution = result["content"]
        resolved = len(resolution) > 50  # Got a substantive response
    except Exception as e:
        resolution = str(e)
        resolved = False

    return {
        "benchmark": "conflict_resolution",
        "scenario": "GPU memory: Agent A (maximize perf) vs Agent B (avoid OOM)",
        "resolution_provided": resolved,
        "resolution": resolution[:300] if resolved else resolution,
        "passed": resolved,
        "interpretation": "Judge should recommend conservative VRAM (e.g., batch_size=1, FP16) for 6GB GPU.",
    }