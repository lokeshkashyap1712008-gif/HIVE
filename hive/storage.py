"""SQLite storage — connection, schema, CRUD operations."""

import aiosqlite
from pathlib import Path
from hive.config import HIVE_DB, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    model TEXT,
    started_at REAL DEFAULT (unixepoch('subsec')),
    ended_at REAL,
    summary TEXT DEFAULT '',
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL DEFAULT (unixepoch('subsec'))
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    duration_ms INTEGER,
    success INTEGER DEFAULT 1,
    created_at REAL DEFAULT (unixepoch('subsec'))
);

CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    code_path TEXT NOT NULL,
    description TEXT,
    risk_tier TEXT DEFAULT 'moderate',
    created_at REAL DEFAULT (unixepoch('subsec')),
    last_used_at REAL,
    use_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT,
    confidence REAL DEFAULT 0.0,
    source_session_id TEXT,
    created_at REAL DEFAULT (unixepoch('subsec')),
    last_used_at REAL,
    use_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    action TEXT NOT NULL,
    details_json TEXT,
    risk_tier TEXT,
    created_at REAL DEFAULT (unixepoch('subsec'))
);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (unixepoch('subsec'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit(action);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    role,
    content=messages,
    content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, role)
    VALUES (new.id, new.content, new.role);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, role)
    VALUES('delete', old.id, old.content, old.role);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, role)
    VALUES('delete', old.id, old.content, old.role);
    INSERT INTO messages_fts(rowid, content, role)
    VALUES (new.id, new.content, new.role);
END;
"""


async def get_db() -> aiosqlite.Connection:
    """Get database connection with WAL mode and optimized settings."""
    ensure_dirs()
    db = await aiosqlite.connect(str(HIVE_DB))
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA busy_timeout = 5000")
    await db.execute("PRAGMA cache_size = -64000")
    await db.execute("PRAGMA temp_store = MEMORY")
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize database schema."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        try:
            await db.executescript(FTS_SCHEMA)
            await db.executescript(FTS_TRIGGERS)
        except Exception:
            pass  # FTS already exists
        await db.commit()
    finally:
        await db.close()


# --- Sessions ---

async def create_session(db, session_id: str, model: str) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, model) VALUES (?, ?)",
        (session_id, model),
    )
    await db.commit()


async def end_session(db, session_id: str) -> None:
    import time
    await db.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (time.time(), session_id),
    )
    await db.commit()


async def get_session(db, session_id: str):
    cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return await cursor.fetchone()


async def list_sessions(db, limit: int = 20):
    cursor = await db.execute(
        "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )
    return await cursor.fetchall()


# --- Messages ---

async def add_message(db, session_id: str, role: str, content: str) -> int:
    cursor = await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    await db.commit()
    return cursor.lastrowid


async def get_messages(db, session_id: str, limit: int = 50):
    cursor = await db.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    )
    rows = await cursor.fetchall()
    return list(reversed(rows))


# --- Tool Calls ---

async def log_tool_call(db, session_id: str, message_id: int,
                        tool_name: str, input_json: str, output_json: str,
                        duration_ms: int, success: bool = True) -> None:
    await db.execute(
        """INSERT INTO tool_calls
           (session_id, message_id, tool_name, input_json, output_json, duration_ms, success)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, message_id, tool_name, input_json, output_json,
         duration_ms, 1 if success else 0),
    )
    await db.commit()


# --- Audit ---

async def audit_log(db, session_id: str, action: str,
                    details_json: str = "", risk_tier: str = "") -> None:
    await db.execute(
        "INSERT INTO audit (session_id, action, details_json, risk_tier) VALUES (?, ?, ?, ?)",
        (session_id, action, details_json, risk_tier),
    )
    await db.commit()


# --- Agents ---

async def register_agent(db, name: str, code_path: str,
                         description: str = "", risk_tier: str = "moderate") -> None:
    await db.execute(
        """INSERT OR REPLACE INTO agents (name, code_path, description, risk_tier)
           VALUES (?, ?, ?, ?)""",
        (name, code_path, description, risk_tier),
    )
    await db.commit()


async def get_agent(db, name: str):
    cursor = await db.execute("SELECT * FROM agents WHERE name = ?", (name,))
    return await cursor.fetchone()


async def list_agents(db):
    cursor = await db.execute("SELECT * FROM agents ORDER BY use_count DESC")
    return await cursor.fetchall()


# --- Skills ---

async def add_skill(db, name: str, description: str, confidence: float = 0.0,
                    source_session_id: str = "") -> None:
    await db.execute(
        """INSERT OR REPLACE INTO skills (name, description, confidence, source_session_id)
           VALUES (?, ?, ?, ?)""",
        (name, description, confidence, source_session_id),
    )
    await db.commit()


async def list_skills(db):
    cursor = await db.execute("SELECT * FROM skills ORDER BY confidence DESC")
    return await cursor.fetchall()


# --- Search ---

async def search_messages(db, query: str, limit: int = 10):
    cursor = await db.execute(
        """SELECT m.*, snippet(messages_fts, 0, '>>>', '<<<', '...', 20) as snippet
           FROM messages_fts
           JOIN messages m ON messages_fts.rowid = m.id
           WHERE messages_fts MATCH ?
           ORDER BY rank LIMIT ?""",
        (query, limit),
    )
    return await cursor.fetchall()
