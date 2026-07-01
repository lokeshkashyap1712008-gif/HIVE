"""
HIVE — GPU Tuner Worker
Monitors and optimizes GPU usage, thermal management, nvidia-smi, VRAM allocation
"""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


class GPUTuner:
    """Monitors GPU, optimizes VRAM, manages thermal throttling."""

    async def run(description: str, context: dict = None) -> dict:
        description = description.lower()
        context = context or {}

        try:
            if not _gpu_available():
                return {"status": "no_gpu", "message": "No NVIDIA GPU detected. Run 'nvidia-smi' to verify."}

            if any(word in description for word in ["thermal", "temperature", "temp", "hot", "throttle"]):
                return await _check_thermal()
            elif any(word in description for word in ["vram", "memory", "gpu memory", "oom"]):
                return await _check_vram()
            elif any(word in description for word in ["optimize", "tune", "boost", "overclock"]):
                return await _optimize_gpu(description)
            elif any(word in description for word in ["process", "running", "utilization", "usage"]):
                return await _check_utilization()
            else:
                return await _full_diagnostic()

        except Exception as e:
            logger.error(f"[GPUTuner] Error: {e}")
            return {"status": "error", "error": str(e)}


def _gpu_available() -> bool:
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


async def _check_thermal() -> dict:
    """Check GPU temperatures and thermal status."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,temperature.gpu,power.draw,clocks.current.sm",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )

        lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpu = {
                    "index": parts[0],
                    "temperature_c": float(parts[1]),
                    "power_watts": float(parts[2]),
                    "clock_mhz": float(parts[3]),
                }
                # Thermal assessment
                if gpu["temperature_c"] >= 85:
                    gpu["thermal_status"] = "CRITICAL — throttling likely"
                    gpu["recommendation"] = "Improve airflow, reduce power limit, undervolt"
                elif gpu["temperature_c"] >= 75:
                    gpu["thermal_status"] = "HIGH — monitoring recommended"
                    gpu["recommendation"] = "Consider additional cooling"
                else:
                    gpu["thermal_status"] = "NORMAL"
                    gpu["recommendation"] = "No action needed"

                gpus.append(gpu)

        return {
            "status": "checked",
            "gpus": gpus,
            "overall": "THERMAL_THROTTLE_RISK" if any(g["temperature_c"] >= 85 for g in gpus) else "OK",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_vram() -> dict:
    """Check VRAM usage and availability."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )

        lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                used = float(parts[1])
                total = float(parts[2])
                free = float(parts[3])
                percent = (used / total * 100) if total > 0 else 0

                gpu = {
                    "index": parts[0],
                    "vram_used_mb": used,
                    "vram_total_mb": total,
                    "vram_free_mb": free,
                    "usage_percent": round(percent, 1),
                }

                if percent >= 95:
                    gpu["status"] = "CRITICAL — OOM risk"
                    gpu["recommendation"] = "Reduce batch size, clear cache, restart processes"
                elif percent >= 80:
                    gpu["status"] = "HIGH — consider optimization"
                    gpu["recommendation"] = "Monitor for OOM, optimize memory usage"
                else:
                    gpu["status"] = "OK"
                    gpu["recommendation"] = "Memory available for more agents"

                gpus.append(gpu)

        return {
            "status": "checked",
            "gpus": gpus,
            "total_vram_mb": sum(g["vram_total_mb"] for g in gpus),
            "free_vram_mb": sum(g["vram_free_mb"] for g in gpus),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_utilization() -> dict:
    """Check GPU utilization and running processes."""
    try:
        # Utilization
        util_output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu,utilization.memory",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )

        # Running processes
        proc_output = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid,name,used_memory",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )

        processes = []
        for line in proc_output.strip().split("\n"):
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    processes.append({
                        "pid": parts[0],
                        "name": parts[1],
                        "vram_mb": float(parts[2]) if parts[2].strip() else 0,
                    })

        lines = [l.strip() for l in util_output.strip().split("\n") if l.strip()]
        gpus = []
        for i, line in enumerate(lines):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "index": parts[0],
                    "gpu_util_percent": float(parts[1]),
                    "mem_util_percent": float(parts[2]),
                    "running_processes": len([p for p in processes if True]),  # all show all for simplicity
                })

        return {
            "status": "checked",
            "gpus": gpus,
            "processes": processes,
            "total_processes": len(processes),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _optimize_gpu(description: str) -> dict:
    """Provide GPU optimization recommendations."""
    diagnostics = await _check_vram()
    thermal = await _check_thermal()

    recommendations = []

    # Memory-based recommendations
    for gpu in diagnostics.get("gpus", []):
        if gpu.get("usage_percent", 0) >= 80:
            recommendations.extend([
                f"GPU {gpu['index']}: Reduce VRAM usage (currently {gpu['usage_percent']}%)",
                "Use mixed precision (FP16) for inference",
                "Enable gradient checkpointing for training",
                "Set PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512",
            ])

    # Thermal-based recommendations
    for gpu in thermal.get("gpus", []):
        if gpu.get("temperature_c", 0) >= 75:
            recommendations.extend([
                f"GPU {gpu['index']}: Thermal issue detected ({gpu['temperature_c']}°C)",
                "Set nvidia-smi --power-limit to reduce TDP",
                "Consider undervolting (-50mV to start)",
                "Increase fan speed: nvidia-settings -a [fan]/fan_speed=70",
            ])

    if not recommendations:
        recommendations = [
            "GPU is running optimally",
            "Current settings are appropriate for current workload",
            "No immediate action required",
        ]

    return {
        "status": "optimized",
        "recommendations": recommendations,
        "current_vram": diagnostics.get("gpus", [{}])[0].get("vram_used_mb", "N/A"),
        "current_temp": thermal.get("gpus", [{}])[0].get("temperature_c", "N/A"),
    }


async def _full_diagnostic() -> dict:
    """Run a complete GPU diagnostic."""
    vram = await _check_vram()
    thermal = await _check_thermal()
    util = await _check_utilization()

    return {
        "status": "diagnostic_complete",
        "vram": vram,
        "thermal": thermal,
        "utilization": util,
        "recommendation": "Run with specific optimization goal for targeted advice",
    }


async def run(description: str, context: dict = None) -> dict:
    return await GPUTuner.run(description, context)