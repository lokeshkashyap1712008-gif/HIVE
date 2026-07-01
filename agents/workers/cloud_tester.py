"""
HIVE — Cloud Tester Worker
Tests cloud services: Alibaba Cloud ECS/FC, Docker containers, health checks, API endpoints
"""

import asyncio
import logging
import httpx
import time

logger = logging.getLogger(__name__)


class CloudTester:
    """Tests cloud infrastructure, containers, and service health."""

    async def run(description: str, context: dict = None) -> dict:
        description = description.lower()
        context = context or {}

        try:
            if any(word in description for word in ["docker", "container", "image", "dockerfile"]):
                return await _test_docker(description)
            elif any(word in description for word in ["ecs", "alibaba", "aliyun", "fc", "function compute"]):
                return await _test_alibaba(description)
            elif any(word in description for word in ["health", "ping", "uptime", "endpoint"]):
                return await _test_endpoint(description)
            elif any(word in description for word in ["deploy", "deployment"]):
                return await _simulate_deploy(description)
            else:
                return await _test_endpoint(description)

        except Exception as e:
            logger.error(f"[CloudTester] Error: {e}")
            return {"status": "error", "error": str(e)}


async def _test_endpoint(description: str) -> dict:
    """Test an HTTP endpoint for health and response time."""
    import re
    url_match = re.search(r"https?://[^\s]+", description)
    url = url_match.group(0).rstrip(".,;") if url_match else None

    if not url:
        return {"status": "error", "error": "No URL found in task description"}

    results = {"url": url, "checks": []}

    # Run checks
    async with httpx.AsyncClient(timeout=15.0) as client:
        # HTTP check
        start = time.time()
        try:
            resp = await client.get(url)
            elapsed = (time.time() - start) * 1000
            results["checks"].append({
                "test": "http_get",
                "status": resp.status_code,
                "response_time_ms": round(elapsed, 1),
                "passed": resp.status_code < 400,
            })
        except Exception as e:
            results["checks"].append({"test": "http_get", "error": str(e), "passed": False})

        # DNS check
        from urllib.parse import urlparse
        parsed = urlparse(url)
        try:
            import socket
            ip = socket.gethostbyname(parsed.netloc)
            results["checks"].append({"test": "dns_resolution", "ip": ip, "passed": True})
        except Exception as e:
            results["checks"].append({"test": "dns_resolution", "error": str(e), "passed": False})

        # Redirect check
        try:
            resp_head = await client.head(url)
            results["checks"].append({
                "test": "redirect_chain",
                "redirects": len(resp.history),
                "final_url": str(resp.url),
                "passed": True,
            })
        except Exception:
            pass

    # Overall status
    passed = all(c.get("passed", False) for c in results["checks"])
    results["overall"] = "PASS" if passed else "DEGRADED"
    results["passed_checks"] = len([c for c in results["checks"] if c.get("passed")])
    results["total_checks"] = len(results["checks"])

    return results


async def _test_docker(description: str) -> dict:
    """Test Docker containers, images, or Dockerfiles."""
    import subprocess

    results = {"tests": []}

    # Check Docker daemon
    try:
        version = subprocess.check_output(["docker", "--version"], text=True, timeout=5).strip()
        results["docker_version"] = version
    except Exception as e:
        return {"status": "error", "error": f"Docker not available: {e}"}

    # List containers
    try:
        containers = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}\\t{{.Status}}"], text=True, timeout=10)
        results["containers"] = [line.split("\t") for line in containers.strip().split("\n") if line]
    except Exception:
        results["containers"] = []

    # List images
    try:
        images = subprocess.check_output(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], text=True, timeout=10)
        results["images"] = [i for i in images.strip().split("\n") if i]
    except Exception:
        results["images"] = []

    # System info
    try:
        stats = subprocess.check_output(["docker", "system", "df"], text=True, timeout=10)
        results["disk_usage"] = stats
    except Exception:
        pass

    return {"status": "success", "docker": results}


async def _test_alibaba(description: str) -> dict:
    """Test Alibaba Cloud resources."""
    # This would use alibaba cloud SDK in production
    # For now, simulate checks
    checks = []

    if any(word in description for word in ["ecs", "server", "instance"]):
        checks.append({"service": "ECS", "status": "simulated", "tip": "Configure ALIBABA_ACCESS_KEY for real checks"})

    if any(word in description for word in ["fc", "function", "serverless"]):
        checks.append({"service": "Function Compute", "status": "simulated", "tip": "Configure ALIBABA_ACCESS_KEY for real checks"})

    if any(word in description for word in ["api gateway", "gateway"]):
        checks.append({"service": "API Gateway", "status": "simulated", "tip": "Configure ALIBABA_ACCESS_KEY for real checks"})

    return {
        "status": "checked",
        "configured": False,
        "checks": checks,
        "tip": "Install alibaba-cloud-python-sdk and set ALIBABA_ACCESS_KEY_ID / ALIBABA_ACCESS_KEY_SECRET",
    }


async def _simulate_deploy(description: str) -> dict:
    """Simulate a deployment and return expected results."""
    return {
        "status": "simulated",
        "deployment": {
            "target": "cloud",
            "estimated_duration_seconds": 120,
            "steps": ["Build image", "Push to registry", "Pull on server", "Restart containers", "Health check"],
            "tip": "Configure CI/CD credentials for automated deployment",
        },
    }


async def run(description: str, context: dict = None) -> dict:
    return await CloudTester.run(description, context)