"""Minimal HTTP proof-of-deployment server for Alibaba Cloud SAS/ECS.

Exposes /health and /info so Workbench / public IP screenshots show HIVE
running on Alibaba compute while all LLM calls go to Qwen Cloud (DashScope).
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hive.config import DASHSCOPE_API_KEY, QWEN_BASE_URL, QWEN_MODEL

HOST = os.environ.get("HIVE_DEPLOY_HOST", "0.0.0.0")
PORT = int(os.environ.get("HIVE_DEPLOY_PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[hive-deploy] {self.address_string()} - {fmt % args}")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            key_ok = bool(DASHSCOPE_API_KEY) and not DASHSCOPE_API_KEY.startswith(
                "your_"
            )
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "HIVE Agent OS",
                    "track": "Agent Society",
                    "cloud": "Alibaba Cloud (SAS/ECS)",
                    "llm": {
                        "provider": "Qwen Cloud / DashScope",
                        "base_url": QWEN_BASE_URL,
                        "model": QWEN_MODEL,
                        "api_key_configured": key_ok,
                    },
                    "proof_code": "https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/llm.py",
                },
            )
            return

        if self.path == "/info":
            self._json(
                200,
                {
                    "name": "hive-os",
                    "description": "AI agents form temporary societies powered by Qwen Cloud",
                    "entrypoint_cli": "python -m hive",
                    "alibaba_api": QWEN_BASE_URL,
                },
            )
            return

        self._json(404, {"error": "not found", "paths": ["/", "/health", "/info"]})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"HIVE deploy server listening on http://{HOST}:{PORT}")
    print(f"Qwen Cloud base_url={QWEN_BASE_URL} model={QWEN_MODEL}")
    print("Proof endpoints: GET /health  GET /info")
    server.serve_forever()


if __name__ == "__main__":
    main()
