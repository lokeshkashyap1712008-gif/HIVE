"""
HIVE — Audit Logger
Append-only log of all Leader decisions
"""

import sqlite3
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".hive" / "hive.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

try:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                datetime TEXT,
                decision_type TEXT,
                reason TEXT,
                agents_affected TEXT,
                metadata TEXT
            )
        """)
except Exception as e:
    logger.warning(f"Could not create audit table: {e}")


class AuditLogger:
    def __init__(self):
        pass

    def log(self, decision_type: str, reason: str,
            agents_affected: Optional[list] = None, metadata: Optional[dict] = None):
        now = time.time()
        dt = datetime.fromtimestamp(now).isoformat()
        agents_json = json.dumps(agents_affected or [])
        meta_json = json.dumps(metadata or {})

        try:
            conn = sqlite3.connect(DB_PATH, isolation_level=None)
            conn.execute(
                "INSERT INTO audit_log (timestamp, datetime, decision_type, reason, agents_affected, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (now, dt, decision_type, reason, agents_json, meta_json),
            )
            conn.close()
            logger.debug(f"[AuditLog] {decision_type}: {reason}")
        except Exception as e:
            logger.error(f"[AuditLog] Failed to write: {e}")

    def get_entries(self, limit: int = 50, offset: int = 0,
                    decision_type: Optional[str] = None) -> list:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            query = "SELECT * FROM audit_log"
            params = []
            if decision_type:
                query += " WHERE decision_type = ?"
                params.append(decision_type)
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(query, params)
            rows = cur.fetchall()
            conn.close()

            return [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "datetime": r["datetime"],
                    "decision_type": r["decision_type"],
                    "reason": r["reason"],
                    "agents_affected": json.loads(r["agents_affected"]),
                    "metadata": json.loads(r["metadata"]),
                }
                for r in rows
            ]
        except Exception:
            return []

    def total(self) -> int:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM audit_log")
            count = cur.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0


audit_logger = AuditLogger()
