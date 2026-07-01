"""
HIVE — GPU Tuner Agent
Real nvidia-smi integration for GPU monitoring and thermal management.
Reads: temperature, utilization %, VRAM, clock speeds.
Detects thermal throttling (>80C) and auto-cools.
"""

import subprocess
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _run_nvidia_smi(args: str) -> Optional[str]:
    """Run nvidia-smi and return output, or None if no GPU."""
    try:
        result = subprocess.run(
            ["nvidia-smi"] + args.split(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_gpu_status() -> dict:
    """Get current GPU status via nvidia-smi."""
    output = _run_nvidia_smi("--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits")
    if not output:
        return {
            "available": False,
            "error": "No NVIDIA GPU found or nvidia-smi not available",
        }

    try:
        name, temp, util, vram_used, vram_total, clock_sm, clock_mem = [
            x.strip() for x in output.strip().split(",")
        ]
        temp = int(temp)
        util = int(util)
        vram_used = int(vram_used)
        vram_total = int(vram_total)
        clock_sm = int(clock_sm)
        clock_mem = int(clock_mem)
    except Exception as e:
        return {"available": False, "error": f"Parse error: {e}", "raw": output}

    # Check thermal throttling
    throttle_output = _run_nvidia_smi("--query-gpu=clocks_throttle_reasons.hw_slowdown --format=csv,noheader")
    is_throttling = throttle_output and "N/A" not in throttle_output and throttle_output.strip() != "Not Active"

    return {
        "available": True,
        "name": name,
        "temperature_c": temp,
        "utilization_pct": util,
        "vram_used_mb": vram_used,
        "vram_total_mb": vram_total,
        "vram_pct": round(vram_used / vram_total * 100, 1),
        "clock_sm_mhz": clock_sm,
        "clock_mem_mhz": clock_mem,
        "is_throttling": is_throttling,
        "thermal_pressure": "high" if temp > 80 else ("medium" if temp > 70 else "normal"),
    }


async def run(task: str) -> dict:
    """Handle GPU tuning request."""
    from core.llm_router import chat, QWEN_TURBO

    status = get_gpu_status()

    if not status.get("available", False):
        return {
            "status": "ok",
            "gpu_available": False,
            "message": "No NVIDIA GPU detected",
            "suggestion": "This machine may not have an NVIDIA GPU, or nvidia-smi is not in PATH",
        }

    before_temp = status["temperature_c"]
    suggestions = []

    # Thermal management
    if before_temp > 80:
        suggestions.append("Temperature CRITICAL - apply cooling immediately")
        # Try to reduce power limit to cool down
        result = _run_nvidia_smi("-pl 150")  # Reduce power limit to 150W
        if result:
            suggestions.append("Power limit reduced to 150W to reduce heat")
        # Try to limit clock speeds
        result2 = _run_nvidia_smi("-lgc 300,900")  # Cap clocks
        if result2:
            suggestions.append("GPU clocks limited to reduce thermal output")

    elif before_temp > 70:
        suggestions.append("Temperature elevated - monitor closely")

    if status.get("is_throttling"):
        suggestions.append("HW throttling detected - GPU is thermally constrained")

    # Memory pressure
    if status.get("vram_pct", 0) > 90:
        suggestions.append("VRAM >90% full - reduce concurrent agents")

    # Get LLM analysis
    analysis_result = await chat(
        [
            {"role": "system", "content": "You are a GPU performance engineer. Analyze GPU metrics and provide optimization recommendations."},
            {"role": "user", "content": f"GPU Status:\n{status}\n\nTask: {task}\n\nProvide 3-5 specific actionable recommendations to optimize GPU performance and cooling."},
        ],
        model=QWEN_TURBO,
        max_tokens=512,
    )

    # Check after if we made changes
    after_status = get_gpu_status() if suggestions else status
    after_temp = after_status.get("temperature_c", before_temp)

    return {
        "status": "ok",
        "gpu_available": True,
        "before": {
            "temperature_c": before_temp,
            "utilization_pct": status["utilization_pct"],
            "vram_pct": status["vram_pct"],
            "is_throttling": status.get("is_throttling", False),
        },
        "after": {
            "temperature_c": after_temp,
            "utilization_pct": after_status["utilization_pct"],
        },
        "temperature_delta_c": after_temp - before_temp,
        "thermal_pressure": status["thermal_pressure"],
        "suggestions": suggestions,
        "llm_analysis": analysis_result["content"],
        "gpu_name": status["name"],
    }