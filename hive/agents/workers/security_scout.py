"""
HIVE — Security Scout Agent
OWASP Top 10 vulnerability scanning, CVE detection, security assessment.
"""

import re
import socket
import asyncio
import logging
from typing import Optional

import httpx

from hive.core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)


async def _check_sql_injection(url: str) -> dict:
    test_payloads = ["' OR 1=1--", "'; DROP TABLE users--", "' OR 'a'='a"]
    vulnerable = False
    details = []

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for payload in test_payloads:
            try:
                for param in ["id", "user", "q", "search", "query"]:
                    test_url = f"{url}?{param}={payload}"
                    resp = await client.get(test_url, timeout=5.0)
                    text = resp.text.lower()
                    if any(err in text for err in ["sql", "syntax error", "mysql", "postgresql", "ora-", "sqlite"]):
                        vulnerable = True
                        details.append(f"SQL injection possible via param '{param}' with payload: {payload}")
                        break
            except Exception:
                pass

    return {"test": "sql_injection", "vulnerable": vulnerable, "details": details, "severity": "critical" if vulnerable else "info"}


async def _check_xss(url: str) -> dict:
    payloads = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "javascript:alert(1)"]
    vulnerable = False
    details = []

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for payload in payloads:
            try:
                for param in ["q", "search", "name", "input"]:
                    test_url = f"{url}?{param}={payload}"
                    resp = await client.get(test_url, timeout=5.0)
                    if payload in resp.text:
                        vulnerable = True
                        details.append(f"XSS via param '{param}' with payload: {payload}")
                        break
            except Exception:
                pass

    return {"test": "xss", "vulnerable": vulnerable, "details": details, "severity": "high" if vulnerable else "info"}


def _check_open_ports(host: str, ports: Optional[list[int]] = None) -> dict:
    if ports is None:
        ports = [21, 22, 23, 25, 80, 443, 445, 1433, 3306, 5432, 6379, 27017]

    open_ports = []
    try:
        for port in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                open_ports.append(port)
    except Exception:
        pass

    service_names = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 80: "HTTP", 443: "HTTPS",
                     445: "SMB", 1433: "MSSQL", 3306: "MySQL", 5432: "PostgreSQL",
                     6379: "Redis", 27017: "MongoDB"}
    risky = [p for p in open_ports if p in [21, 23, 25, 445, 3306, 5432, 6379, 27017, 1433]]

    return {
        "test": "open_ports",
        "open_ports": [{port: service_names.get(port, "unknown")} for port in open_ports],
        "risky_services": risky,
        "severity": "medium" if risky else "low",
    }


async def _check_headers(url: str) -> dict:
    missing_headers = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=5.0)
            headers = {k.lower(): v for k, v in resp.headers.items()}

            security_headers = {
                "strict-transport-security": "HSTS",
                "content-security-policy": "CSP",
                "x-content-type-options": "X-Content-Type",
                "x-frame-options": "X-Frame-Options",
                "x-xss-protection": "X-XSS-Protection",
            }

            for header, name in security_headers.items():
                if header not in headers:
                    missing_headers.append(name)
        except Exception as e:
            return {"test": "security_headers", "error": str(e), "severity": "info"}

    return {
        "test": "security_headers",
        "missing_headers": missing_headers,
        "severity": "medium" if len(missing_headers) > 2 else "low",
    }


async def run(task: str) -> dict:
    url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', task)
    if not url_match:
        result = await chat(
            [{"role": "system", "content": "Extract any URL or hostname from the text. Reply with just the URL or hostname."},
             {"role": "user", "content": task}],
            model=QWEN_TURBO,
            max_tokens=128,
        )
        url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', result["content"])

    if not url_match:
        return {"status": "error", "message": "No URL or hostname found in task"}

    url = url_match.group(0).rstrip("/")
    host = url.split("://")[1].split("/")[0]

    sql_result, xss_result, port_result, header_result = await asyncio.gather(
        _check_sql_injection(url),
        _check_xss(url),
        asyncio.to_thread(_check_open_ports, host),
        _check_headers(url),
    )

    all_results = [sql_result, xss_result, port_result, header_result]

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings = [r for r in all_results if r.get("vulnerable") or r.get("missing_headers")]
    if findings:
        max_severity = min(findings, key=lambda x: severity_order.get(x.get("severity", "info"), 4))
        overall = max_severity.get("severity", "low")
    else:
        overall = "info"

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in all_results:
        sev = r.get("severity", "info")
        if sev in severity_counts:
            severity_counts[sev] += 1

    summary_result = await chat(
        [{"role": "system", "content": "You are a security analyst. Summarize the security scan results concisely."},
         {"role": "user", "content": f"URL: {url}\nResults: {all_results}\n\nGive a brief executive summary and top 3 prioritized recommendations."}],
        model=QWEN_TURBO,
        max_tokens=512,
    )

    return {
        "status": "ok",
        "url": url,
        "overall_severity": overall,
        "severity_counts": severity_counts,
        "vulnerabilities": all_results,
        "scan_summary": summary_result["content"],
        "compliance": {
            "owasp_top_10_covered": ["A01", "A05", "A07"],
            "missing_security_headers": header_result.get("missing_headers", []),
        },
    }
