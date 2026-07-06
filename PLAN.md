# HIVE OS — Complete Implementation Plan

> Single source of truth. Every decision, every file, every detail.

---

## Swarm & Agent Collaboration Overhaul (Phase 1-5 Complete)

### Phase 1: Critical Bug Fixes (DONE)

| # | Bug | File | Fix |
|---|---|---|---|
| 1 | `MessageBus.publish()` missing | `core/message_bus.py` | Added `publish()` method |
| 2 | `quality_mode` wrong kwarg | `agents/safety_agent.py:106`, `agents/workers/report_agent.py:103` | Changed to `quality` |
| 3 | Dual MessageBus singletons | `core/message_bus.py:134` | Removed duplicate `message_bus` instance |
| 4 | Debate rounds 1-3 data lost | `agents/debate_protocol.py:189-194` | Fixed to pass actual r1, r2, r3 dicts |
| 5 | CreatorAgent not registering | `creator.py:57-68` | Added `register_agent()` call |
| 6 | Worker methods missing `self` | 6 worker files | Added `@staticmethod` decorators |
| 7 | Desktop Controller Windows-only | `agents/workers/desktop_controller.py` | Added `IS_WINDOWS`/`IS_MACOS` platform detection |

### Phase 2: Unified Architecture (DONE)

- **Merged CLI Leader + Swarm Leader** — Single `Leader` class in `hive/leader.py`
- **Smart LLM routing** — Uses LLM to decide single-agent vs swarm mode
- **`/swarm` command** — Force swarm mode for next task
- **`/status` command** — Show bus messages, registered agents, budget

### Phase 3: Agent Collaboration (DONE)

- **Parallel worker execution** — Workers in same group run via `asyncio.gather()`
- **MessageBus integration** — Leader sends TASK messages, workers send RESPONSE messages
- **Debate protocol integration** — High-stakes tasks trigger 4-round debate before execution
- **Agent state tracking** — Workers update emotional state on task start/completion

### Phase 4: CLI Production Ready (DONE)

- **Retry logic** — CLI retries failed requests up to 2 times
- **Better token estimation** — Improved `estimate_tokens()` in memory.py
- **Context window fix** — Always keeps last 4 messages for continuity
- **Max loop iterations** — Runtime capped at 20 iterations to prevent hangs

### Phase 5: Gap Closure (DONE)

- **Judge integration** — High-stakes swarm tasks go through debate protocol
- **Cross-platform desktop** — macOS support for open/close/list windows
- **Platform detection** — `IS_WINDOWS`/`IS_MACOS` flags in desktop controller

---

## Comparison with Successful AI OS

| Feature | OpenHands | CrewAI | AutoGen | HIVE OS (After) |
|---|---|---|---|---|
| Event-driven | Yes | No | Yes | Partial (MessageBus) |
| Supervisor pattern | Yes | Yes | Yes | Yes (LLM routing) |
| Parallel execution | Yes | Yes | Yes | Yes (asyncio.gather) |
| Agent handoff | Yes | Yes | Yes | Yes (MessageBus) |
| State management | Event stream | Task context | Typed events | AgentState + MessageBus |
| Token budgeting | Yes | Yes | Yes | Yes (Economy) |
| Debate/verification | No | No | No | Yes (4-round debate) |
| Judge/guardrails | No | No | No | Yes (Judge + Safety) |
| Error recovery | Retry | Retry | Retry | Yes (CLI retry) |
| Streaming | Yes | No | Yes | Partial (buffered) |
| Observability | Full UI | Verbose | Event log | /status + /agents |

---

## Architecture After Overhaul

```
User Terminal
    │
    ▼
CLI Layer (cli.py)
    │  /status, /swarm, /agents, /skills
    ▼
Unified Leader (leader.py)
    │  LLM routing: single vs swarm
    ├── Single Agent Path ──────────────────┐
    │   AgentRuntime.run_loop()             │
    │   Tools ↔ LLM ↔ Permission           │
    │                                       │
    └── Swarm Path ────────────────────────┐│
        agents/leader.py                   ││
        Task Decomposition (LLM)           ││
        ├── Group A: [worker1, worker2] ───┤│  asyncio.gather()
        ├── Group B: [worker3] ────────────┤│
        │                                   ││
        High-stakes? ──► Debate Protocol ──┤│
        │                  4 rounds         ││
        │                  Judge verdict    ││
        │                                   ││
        Result Synthesis (LLM) ────────────┘│
        │                                   │
        MessageBus ◄── all agents ──────────┘
        Economy (credit tracking)
        AgentState (emotions, reputation)
        AuditLogger (decision log)
```

## 1. What This Is

HIVE OS is a **CLI-based AI operating system**. Cloud brain (Qwen DashScope API) + local execution (your PC).

- Not a web app
- Not a dashboard
- Not a TUI with panels and widgets
- A **clean CLI tool** like Claude Code / OpenCode

You type a message. HIVE responds. Tools run. Files get edited. That's it.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER TERMINAL                         │
│                    > user input                          │
│                    ● agent output                        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    CLI LAYER                             │
│              hive/cli.py + hive/main.py                  │
│         input handling, output formatting, slash cmds    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    LEADER                                │
│                  hive/leader.py                          │
│        task decomposition, agent spawning, coord        │
└───────┬──────────────┼──────────────┬───────────────────┘
        │              │              │
┌───────▼───┐  ┌───────▼───┐  ┌───────▼───┐
│  AGENT 1  │  │  AGENT 2  │  │  AGENT 3  │  ... (max 4)
│ (process) │  │ (process) │  │ (process) │
│  Creator  │  │  Worker   │  │  Worker   │
└───────┬───┘  └───────┬───┘  └───────┬───┘
        │              │              │
┌───────▼──────────────▼──────────────▼───────────────────┐
│                 TOOL EXECUTION                           │
│              hive/tools.py (async, main process)        │
│     file ops, shell commands, git, web requests         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 STORAGE                                  │
│         hive/storage.py (SQLite + files)                 │
│    ~/.hive/hive.db + ~/.hive/agents/generated/          │
└─────────────────────────────────────────────────────────┘
```

### Process Model

| Component | Runs In | Why |
|---|---|---|
| CLI (input/output) | Main process | Simple, single user |
| Leader reasoning | Main process, asyncio | Calls Qwen API (I/O bound) |
| Agent execution | Separate process | Bypass GIL, true parallelism |
| Tool execution | Main process, asyncio | Fast, no need for separate process |
| File I/O | Main process, asyncio | aiofiles for non-blocking |
| Web requests | Main process, asyncio | httpx async client |
| Shell commands | Main process, subprocess | Run in background, poll status |

---

## 3. Storage — SQLite

### Why SQLite

Every successful CLI tool uses it (Claude Code, OpenCode, Hermes). Fast queries, FTS5 search, battle-tested, single file.

### Location

```
~/.hive/
├── hive.db                  ← SQLite database (WAL mode)
├── hive.db-wal              ← Write-ahead log (auto)
├── hive.db-shm              ← Shared memory (auto)
├── agents/
│   └── generated/           ← Generated agent code (.py files)
└── skills/
    └── {name}/
        └── SKILL.md         ← Human-readable skill docs
```

### Connection Setup

```python
import aiosqlite

async def get_db():
    db = await aiosqlite.connect("~/.hive/hive.db")
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA busy_timeout = 5000")
    await db.execute("PRAGMA cache_size = -64000")  # 64MB
    await db.execute("PRAGMA temp_store = MEMORY")
    db.row_factory = aiosqlite.Row
    return db
```

### Schema

```sql
-- Sessions: one row per conversation
CREATE TABLE sessions (
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

-- Messages: every user/assistant/tool message
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,           -- 'user', 'assistant', 'system', 'tool'
    content TEXT NOT NULL,
    created_at REAL DEFAULT (unixepoch('subsec'))
);

-- Tool calls: tracked separately for analytics
CREATE TABLE tool_calls (
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

-- Agents: generated agent registry
CREATE TABLE agents (
    name TEXT PRIMARY KEY,
    code_path TEXT NOT NULL,
    description TEXT,
    risk_tier TEXT DEFAULT 'moderate',
    created_at REAL DEFAULT (unixepoch('subsec')),
    last_used_at REAL,
    use_count INTEGER DEFAULT 0
);

-- Skills: learned patterns from sessions
CREATE TABLE skills (
    name TEXT PRIMARY KEY,
    description TEXT,
    confidence REAL DEFAULT 0.0,
    source_session_id TEXT,
    created_at REAL DEFAULT (unixepoch('subsec')),
    last_used_at REAL,
    use_count INTEGER DEFAULT 0
);

-- Audit log: every permission check and action
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    action TEXT NOT NULL,
    details_json TEXT,
    risk_tier TEXT,
    created_at REAL DEFAULT (unixepoch('subsec'))
);

-- State: key-value store for runtime state
CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (unixepoch('subsec'))
);

-- FTS5: full-text search across messages
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    role,
    content=messages,
    content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, role)
    VALUES (new.id, new.content, new.role);
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, role)
    VALUES('delete', old.id, old.content, old.role);
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, role)
    VALUES('delete', old.id, old.content, old.role);
    INSERT INTO messages_fts(rowid, content, role)
    VALUES (new.id, new.content, new.role);
END;

-- Indexes
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX idx_tool_calls_name ON tool_calls(tool_name);
CREATE INDEX idx_audit_session ON audit(session_id);
CREATE INDEX idx_audit_action ON audit(action);
CREATE INDEX idx_sessions_started ON sessions(started_at DESC);
```

---

## 4. Memory System

### Short-Term (In-Memory, Per-Session)

```python
class ShortTermMemory:
    """Dies when session ends. No disk I/O."""
    
    def __init__(self, max_messages=50, max_tool_cache=20):
        self.messages = deque(maxlen=max_messages)  # Last 50 messages
        self.tool_cache = OrderedDict()              # LRU, last 20 results
        self.agents = {}                            # Active agent states
        self.max_tool_cache = max_tool_cache
    
    def add_message(self, role, content):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
    
    def cache_tool_result(self, tool_name, args, result):
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        self.tool_cache[key] = {"result": result, "timestamp": time.time()}
        if len(self.tool_cache) > self.max_tool_cache:
            self.tool_cache.popitem(last=False)
    
    def get_context_window(self, max_tokens=4000):
        """Build context for Qwen, fitting within token limit."""
        messages = []
        total_tokens = 0
        for msg in reversed(self.messages):
            msg_tokens = estimate_tokens(msg["content"])
            if total_tokens + msg_tokens > max_tokens:
                break
            messages.insert(0, msg)
            total_tokens += msg_tokens
        return messages
```

### Long-Term (SQLite + Files)

- **Sessions**: `sessions` + `messages` tables in SQLite
- **Skills**: `skills` table + `~/.hive/skills/{name}/SKILL.md`
- **Agents**: `agents` table + `~/.hive/agents/generated/{name}.py`
- **Patterns**: Extracted from sessions, stored in `skills` table

### Memory Budget

| Component | Memory | Notes |
|---|---|---|
| Main process (CLI + Leader) | ~50 MB | Python + asyncio |
| Short-term memory (50 messages) | ~5 MB | Text in RAM |
| Tool cache (20 results) | ~2 MB | Small |
| Each agent process | ~30 MB | Python overhead |
| 4 concurrent agents | ~120 MB | Max |
| **Total** | **~200 MB** | Lean |

---

## 5. Security

### Threat Model

| Threat | Risk | Mitigation |
|---|---|---|
| Prompt injection | Critical | Permission system + code validation |
| Credential theft | Critical | Never expose API keys to agents |
| Data exfiltration | High | Network domain allowlist |
| Unauthorized file access | High | Filesystem path validation |
| Shell abuse | High | Dangerous pattern blocking |
| Cross-agent contamination | Medium | Separate processes, isolated state |
| Approval fatigue | Medium | Risk-based tiers (safe/moderate/sensitive/dangerous) |

### Permission Tiers

| Tier | Behavior | Tools |
|---|---|---|
| **safe** | Auto-allow | read_file, list_directory, search_content |
| **moderate** | Ask before | edit_file, write_file, run_command |
| **sensitive** | Ask every time | install_package, git_push, delete_file |
| **dangerous** | Denied | rm -rf, curl\|bash, env access, sudo |

### Dangerous Patterns (Regex)

```python
DENIED_PATTERNS = [
    r"rm\s+-rf",
    r"curl.*\|\s*bash",
    r"wget.*\|\s*bash",
    r"eval\s*\(",
    r"exec\s*\(",
    r">\s*/dev/sd",
    r"chmod\s+777",
    r"sudo\s+.*",
]
```

### Filesystem Isolation

```python
# Agent CAN access
ALLOWED_PATHS = [
    os.getcwd(),                    # Project directory
    os.path.join(os.getcwd(), "**"), # Subdirectories
    "~/.hive/",                     # HIVE's own data
]

# Agent CANNOT access
DENIED_PATHS = [
    "~/.ssh/", "~/.aws/", "~/.gnupg/", "~/.env",
    "~/.bashrc", "~/.zshrc", "/etc/", "/usr/",
    "/bin/", "/sbin/", "/proc/", "/sys/",
]

# Credential files
CREDENTIAL_PATTERNS = [
    "*.env", "*.key", "*.pem", "*.p12", "*.pfx",
    "*credentials*", "*secret*", "*token*",
]
```

### Network Isolation

```python
ALLOWED_DOMAINS = [
    "api.dashscope.aliyuncs.com",  # Qwen API
    "registry.npmjs.org",          # npm
    "pypi.org",                    # Python packages
    "api.github.com",              # GitHub
    "raw.githubusercontent.com",   # GitHub raw
]
```

### Credential Protection

```python
BLOCKED_ENV_VARS = [
    "DASHSCOPE_API_KEY",   # We use it, agent never sees it
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
]

def get_sanitized_context():
    return {
        "project_dir": os.getcwd(),
        "platform": sys.platform,
        "python_version": sys.version,
        # NO API keys
    }
```

### Audit Logging

Every action logged to `audit` table:
- tool_call
- permission_check
- permission_granted
- permission_denied
- file_access
- command_execution
- agent_spawned
- agent_killed

### Agent Code Validation

```python
DANGEROUS_PATTERNS = [
    "import os", "import subprocess", "import shutil",
    "os.system(", "subprocess.call(", "subprocess.Popen(",
    "open('/etc/", "open('/usr/", "open('~/.ssh/",
    "open('~/.aws/", "eval(", "exec(", "__import__(",
]

def validate_agent_code(code: str) -> bool:
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            return False
    return True
```

---

## 6. CLI Interface

### Design Principles

- **Plain text output** — no boxes, no panels, no borders
- **Simple prefix** — `>` for input, `●` for agent actions
- **Inline permissions** — ask in the same stream
- **Slash commands** — `/help`, `/sessions`, `/quit`
- **Streaming** — text appears as generated
- **You own your terminal** — just another CLI tool

### Output Format

```
User input:      > your message here
Agent action:    ● tool_name (details)
Agent text:      plain text, no decoration
Tool result:     shown briefly, collapsed by default
Diff:            - removed line
                 + added line
Permission:      ? Allow edit_file on main.py? [Y/n]
Error:           ! Error: file not found
```

### Full Session Example

```
$ hive
hive v0.1.0 │ qwen-max │ type /help for commands

> fix the bug in main.py

  ● Reading main.py... (847 lines)
  ● Found bug on line 42

  The condition `if x > 0` should be `if x >= 0`. Zero values
  were being incorrectly filtered out. Want me to fix it?

> yes

  ● Editing main.py (line 42)
    - if x > 0
    + if x >= 0
  ● Running tests... 12 passed

  Done. Bug fixed.

> /help

  Commands:
    /help           Show this help
    /quit           Exit hive
    /sessions       List past sessions
    /resume <id>    Resume a session
    /agents         List active agents
    /kill <name>    Kill an agent
    /skills         List learned skills
    /compact        Compress context window
    /model          Switch model
    /mode           Switch permission mode
    /clear          Clear screen

> /sessions

  Recent sessions:
    1. abc123  Fix login bug        Jul 05  12.4k tokens
    2. def456  Add dark mode         Jul 04   8.2k tokens
    3. ghi789  Refactor API          Jul 03  22.1k tokens

> /resume abc123

  Resumed session abc123 (Fix login bug)
  Context: 45 messages, 12.4k tokens

> /mode auto-accept

  Mode changed: auto-accept edits
  File edits will be auto-approved. Shell commands still require approval.

> _
```

### Permission Prompt (Inline)

```
> edit the config file

  I want to edit config.json to add the new API endpoint.

  ? Allow edit_file on config.json? [Y/n/_ always]: 
```

Not a modal. Not a panel. Just a question in the stream.

### Modes

| Mode | Behavior |
|---|---|
| **normal** (default) | Ask for every moderate+ action |
| **auto-accept** | Skip permission for file edits only |
| **plan** | Read-only, no writes allowed |
| **bypass** | Skip all permissions (testing only) |

### Keybindings

| Key | Action |
|---|---|
| Enter | Send message |
| Ctrl+C | Cancel current agent |
| Ctrl+L | Clear screen |
| Ctrl+D | Exit |

---

## 7. Agent System

### Leader (hive/leader.py)

The orchestrator. Receives user tasks, decides what to do.

Responsibilities:
- Decompose complex tasks into subtasks
- Decide which agents to spawn
- Assign tool sets to agents
- Manage permissions
- Coordinate results
- Handle failures

### Creator Agent (hive/creator.py)

Generates Python code for new agents via Qwen.

Responsibilities:
- Receive agent specification (name, purpose, tools)
- Generate Python class with `execute()` method
- Validate code against dangerous patterns
- Save to `~/.hive/agents/generated/{name}.py`
- Register in `agents` table

### Worker Agents (hive/runtime.py)

Execute tasks in separate processes.

Properties:
- Run in separate Python process (own memory space)
- Have restricted tool sets (not all tools)
- Can't spawn other agents
- Can't access other agents' state
- Return results to leader
- Timeout after 60 seconds

### Agent Code Format

```python
# ~/.hive/agents/generated/fix_syntax.py
"""Agent: fix_syntax — Fixes syntax errors in Python files."""

class FixSyntaxAgent:
    def __init__(self, tools):
        self.tools = tools
    
    def execute(self, task, context):
        """Execute the agent's task."""
        # 1. Find files with syntax errors
        # 2. Read and analyze them
        # 3. Fix the errors
        # 4. Verify fixes
        return {"status": "success", "files_fixed": [...]}
```

---

## 8. LLM Layer (hive/llm.py)

### Provider: Qwen via DashScope

```python
import httpx

class QwenClient:
    def __init__(self, api_key, model="qwen-max"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    async def chat(self, messages, tools=None):
        """Send chat completion request."""
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60.0,
            )
            return resp.json()
    
    async def stream(self, messages, tools=None):
        """Stream chat completion."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60.0,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])
```

---

## 9. Tools (hive/tools.py)

### Available Tools

| Tool | Category | Permission | Description |
|---|---|---|---|
| read_file | file | safe | Read file contents |
| list_directory | file | safe | List directory contents |
| search_content | file | safe | Search file contents (grep) |
| edit_file | file | moderate | Edit file (old/new replacement) |
| write_file | file | moderate | Write file contents |
| run_command | shell | moderate | Run shell command |
| git_status | git | safe | Run git status |
| git_diff | git | safe | Run git diff |
| git_commit | git | sensitive | Create git commit |
| web_fetch | web | moderate | Fetch URL content |
| web_search | web | moderate | Search the web |

### Tool Registry

```python
TOOLS = {
    "read_file": {
        "description": "Read the contents of a file",
        "parameters": {"path": "string"},
        "risk_tier": "safe",
    },
    "edit_file": {
        "description": "Edit a file by replacing text",
        "parameters": {"path": "string", "old": "string", "new": "string"},
        "risk_tier": "moderate",
    },
    # ...
}
```

---

## 10. File Plan (Build Order)

### Phase 1: Foundation (no dependencies)

| # | File | Purpose | Est. Lines |
|---|---|---|---|
| 1 | `hive/__init__.py` | Package init, version | 5 |
| 2 | `hive/config.py` | Settings, paths, env vars | 60 |
| 3 | `hive/storage.py` | SQLite connection, schema, CRUD | 200 |
| 4 | `hive/permissions.py` | Risk tiers, validation, audit | 150 |
| 5 | `hive/memory.py` | Short-term (RAM) + long-term (SQLite) | 100 |
| 6 | `hive/llm.py` | Qwen API client (httpx async) | 150 |

### Phase 2: Tools & Runtime (depends on Phase 1)

| # | File | Purpose | Est. Lines |
|---|---|---|---|
| 7 | `hive/tools.py` | File, shell, git, web tools | 200 |
| 8 | `hive/runtime.py` | Agent loop (Qwen ↔ tools, process pool) | 250 |
| 9 | `hive/creator.py` | Agent code generation via Qwen | 150 |
| 10 | `hive/leader.py` | Task orchestration, agent spawning | 200 |

### Phase 3: CLI & Integration (depends on Phase 2)

| # | File | Purpose | Est. Lines |
|---|---|---|---|
| 11 | `hive/cli.py` | Main loop, input, output formatting | 150 |
| 12 | `hive/main.py` | Entry point, argument parsing | 30 |

### Phase 4: Packaging

| # | File | Purpose | Est. Lines |
|---|---|---|---|
| 13 | `pyproject.toml` | Package definition, deps, scripts | 40 |
| 14 | `requirements.txt` | Updated dependencies | 15 |

### Total

**14 files, ~1,700 lines**

---

## 11. Dependencies

```
aiosqlite>=0.20.0      # Async SQLite
httpx>=0.27.0          # Async HTTP client
rich>=13.0.0           # Terminal colors/formatting
python-dotenv>=1.0.0   # Load .env
pydantic>=2.9.0        # Settings validation
```

**5 dependencies. Lean.**

---

## 12. What Gets Deleted (Later)

| Path | Reason |
|---|---|
| `core/` (20 files) | Replaced by `hive/` |
| `agents/` (20 files) | Replaced by generated agents |
| `db/` (3 files) | SQLite replaced by new schema |
| `frontend/` | Replaced by CLI |
| `frontend-next/` | Replaced by CLI |
| `benchmarks/` | Can re-add as CLI command later |
| `tests/` | Will be rewritten |
| `main.py` (old) | Replaced by `hive/main.py` |
| `requirements.txt` | Replaced by `pyproject.toml` |

**Don't delete yet. Build new alongside old. Switch when ready.**

---

## 13. Session Flow

```
1. User runs `hive`
2. CLI loads config from ~/.hive/config.json
3. CLI connects to SQLite
4. CLI creates new session (or resumes existing)
5. User types message
6. Leader receives message
7. Leader builds context (short-term memory + system prompt)
8. Leader sends to Qwen API
9. Qwen responds with text + optional tool calls
10. For each tool call:
    a. Permission check (safe/moderate/sensitive/dangerous)
    b. If moderate+: ask user
    c. If approved: execute tool
    d. Log to audit table
    e. Return result to leader
11. Leader sends results back to Qwen
12. Qwen responds with final answer
13. Answer printed to terminal
14. Messages saved to SQLite
15. Loop back to step 5
```

---

## 14. Creator Agent Flow

```
1. Leader decides a new agent is needed
2. Leader sends spec to Creator Agent:
   - Name, purpose, tools needed, risk tier
3. Creator Agent sends spec to Qwen:
   "Generate Python class with execute() method"
4. Qwen generates agent code
5. Creator validates code against dangerous patterns
6. If valid: save to ~/.hive/agents/generated/{name}.py
7. Register in agents table
8. Return agent code to Leader
9. Leader spawns agent in separate process
```

---

## 15. Key Decisions Summary

| Decision | Choice | Why |
|---|---|---|
| Interface | Plain CLI, not TUI | Clean, simple, not AI slop |
| Framework | None (maybe Rich for colors) | Lean, no bloat |
| Storage | SQLite (raw aiosqlite) | Fast queries, FTS5, no ORM overhead |
| Short-term memory | In-memory deque | Fast, dies with session |
| Long-term memory | SQLite + files | Persistent, searchable |
| RAG | No | Grep + FTS5 is enough |
| LLM | Qwen cloud only | No local models |
| Parallelism | ProcessPoolExecutor (max 4) | Bypass GIL |
| Security | 8-layer defense | Permission + filesystem + network + audit |
| Agent code | Executable Python | Real classes, not metadata |
| Permissions | Risk-based tiers | safe/moderate/sensitive/dangerous |
| CLI output | Plain text with prefixes | ●, -, +, ? |
| Dependencies | 5 total | aiosqlite, httpx, rich, dotenv, pydantic |
