"""
HIVE — Diagnostician Worker
Parses logs, analyzes errors, suggests fixes, diagnoses issues
"""

import asyncio
import re
import logging

logger = logging.getLogger(__name__)


class Diagnostician:
    """Analyzes errors, logs, and system state to diagnose problems."""

    async def run(description: str, context: dict = None) -> dict:
        description = description.lower()
        context = context or {}

        try:
            # Check for log file path
            log_match = re.search(r"[\w/\\.-]+\.(log|txt|json|err|out)", description)
            if log_match:
                return await _analyze_log_file(log_match.group(0), description)

            # Check for error message
            if any(word in description for word in ["error", "exception", "crash", "fail"]):
                return await _analyze_error(description)

            # Check for system diagnostics
            if any(word in description for word in ["system", "memory", "cpu", "disk", "performance"]):
                return await _system_diagnostics(description)

            return await _analyze_error(description)

        except Exception as e:
            logger.error(f"[Diagnostician] Error: {e}")
            return {"status": "error", "error": str(e)}


async def _analyze_error(description: str) -> dict:
    """Analyze an error message or description."""
    # Extract error type
    error_types = ["404", "403", "500", "401", "timeout", "connection refused",
                   "permission denied", "out of memory", "null pointer", "syntax error",
                   "import error", "module not found", "connection timeout"]
    found_errors = [e for e in error_types if e in description]

    return {
        "status": "diagnosed",
        "errors_found": found_errors,
        "analysis": f"Detected potential issues: {', '.join(found_errors) if found_errors else 'None specific'}",
        "recommendations": _get_recommendations(found_errors),
    }


async def _analyze_log_file(path: str, description: str) -> dict:
    """Read and analyze a log file."""
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read()[:5000]

        # Extract error lines
        error_lines = [line for line in content.split("\n") if "error" in line.lower() or "exception" in line.lower()]

        # Count by severity
        warnings = len([l for l in content.split("\n") if "warn" in l.lower()])
        errors = len(error_lines)
        critical = len([l for l in error_lines if any(x in l.lower() for x in ["fatal", "panic", "critical"])])

        return {
            "status": "analyzed",
            "file": path,
            "total_lines": len(content.split("\n")),
            "error_count": errors,
            "warning_count": warnings,
            "critical_count": critical,
            "sample_errors": error_lines[:5],
            "health_score": max(0, 100 - errors * 5 - critical * 15),
        }
    except FileNotFoundError:
        return {"status": "error", "error": f"Log file not found: {path}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _system_diagnostics(description: str) -> dict:
    """Run basic system diagnostics."""
    import psutil
    import platform

    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    issues = []
    if mem.percent > 85:
        issues.append("HIGH_MEMORY: Memory usage above 85%")
    if cpu > 90:
        issues.append("HIGH_CPU: CPU usage above 90%")
    if disk.percent > 90:
        issues.append("HIGH_DISK: Disk usage above 90%")

    return {
        "status": "diagnosed",
        "hostname": platform.node(),
        "platform": platform.platform(),
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_available_mb": round(mem.available / (1024**2), 1),
        "disk_percent": disk.percent,
        "issues_found": issues,
        "overall_health": "healthy" if not issues else "degraded" if len(issues) == 1 else "critical",
    }


def _get_recommendations(errors: list[str]) -> list[str]:
    recommendations = {
        "404": ["Check URL path is correct", "Verify resource exists on server", "Check routing configuration"],
        "500": ["Check server logs", "Verify backend service is running", "Check database connectivity"],
        "timeout": ["Increase timeout value", "Check network latency", "Optimize slow query"],
        "permission denied": ["Check file permissions", "Verify service account has access", "Check ACL rules"],
        "out of memory": ["Add more RAM", "Optimize memory usage", "Check for memory leaks"],
        "module not found": ["Install missing dependency", "Check PYTHONPATH", "Verify virtual environment"],
    }
    result = []
    for err in errors:
        for key, recs in recommendations.items():
            if key in err:
                result.extend(recs)
    return list(dict.fromkeys(result))[:5]


async def run(description: str, context: dict = None) -> dict:
    return await Diagnostician.run(description, context)