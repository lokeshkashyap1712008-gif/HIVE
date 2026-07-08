"""
Site playbooks — remember how a site/login/checkout works after success.

This is intentionally lightweight:
- store only URLs, session names, and trust score
- never store passwords, cookies, or card numbers
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from hive.config import HIVE_HOME, ensure_dirs

logger = logging.getLogger(__name__)

PLAYBOOK_DIR = HIVE_HOME / "playbooks"
SCHEMA_VERSION = 1


def _site_key(domain_or_url: str) -> str:
    d = (domain_or_url or "").strip().lower()
    # If a URL was given, extract host-like part.
    d = re.sub(r"^https?://", "", d)
    d = d.split("/", 1)[0]
    d = d.replace("www.", "")
    # Keep it filename-safe.
    d = re.sub(r"[^a-z0-9._-]+", "_", d)
    return d or "unknown"


# Public helper (used by agents)
def site_key(domain_or_url: str) -> str:
    return _site_key(domain_or_url)


def _ensure() -> None:
    ensure_dirs()
    PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)


def _playbook_path(site_key: str) -> Path:
    return PLAYBOOK_DIR / f"{site_key}.json"


def load_playbook(site_key: str) -> dict[str, Any]:
    """Load playbook JSON for a site. Returns default structure if missing."""
    _ensure()
    path = _playbook_path(site_key)
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "site": site_key,
            "trust_score": 0,
            "sessions": {},
            "login": {},
            "signup": {},
            "checkout": {},
            "updated_at": time.time(),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid playbook format")
        return data
    except Exception as e:
        logger.warning("Failed to load playbook %s: %s", path, e)
        return {
            "schema_version": SCHEMA_VERSION,
            "site": site_key,
            "trust_score": 0,
            "sessions": {},
            "login": {},
            "signup": {},
            "checkout": {},
            "updated_at": time.time(),
        }


def save_playbook(site_key: str, data: dict[str, Any]) -> None:
    _ensure()
    path = _playbook_path(site_key)
    tmp = path.with_suffix(".json.tmp")
    data = dict(data)
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("site", site_key)
    data["updated_at"] = time.time()
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def record_success(
    site_key: str,
    *,
    flow: str,
    session_name: Optional[str] = None,
    last_url: Optional[str] = None,
    note: Optional[str] = None,
    trust_delta: int = 8,
) -> dict[str, Any]:
    """Update playbook after a successful browser workflow."""
    pb = load_playbook(site_key)

    pb["trust_score"] = int(pb.get("trust_score", 0)) + int(trust_delta)
    pb["trust_score"] = max(0, min(100, pb["trust_score"]))

    flow_key = flow.lower().strip()
    if flow_key not in ("login", "signup", "checkout"):
        flow_key = "login"

    flow_obj = pb.get(flow_key) or {}
    flow_obj = dict(flow_obj)
    flow_obj["last_success_at"] = time.time()
    if session_name:
        flow_obj["session_name"] = session_name
        pb.setdefault("sessions", {})[session_name] = {"flow": flow_key, "saved_at": time.time()}
    if last_url:
        flow_obj["last_url"] = last_url
    if note:
        flow_obj["note"] = note[:400]

    pb[flow_key] = flow_obj
    save_playbook(site_key, pb)
    return pb


def record_failure(site_key: str, *, flow: str, trust_delta: int = -10) -> dict[str, Any]:
    """Update trust score after a failed browser workflow."""
    pb = load_playbook(site_key)
    pb["trust_score"] = int(pb.get("trust_score", 0)) + int(trust_delta)
    pb["trust_score"] = max(0, min(100, pb["trust_score"]))

    flow_key = flow.lower().strip()
    if flow_key not in ("login", "signup", "checkout"):
        flow_key = "login"
    pb.setdefault(flow_key, {})
    pb[flow_key]["last_failure_at"] = time.time()
    save_playbook(site_key, pb)
    return pb

