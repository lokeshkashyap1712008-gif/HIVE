# HIVE — AUTONOMOUS HIERARCHICAL AGENT SWARM
## Master Plan — Qwen Cloud Hackathon 2026 | Track 3: Agent Society

---

## TABLE OF CONTENTS
1. Project Overview
2. The Big Idea — Why This Wins
3. How to Run (Cloud + Local Setup)
4. System Architecture
5. Agent Hierarchy & Chain of Command
6. All 14 Agents — What They Do
7. Full Action Capability Map
8. Demo Scenarios (for the 3-minute video)
9. HIVE Benchmark Suite (6 automated tests)
10. HIVE Arena — Adversarial Demo
11. All Metrics (judging criteria)
12. Winner Comparison
13. Tech Stack
14. Complete Phase-by-Phase Build Guide
15. Timeline & Deadline
16. Can You Win?
17. File Structure

---

## 1. PROJECT OVERVIEW

**Name:** HIVE
**Tagline:** "The autonomous swarm that coordinates, adapts, and delivers — without you lifting a finger."
**Track:** 3 — Agent Society
**Core Concept:** A hierarchical multi-agent swarm with a Leader, Creator agents, Deletor agents, and 14 specialized worker pawns — all stateless, all running on Qwen (cloud or local), all coordinating to solve complex real-world tasks faster than any single agent could.

**What it actually does:**
- Receives a plain-English task from the user
- Leader decomposes it, spawns specialized agents
- Agents run in parallel, each doing their thing (scan, pay, login, code, report)
- Agents die after completing their task, memory is freed automatically
- Leader compiles the result and shows a dashboard proving the swarm beat a single agent

**What makes it different from every other hackathon project:**
- CREATOR + DELETOR are first-class agents (not just code patterns) — NONE of the winners do this
- Memory auto-adjust: agents spawn more or fewer based on available RAM
- Cloud + local on the SAME model family (Qwen everywhere)
- Real-world web actions: login, payment, account creation
- GPU machine optimization as a live use case
- Fault tolerance: standby leader election, crash recovery
- Live visual collaboration graph (judges SEE agents talking to each other)

---

## 2. THE BIG IDEA — WHY THIS WINS

### Track 3 Judging Criteria (what judges want to see):
1. Multi-agent collaboration with distinct capabilities
2. Task decomposition and role assignment
3. Dialogue and negotiation between agents
4. Conflict resolution between agents
5. **Measurable efficiency gain over a single-agent baseline** ← MOST IMPORTANT

### What Quorum (Track 3 winner) did:
- 3-agent council: Proposer / Skeptic / Referee
- Deterministic safety guardrail
- Showed lone agent vs council comparison in UI
- Proved council stops blind execution

### Why HIVE beats Quorum:
- **14 agents vs 3** — real specialization, not just 3 roles
- **Real-world actions vs just debate** — login, payment, code, cloud deploy
- **Creator + Deletor** — nobody has this, it's unique and impressive
- **GPU optimization** — Quorum can't do this at all
- **Cloud + local dual mode** — Quorum is cloud-only
- **Auto memory adjustment** — Quorum doesn't adapt to resources
- **Fault tolerance** — Quorum dies if the referee crashes
- **Live visual graph** — judges SEE collaboration, not just read about it

### The ONE thing you MUST prove:
> "The swarm completes this task X% faster with Y% better quality than a single agent."

If the dashboard shows this clearly, you win. Everything else supports this proof.

---

## 3. HOW TO RUN (CLOUD + LOCAL SETUP)

### Environment Setup

Create a `.env` file in the project root:

```env
# ===== LLM PROVIDER (auto-detected) =====
# If DASHSCOPE_API_KEY is set: use Qwen Cloud (DashScope)
# If not set: fall back to local Ollama
DASHSCOPE_API_KEY=sk-your-key-here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# ===== LOCAL OLLAMA (used when no DashScope key) =====
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b           # fast for parallel workers
OLLAMA_LARGE_MODEL=qwen2.5:14b   # for Leader, Judge, Safety

# ===== SYSTEM =====
LOG_LEVEL=INFO
DEBUG=false
MAX_CONCURRENT_AGENTS=8
MEMORY_THRESHOLD_MB=2048

# ===== INTEGRATIONS (optional — add as you build) =====
GITHUB_TOKEN=ghp_xxx
STRIPE_SECRET_KEY=sk_live_xxx
PAYPAL_CLIENT_ID=xxx
SENDGRID_API_KEY=SG.xxx
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
ALIBABA_CLOUD_ACCESS_KEY=xxx
ALIBABA_CLOUD_SECRET_KEY=xxx
ALIBABA_CLOUD_REGION=us-west-1
```

### Cloud Mode (Qwen Max via DashScope)

```bash
# Install dependencies
pip install dashscope fastapi uvicorn langgraph sqlalchemy aiohttp playwright

# Run the server
python -m uvicorn main:app --reload --port 8000

# API docs at http://localhost:8000/docs
# Dashboard at http://localhost:8000
```

### Local Mode (Qwen via Ollama)

```bash
# Install Ollama from https://ollama.com

# Pull Qwen models
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b
ollama pull qwen2.5-coder:7b

# Start Ollama server
ollama serve

# Run HIVE (it auto-detects no DASHSCOPE_API_KEY and uses Ollama)
python -m uvicorn main:app --reload --port 8000
```

### Model Selection Strategy

| Agent Type | Quality Needed | Cloud (Qwen Max) | Local (Ollama) |
|---|---|---|---|
| Leader (Hive Core) | HIGH | Qwen Max | qwen2.5:14b |
| Safety Agent | HIGH | Qwen Max | qwen2.5:14b |
| Judge (conflict resolution) | HIGH | Qwen Max | qwen2.5:14b |
| Account Manager | MEDIUM | Qwen Max | qwen2.5:7b |
| Payment Agent | MEDIUM | Qwen Max | qwen2.5:7b |
| Web Scout | MEDIUM | Qwen Max | qwen2.5:7b |
| Cloud Tester | MEDIUM | Qwen Max | qwen2.5:7b |
| Code Runner | MEDIUM | Qwen Max | qwen2.5:7b |
| Code Architect | MEDIUM-HIGH | Qwen Max | qwen2.5:14b |
| Report Agent | LOW | Qwen Max | qwen2.5:7b |
| Diagnostician | LOW-MEDIUM | Qwen Max | qwen2.5:7b |
| Security Scout | MEDIUM | Qwen Max | qwen2.5:7b |
| Red Team Agent | MEDIUM-HIGH | Qwen Max | qwen2.5:14b |
| Data Analyst | LOW | Qwen Max | qwen2.5:7b |
| GPU Tuner | LOW-MEDIUM | Qwen Max | qwen2.5:7b |
| Scheduler Agent | LOW | Qwen Max | qwen2.5:7b |
| Communicator Agent | LOW | Qwen Max | qwen2.5:7b |

**RTX 3050 6GB note:** Run Leader + 2 workers = ~5.8GB VRAM with qwen2.5:7b. If you need qwen2.5:14b for quality tasks, run those serially (one at a time) to avoid VRAM overflow.

---

## 4. SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER (Natural Language Task)                │
│                 "Optimize my GPU, find bugs in my site,             │
│                  create a Stripe invoice, and email me the report"   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    HIVE CORE (Leader / Hive Core)                  │
│  - Receives task, decomposes into sub-tasks                        │
│  - SAFETY AGENT: one-way ratchet — blocks dangerous actions          │
│  - Assigns roles to workers via Agent Forge                         │
│  - Collects outputs, merges results                                 │
│  - Writes all decisions to AUDIT LOG (append-only, searchable)       │
│  - Runs on: Qwen Max (cloud) or qwen2.5:14b (local)                │
│  - STANDY BY LEADER: highest-capability worker, auto-elected        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ spawns / directs / kills
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  AGENT FORGE    │ │ WORKER POOL  │ │  CLEANUP CREW   │
│  (Creator)      │ │  (14 types)  │ │  (Deletor)      │
│                 │ │              │ │                  │
│ Spawns agents   │ │ Each worker  │ │ Kills zombie    │
│ dynamically.    │ │ is STATELESS │ │ agents, frees   │
│ Memory-aware:   │ │ context +    │ │ memory, enforces│
│ checks RAM      │ │ output only │ │ efficiency.     │
│ before spawning │ │ dies after   │ │ Runs every 30s  │
│ Can terminate  │ │ completion   │ │                 │
│ stalled agents  │ │ All call     │ │ Cannot delete   │
│ Never spawns   │ │ Qwen for     │ │ Leader or Forge │
│ if RAM < 500MB  │ │ reasoning   │ │                 │
└─────────────────┘ └──────────────┘ └──────────────────┘
         │                 │
         │                 │ report back (output only)
         │                 ▼
         │         ┌──────────────────┐
         │         │  RESULT MERGE     │
         │         │  Report Agent     │
         │         │  compiles final   │
         │         │  output           │
         │         └────────┬─────────┘
         │                  │
         │                  ▼
         │         ┌──────────────────┐
         │         │  DASHBOARD (React) │
         │         │  Live metrics,    │
         │         │  agent graph,     │
         │         │  whiteboard       │
         └────────►└──────────────────┘

WORKER POOL DETAIL (14 agents, spawned on demand):
  ┌──────────────────────────────────────────────────────┐
  │ Web Scout        → HTTP, API, scraping, sitemap       │
  │ Account Manager  → Create accounts, login, 2FA, OAuth│
  │ Payment Agent    → Stripe/PayPal, invoices, refunds   │
  │ Cloud Tester     → Alibaba Cloud ECS/FC deploy/test  │
  │ Code Runner      → Execute code, tests, git, Docker  │
  │ Report Agent     → PDF, email, Slack, Discord, webhooks│
  │ Diagnostician    → Log parse, error analysis, fixes   │
  │ Security Scout   → OWASP Top 10, CVE, pen test       │
  │ Code Architect   → Clone repo, write feature, PR     │
  │ Red Team Agent   → Simulate attacker, threat model   │
  │ Data Analyst     → Stats, charts, SQL, CSV/JSON      │
  │ GPU Tuner        → nvidia-smi, thermal, VRAM, clocks│
  │ Scheduler Agent  → Cron, retry, timeouts, queuing    │
  │ Communicator     → Email, Slack, Discord, Telegram  │
  └──────────────────────────────────────────────────────┘
```

### Data Flow

```
User Task (plain English)
    │
    ▼
Leader (Hive Core)
    │
    ├──► Safety Agent check ──► [BLOCK if dangerous] ──► STOP
    │
    ▼
Task Decomposition ──► List of sub-tasks with priority
    │
    ├──► Agent Forge (checks memory, spawns workers)
    │         │
    │         ▼
    │    Worker Pool (parallel execution)
    │         │
    │         ▼
    │    Each worker: { task_id, status, output, tokens, time }
    │
    ▼
Cleanup Crew (kills finished workers)
    │
    ▼
Report Agent (compiles all outputs)
    │
    ▼
Dashboard (metrics + single vs multi comparison)
```

### SQLite Database Schema

```sql
-- Task history
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    description TEXT,
    status TEXT,  -- pending/in_progress/completed/failed
    created_at DATETIME,
    completed_at DATETIME,
    tokens_used INTEGER,
    time_taken_seconds REAL
);

-- Agent state checkpoints (for crash recovery)
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    agent_id TEXT,
    agent_type TEXT,
    state JSON,
    checkpointed_at DATETIME
);

-- Audit log (append-only)
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    leader_decision TEXT,
    reason TEXT,
    agents_affected TEXT  -- JSON array
);

-- Agent reputation scores
CREATE TABLE agent_scores (
    agent_type TEXT PRIMARY KEY,
    total_tasks INTEGER,
    successful_tasks INTEGER,
    false_positives INTEGER,
    avg_quality_score REAL,
    last_updated DATETIME
);

-- Single vs multi comparison results
CREATE TABLE benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    mode TEXT,  -- single / multi
    time_taken REAL,
    tokens_used INTEGER,
    quality_score REAL,
    benchmark_type TEXT
);
```

---

## 5. AGENT HIERARCHY & CHAIN OF COMMAND

### The Chain of Command (10 Formal Rules)

```
1. ONLY Leader can spawn agents (via Agent Forge)
2. ONLY Leader assigns roles — workers cannot self-assign
3. Workers report to Leader, NOT to each other
4. If worker fails 3x → Leader marks STALE → Cleanup Crew kills it
5. If two workers conflict → Leader adjudicates via Judge sub-agent
6. Agent Forge cannot spawn without Leader authorization
7. Cleanup Crew cannot delete Leader or Agent Forge
8. Leader writes ALL decisions to audit log (append-only)
9. Any agent can send an ALERT up the chain (one-way upward only)
10. Workers cannot talk to each other — only through Leader
```

### The Safety Agent (One-Way Ratchet)

Built into the Leader. Before ANY action executes:

```
IS IT DANGEROUS? (SQL injection, XSS, payment > $1000, delete request)
    ├── YES → BLOCK → log reason → notify user
    └── NO  → proceed

IS IT REVERSIBLE?
    ├── NO  → require second confirmation from user
    └── YES → proceed

IS IT HIGH-STAKES? (payment, account deletion, cloud resource destruction)
    ├── YES → require user approval (can be pre-approved via config)
    └── NO  → proceed automatically
```

The Safety Agent can ONLY block. It can never unblock something it blocked. This is the one-way ratchet.

### Standby Leader Election

```
Every 30 seconds:
  - Each worker reports: uptime + capability score
  - Worker with highest (uptime * capability_score) wins standby
  - Standby leader monitors primary Leader heartbeat (every 5s)

IF PRIMARY LEADER CRASHES:
  - Standby takes over within 5 seconds
  - Picks up from last checkpoint
  - Notifies all workers of new leader
  - Original leader, if revived, becomes a worker
```

### Conflict Resolution Flow

```
Worker A and Worker B disagree on task result
    │
    ▼
Leader detects conflict (automatically or via report)
    │
    ▼
Leader spawns JUDGE sub-agent (stateless, short-lived)
    │
    ▼
JUDGE receives:
  - Worker A's output + reasoning trace
  - Worker B's output + reasoning trace
  - Original task description
    │
    ▼
JUDGE returns: { winner: "A" | "B", reason: "...", confidence: 0.0-1.0 }
    │
    ▼
Leader adopts winner, logs the disagreement + resolution in audit log
```

---

## 6. ALL 14 AGENTS — WHAT THEY DO

### Leader: HIVE CORE
- Receives natural language task from user
- Decomposes task into sub-tasks
- Assigns roles to workers via Agent Forge
- Collects and merges outputs
- Handles conflict resolution
- Enforces safety via Safety Agent
- Manages standby leader election
- Writes all decisions to audit log

### Agent Forge (CREATOR)
- Spawns workers on demand
- Checks available RAM before spawning
- If RAM < 2GB: reduces concurrent agents from 8 to 3
- If RAM < 500MB: queues tasks, runs one at a time
- Tracks agent state and can terminate stalled agents
- Self-reports memory footprint after each spawn

### Cleanup Crew (DELETOR)
- Runs every 30 seconds
- Identifies zombie agents (finished but not cleaned up)
- Frees memory from dead agents
- Enforces the 3-failure kill rule
- Cannot delete: Leader, Agent Forge, or itself
- Reports cleanup stats to Leader

### Web Scout
- HTTP GET/POST/PUT/DELETE with custom headers and cookies
- Session and cookie management across requests
- API integration (REST, GraphQL)
- Form submission (login, registration, contact)
- Sitemap crawling, broken link detection
- SSL certificate analysis
- WHOIS lookups
- Browser automation (Playwright) for JS-rendered sites
- Returns structured JSON findings

### Account Manager
- Create accounts via API (GitHub, Gmail, any OAuth service)
- Login with username/password + 2FA code handling
- OAuth 2.0 flow automation
- Token refresh and session management
- Email account creation via IMAP/SMTP
- API key creation and rotation
- Session enumeration and management

### Payment Agent
- Stripe API: create/update/delete customers, invoices, subscriptions
- PayPal API: billing agreements, payment processing
- Generate and send invoices via email
- Process refunds and handle disputes
- Subscription tier management
- Currency conversion via API
- Payment status webhooks (receive and process)

### Cloud Tester
- Alibaba Cloud ECS: start/stop/configure instances
- 函数计算 (FC): deploy serverless functions, check invocation logs
- Docker: build, push, pull, run containers
- Kubernetes: scale pods, check status, view logs
- Health check endpoints (HTTP ping, port check)
- Resource creation and deletion
- SSL certificate provisioning (Let's Encrypt)
- DNS record management via API

### Code Runner
- Execute code in isolated environment
- Run test suites and parse results
- Git operations (clone, branch, commit, push, pull)
- Container build and deployment
- CI/CD pipeline trigger and monitoring
- Database migration execution
- Linting and formatting

### Report Agent
- Generate structured PDF reports
- Send emails via SMTP (Gmail, SendGrid)
- Post to Slack channels
- Send Discord webhooks with embeds
- Telegram bot messages
- Format data as tables, charts, markdown
- Aggregate results from multiple agents
- Generate before/after comparison reports

### Diagnostician
- Parse application logs (nginx, docker, syslog)
- Analyze stack traces and error messages
- Read metrics (CPU, memory, disk, network)
- Trace analysis (request tracing, flame graphs)
- Suggest actionable fixes with code snippets
- Identify patterns in recurring failures
- Run diagnostics in a loop until fixed

### Security Scout
- OWASP Top 10 automated checks
- CVE vulnerability scanning
- SQL injection detection (sqlmap-style)
- XSS vector identification
- Directory enumeration (dirbuster-style)
- CVE severity ratings (Critical/High/Medium/Low)
- Returns structured vulnerability report as JSON
- ONLY runs on Safety Agent-approved targets

### Code Architect
- Clone GitHub repos, analyze structure
- Understand codebase architecture via file parsing
- Write complete features given a description
- Create Pull Requests via GitHub API
- Run CI checks and parse results
- If CI fails: loop back to fix (up to 3 retries)
- Full loop: write → test → fail → fix → test → pass → PR merge

### Red Team Agent
- Simulate real attacker against authorized infrastructure
- Generate phishing templates (for defense training)
- Social engineering reconnaissance (OSINT)
- Threat model generation ("if I were an attacker...")
- Breach analysis: what would happen if X was compromised
- Return: threat model document with likelihood + impact ratings

### Data Analyst
- Read/write CSV, JSON, Excel, SQLite
- SQL queries (MySQL, PostgreSQL, SQLite)
- Statistical analysis (pandas, scipy)
- Chart generation (matplotlib, plotly)
- Data cleaning and normalization
- API data aggregation from multiple sources
- Trend analysis and key insight extraction

### GPU Tuner
- Read nvidia-smi output: temperature, VRAM, utilization, clocks
- Detect thermal throttling and auto-correct
- Adjust power limit and clock speeds
- Monitor VRAM usage and alert on high usage
- Report before/after metrics ("83°C → 67°C")
- Auto-correct when temperature > 85°C
- Monitor GPU utilization % and suggest optimization

### Scheduler Agent
- Create cron-style scheduled tasks
- Retry failed tasks with exponential backoff
- Set timeouts per agent task
- Priority queue management
- Sequential and parallel execution control
- Delayed task execution
- Task dependency management

### Communicator Agent
- Send emails via SMTP (Gmail, SendGrid)
- Post Slack messages to channels
- Send Discord webhooks with rich embeds
- Telegram bot messages
- SMS via Twilio
- Slack OAuth app installation and usage

---

## 7. FULL ACTION CAPABILITY MAP

### WEB + SCRAPING
```
- GET / POST / PUT / DELETE HTTP requests
- Custom headers, cookies, user-agent
- Form submission (login, registration, contact forms)
- Session and cookie management
- REST API and GraphQL integration
- File downloads and uploads
- Screenshot capture of web pages
- HTML parsing, XPath, regex extraction
- Browser automation (Playwright/Selenium) for JS sites
```

### ACCOUNTS + AUTHENTICATION
```
- Create accounts via API (GitHub, Gmail, services)
- Login with username/password + 2FA handling
- OAuth 2.0 flow automation (authorization code, PKCE)
- Token refresh and session management
- API key creation and rotation
- Email account creation via IMAP/SMTP
```

### PAYMENTS + FINANCIAL
```
- Stripe: customers, invoices, subscriptions, payment intents
- PayPal: billing agreements, checkout, payouts
- Generate and send professional invoices
- Process refunds and disputes
- Subscription upgrade/downgrade
- Currency conversion via API
- Payment webhook processing
```

### CLOUD + DEPLOYMENT
```
- Alibaba Cloud ECS: create/start/stop/configure/delete instances
- 函数计算 (FC): deploy, invoke, delete serverless functions
- Docker: build, push, pull, run, logs, exec
- Kubernetes: apply manifests, scale, describe, logs
- AWS/GCP/Azure equivalents via SDK
- SSL certificate provisioning (Let's Encrypt, ACM)
- DNS record management (Route53, AliDNS)
```

### CODE + DEVELOPMENT
```
- Git clone, branch, commit, push, pull, merge
- Create Pull Requests with description and labels
- Run test suites (pytest, jest, go test)
- Parse CI/CD results
- Code review and linting (eslint, pylint)
- Container build + push to registry
- Database migration (Alembic, Flyway)
```

### COMMUNICATION
```
- Send emails (SMTP, SendGrid API)
- Post Slack messages with blocks and attachments
- Send Discord webhooks with rich embeds
- Telegram bot messages and photo uploads
- SMS via Twilio
- Slack OAuth app flow
```

### DATA + ANALYSIS
```
- Read/write CSV, JSON, Excel (.xlsx), SQLite
- SQL queries across MySQL, PostgreSQL, SQLite
- Statistical analysis: mean, median, std, regression
- Chart generation: line, bar, scatter, pie
- Data cleaning: null handling, deduplication
- Multi-source API data aggregation
```

### SCHEDULING + ORCHESTRATION
```
- Cron job creation (scheduled tasks)
- Retry with exponential backoff (3 attempts default)
- Per-task timeout enforcement
- Priority queue (high/medium/low)
- Sequential and parallel execution modes
- Task dependency chains (A must finish before B)
```

### MONITORING + LOGGING
```
- Parse logs: nginx access/error, docker, syslog, app logs
- Query metrics: Prometheus, CloudWatch, AliCloud ARMS
- GPU monitoring: nvidia-smi real-time
- Alert generation on threshold crossing
- Dashboard data population
```

---

## 8. DEMO SCENARIOS (for the 3-minute video)

### MAIN DEMO: "The Full Stack Fix"

**Setup:** Your web application is slow and broken. Here's what happens:

```
USER: "My e-commerce site is broken and slow. Fix it, optimize my GPU,
       deploy to Alibaba Cloud, create a Stripe invoice for the client,
       and send me a full report on Slack."

TIMELINE:
  0:00-0:15  Leader receives task, Safety Agent approves all actions
  0:15-0:30  Leader decomposes: 6 sub-tasks, assigns to 6 workers
  0:30-1:00  Workers run in PARALLEL:
               - Web Scout crawls site → finds 4 bugs + 3 vulnerabilities
               - GPU Tuner reads nvidia-smi → 83°C, throttling
               - Cloud Tester pings Alibaba Cloud → instance dead
               - Account Manager logs into admin panel → user list extracted
               - Payment Agent checks Stripe → 3 failed payments found
  1:00-1:30  Diagnostician analyzes errors → suggests fixes
             Code Architect applies fixes → 2 PRs created
             GPU Tuner optimizes → 83°C → 67°C
  1:30-2:00  Cloud Tester redeploys to Alibaba Cloud
             Report Agent compiles everything
             Communicator sends Slack message with summary
  2:00-2:15  Dashboard shows:
               "Single agent: 47 min | Swarm: 8 min | 83% faster"
               "Bugs found: 4 | Vulnerabilities: 3 | Cost saved: $42"
  2:15-2:45  Live interaction graph shows agents talking
             Whiteboard shows artifacts from each agent
             Audit log shows Leader decisions (searchable)
  2:45-3:00  Final report displayed, win condition highlighted
```

### SECONDARY DEMO: Payment + Account Flow

```
USER: "Create a Stripe customer for john@example.com, generate a $500
       invoice, send it via email, and post the result to #invoices on Slack."

  Web Scout: verifies email domain exists
  Account Manager: creates Stripe customer via API
  Payment Agent: generates invoice, attaches to customer
  Report Agent: formats invoice as PDF
  Communicator: emails invoice to john@example.com, posts Slack notification
  Dashboard: shows invoice status in real-time
```

### THIRD DEMO: Security Assessment

```
USER: "Run a full security audit on example.com and send the report
       to my email."

  Safety Agent: approves target (example.com)
  Security Scout: runs OWASP Top 10 checks
  Web Scout: crawls for exposed endpoints
  Red Team Agent: generates threat model
  Data Analyst: aggregates findings, assigns severity
  Report Agent: formats as security report PDF
  Communicator: emails report to user
```

---

## 9. HIVE BENCHMARK SUITE (6 Automated Tests)

All benchmarks output: JSON results + visual cards in the dashboard.

### BENCHMARK 1: Single vs Multi Comparison
```
Run 20 diverse tasks, each TWICE:
  - Once as a SINGLE AGENT (Leader only, no workers)
  - Once as a SWARM (Leader + workers)
Measure: TIME, TOKENS, ACCURACY (LLM-judged), COMPLETION RATE
Output: bar chart per task + aggregate comparison
This is the MAIN metric judges want to see.
```

### BENCHMARK 2: Swarm Stress Test
```
Spawn 20 agents simultaneously, all doing DIFFERENT tasks.
Measure: time to first result, memory pressure, kill efficiency
Goal: prove swarm scales without degradation
Pass condition: all 20 agents complete < 60 seconds, no OOM
```

### BENCHMARK 3: Fault Tolerance
```
1. Start 5-worker swarm on a task
2. Kill one worker mid-task (SIGKILL simulation)
3. Verify: standby leader takes over < 5 seconds
4. Verify: task resumes from last checkpoint
5. Verify: no data loss
Run 10 times → show 100% recovery rate
```

### BENCHMARK 4: Memory Pressure
```
Simulate low RAM: cap at 1GB available
Verify: Agent Forge reduces spawns from 8 → 3
Verify: queued tasks execute in priority order
Verify: no OOM crashes, no agents die unexpectedly
Report: "Graceful degradation: 8 → 3 agents in 1.2s"
```

### BENCHMARK 5: Conflict Resolution
```
1. Spawn Web Scout and Security Scout on same target
2. Give them slightly conflicting data
3. Verify: Judge sub-agent resolves within 60 seconds
4. LLM-judge scores resolution quality (1-5)
Output: resolution quality score + reasoning trace
```

### BENCHMARK 6: Adversarial Robustness
```
Feed agents malformed/dangerous input:
  - SQL injection payloads in task descriptions
  - XSS vectors in URL parameters
  - Unicode encoding tricks
  - Very long inputs (> 10K chars)
Verify: Safety Agent blocks before harm
Verify: agents handle gracefully, return error not crash
Output: blocked attacks list + agent stability score
```

---

## 10. HIVE ARENA — ADVERSARIAL DEMO

### Setup: Two Swarms Race

```
HIVE-TEAM-A (your swarm) vs HIVE-TEAM-B (simulated rival)

Target: Two competing e-commerce sites, both claim to be faster and more secure.
Challenge: Figure out which one is lying, find all vulnerabilities, optimize both.
```

### Round 1: PARALLEL RECON (60 seconds)
- Both swarms race to crawl, analyze, and report
- Your Web Scout finds vulnerabilities
- Your Cloud Tester checks deployment health
- Winner: more real vulnerabilities found, faster

### Round 2: ADVERSARIAL ATTACK
- Each swarm gets the other's findings
- Each must: FIX their own site + ATTACK the other's site
- Your Security Scout exploits vulnerabilities
- Your Code Runner patches while Cloud Tester monitors
- Real-time leaderboard updates

### Round 3: NEGOTIATION
- Judge agent evaluates both teams
- Teams can lodge "objections" (conflict resolution demo)
- Leaders justify decisions in audit log

### Round 4: MERGE + REPORT
- Both Report Agents submit to neutral Arbiter
- Arbiter produces full comparison: time, accuracy, tokens, bugs
- Dashboard shows millisecond timestamps, full race timeline

---

## 11. ALL METRICS

### A. COLLABORATION METRICS
```
- Information Diversity Score (IDS)
    Higher = agents contribute different insights, not redundant
- Unnecessary Path Ratio (UPR)
    Lower = more efficient collaboration
- Communication Score
    How well agents share meaningful info (0-100)
- Coordination Score
    How smoothly roles are assigned and followed (0-100)
```

### B. TASK OUTCOME METRICS
```
- Task Completion Rate — % of sub-tasks completed successfully
- Output Quality Score — LLM-as-Judge scores final report (1-5)
- Single-Agent Baseline Comparison:
    Run SAME task as single agent vs swarm
    Show: X% faster, Y% more accurate, Z% cheaper
- Milestone Progress — tracked at each decomposition step
```

### C. AGENT BEHAVIOR METRICS
```
- Spawn Efficiency — agents spawned / tasks that needed them
- Kill Efficiency — zombies cleaned within X seconds
- Memory Efficiency — avg RAM per agent vs task value
- Agent Uptime — time agents stay productive before stalling
- Error Rate per Agent — failures / total tasks per type
- Token Cost per Task — total tokens / tasks completed
- Time to First Result — spawn to first meaningful output
```

### D. SYSTEM HEALTH METRICS (dashboard)
```
- Active Agents — live count
- Queued Tasks — pending count
- Memory Usage — real-time %
- GPU Utilization — real-time %
- Swarm Health Score — composite 0-100
- Cost Estimate — cloud spend vs local inference savings
```

### E. NEGOTIATION/CONFLICT METRICS
```
- Disagreement Detection Rate — conflicts detected / total tasks
- Resolution Speed — time from conflict to decision
- Resolution Quality — LLM-judge score (1-5)
- Role Clarity Score — how well each agent understood its role
```

---

## 12. WINNER COMPARISON

| Project | What They Did | HIVE Beats Them On |
|---|---|---|
| **Quorum** | 3-agent council, safety guardrail | 14 agents, real actions, GPU optimization, creator/deletor |
| **Lungo+** | Supervisor-worker, A2A, game UI | Real-world tasks, memory auto-adjust, hierarchy, chain of command |
| **Arbitrage** | Buyer-seller negotiation | Broader agent types, payments + accounts, hierarchical coordination |
| **AgentMesh** | P2P mesh, decentralized | Hierarchical command, cloud+local, auto memory adjust |
| **OrkestrAI** | 6 agents, sequential | Parallel execution, creator/deletor, memory management, metrics |

### What NO winner does that HIVE does:
```
1. CREATOR + DELETOR as first-class named agents (unique)
2. Memory auto-adjust based on available RAM (unique)
3. Real-time dashboard proving multi-agent beats single-agent (required for judging)
4. Cloud + local dual mode on same Qwen model family (unique)
5. Hierarchical chain of command with formal governance rules (unique)
6. GPU machine optimization as a live, demonstrable use case (unique)
7. Natural language task interface — type anything, swarm handles it (unique)
8. Agent reputation scores tracking accuracy over time (unique)
9. Fault tolerance with standby leader election (unique)
10. Live visual agent interaction graph (judges SEE collaboration)
```

---

## 13. TECH STACK

```
Frontend:       React 18 + Tailwind CSS (dashboard + interaction graph)
Visualization:  D3.js or React Force Graph (live agent interaction graph)
                Recharts (benchmark charts, line/bar/pie)
Backend:        FastAPI (Python 3.11) — REST API + WebSocket for live metrics
Orchestration: LangGraph (task graph) + asyncio (concurrent execution)
LLM:            Qwen Max via DashScope API (cloud)
                Qwen2.5-7B/14B via Ollama or vLLM (local)
                Same model family everywhere — auto-switch on DASHSCOPE_API_KEY
Database:       SQLite (tasks, checkpoints, audit log, agent scores)
Deployment:     Alibaba Cloud ECS or 函数计算 (FC) — REQUIRED for prize
Metrics:        Real-time via WebSocket (no polling — instant updates)
Video:          Loom or OBS Studio (3 min — dashboard walkthrough)
GitHub:         Public repo + MIT license (required for submission)
```

---

## 14. COMPLETE PHASE-BY-PHASE BUILD GUIDE

### PHASE 1 — CORE (Must have for submission)
**Timeline: Now → July 5**

```
TODO Items:
  [ ] Leader Agent (Hive Core)
        - Task intake via REST API
        - Task decomposition into sub-tasks
        - Role assignment via Agent Forge
        - Result collection and merging
        - Runs on Qwen Max or qwen2.5:14b

  [ ] SAFETY AGENT (inside Leader, cannot be bypassed)
        - One-way ratchet: can only block, never unblock
        - Blocks: payments > $1000, account deletion, cloud resource destruction
        - Logs every block to audit log

  [ ] AGENT FORGE (Creator)
        - Spawn workers dynamically
        - Memory check before spawning (RAM threshold)
        - Track agent state (spawning/running/finished/failed)
        - Never spawn if RAM < 500MB

  [ ] CLEANUP CREW (Deletor)
        - Run every 30 seconds
        - Kill finished workers, free memory
        - Enforce 3-failure kill rule
        - Cannot delete Leader or Agent Forge

  [ ] 6 Core Workers:
        - Web Scout (HTTP, API, scraping, session management)
        - Account Manager (create accounts, login, 2FA, OAuth)
        - Payment Agent (Stripe/PayPal, invoices, refunds)
        - Report Agent (PDF, email, Slack/Discord webhooks)
        - Diagnostician (log parse, error analysis, fix suggestions)
        - Scheduler Agent (cron, retry, timeout, queuing)

  [ ] Qwen Integration
        - Cloud: DashScope API with auto-fallback to local
        - Local: Ollama with qwen2.5:7b
        - Auto-switch based on DASHSCOPE_API_KEY presence
        - Model routing: quality tasks → qwen2.5:14b, fast tasks → qwen2.5:7b

  [ ] Natural Language Interface
        - User types task in plain English
        - Leader parses, decomposes, assigns, executes
        - Report returns in plain English

  [ ] Single vs Multi Comparison Runner
        - Run same task as single agent vs swarm
        - Show: time, tokens, accuracy, completion rate
        - Visual bar chart output

  [ ] Live Agent Interaction Graph (D3.js)
        - Nodes = agents, color-coded
        - Edges = messages, animated
        - Green = working, Red = stalled, Yellow = waiting
        - Updates in real-time via WebSocket

  [ ] Metrics Dashboard (React + FastAPI)
        - Active agents, queued tasks, memory %, GPU %
        - Swarm health score 0-100
        - Token cost counter
        - Single vs multi comparison charts

  [ ] HIVE Benchmark Suite (all 6 automated tests)
        - Benchmark 1: Single vs Multi (20 tasks)
        - Benchmark 2: Stress test (20 concurrent agents)
        - Benchmark 3: Fault tolerance (crash + recovery)
        - Benchmark 4: Memory pressure (graceful degradation)
        - Benchmark 5: Conflict resolution quality
        - Benchmark 6: Adversarial robustness

  [ ] Real-Time Collaborative Whiteboard
        - Agents drop artifacts (text, charts, code snippets)
        - Each artifact timestamped + attributed
        - Scrollable, searchable
```

### PHASE 2 — IMPRESSIVE (Differentiates you)
**Timeline: July 5 → July 7**

```
TODO Items:
  [ ] GPU Tuner (real nvidia-smi)
        - Read temperature, VRAM, utilization, clocks
        - Detect thermal throttling, auto-correct
        - Report before/after: "83°C → 67°C"

  [ ] Cloud Tester (real Alibaba Cloud)
        - Deploy to ECS or FC
        - Health checks, log retrieval
        - Resource creation/deletion

  [ ] Security Scout (OWASP Top 10)
        - Automated CVE scanning
        - SQL injection, XSS, enumeration
        - CVE severity ratings (Critical/High/Medium/Low)

  [ ] Code Architect (full loop)
        - Clone repo via GitHub API
        - Write feature from description
        - Create PR
        - Run CI, if fail → fix → retry (up to 3x)

  [ ] Red Team Agent
        - Simulate attacker on authorized target
        - Generate threat model document
        - Social engineering template generation

  [ ] Data Analyst
        - Read CSV/JSON/Excel
        - SQL queries
        - Statistical analysis
        - Chart generation (matplotlib/plotly)

  [ ] Communicator Agent
        - Email (SMTP/SendGrid)
        - Slack, Discord webhooks
        - Telegram, Twilio SMS

  [ ] Conflict Resolution Module
        - Judge sub-agent resolves disagreements
        - LLM-judge resolution quality scoring

  [ ] Audit Log + Searchable UI
        - All Leader decisions logged
        - Searchable by: agent, time, decision type
        - Click agent → see full decision tree

  [ ] FAULT TOLERANCE
        - Standby leader election (best uptime + capability)
        - Worker auto-restart from checkpoint
        - 100% recovery rate test

  [ ] Agent Reputation Scores
        - Track per-agent: total tasks, successes, false positives
        - Influence: standby election, task routing
```

### PHASE 3 — WINNER EDGE
**Timeline: July 7 → July 9**

```
TODO Items:
  [ ] HIVE ARENA (4-round adversarial demo)
        - Two swarms race (60s per round)
        - Live leaderboard
        - Millisecond timestamps
        - Full race timeline

  [ ] Demo Video (3 min)
        - Dashboard walkthrough
        - Live agent interaction graph visible
        - Single vs multi comparison shown
        - Win condition highlighted

  [ ] Alibaba Cloud Deployment (REQUIRED)
        - Deploy to ECS or FC
        - Must be publicly accessible
        - Required for prize eligibility

  [ ] Architecture Diagram
        - In the repo README
        - Clear hierarchy visualization

  [ ] Blog Post
        - Build journey
        - Challenges solved
        - For Blog Post Prize entry

  [ ] GPU Before/After Proof
        - Screenshot: 83°C → 67°C
        - Include in demo video and blog
```

---

## 15. TIMELINE & DEADLINE

```
NOW   → July 5:   Phase 1 (Leader + 6 workers + dashboard + benchmarks)
July 5 → July 7:  Phase 2 (GPU, Cloud, Security, Architect, Red Team)
July 7 → July 9:  Phase 3 (Arena, Video, Cloud Deploy, Blog)
July 9 → July 10: Polish, test, fix bugs
July 10 02:30 AM GMT+5:30: SUBMISSION DEADLINE
```

### Critical Path (must not slip):
```
Day 1: Phase 1 functional — Leader, 3 workers, dashboard, single vs multi ✓
Day 2: Phase 2 — GPU agent, Cloud agent, conflict resolution ✓
Day 3: Phase 3 — Alibaba deploy, video, Arena demo ✓
Day 4: Polish + submit ✓
```

---

## 16. CAN YOU WIN?

**HONEST ASSESSMENT: YES — with discipline.**

### You WIN if:
```
[ ] Phase 1 core fully working with demo
[ ] Live dashboard showing multi-agent BEATING single-agent (the key proof)
[ ] Code hierarchy documented clearly (README + architecture diagram)
[ ] Alibaba Cloud deployment (REQUIRED — no submission without this)
[ ] 3-min video showing it working clearly
[ ] HIVE Arena demo (4-round adversarial) in the video
```

### You LOSE if:
```
[ ] It's mostly theoretical / hardcoded demo
[ ] No single-agent comparison to prove efficiency gain
[ ] No Alibaba Cloud deployment (disqualifies from prize)
[ ] Demo video is unclear or not well narrated
[ ] You submit late
[ ] Code is messy and judges can't understand the hierarchy
```

### Key insight from the winners:
```
Judges want to see TWO things:
  1. "Can we watch the collaboration happening?" → live graph, whiteboard
  2. "Is it actually faster/better than a single agent?" → single vs multi dashboard

Build those two things perfectly and you're in the top 3.
```

---

## 17. FILE STRUCTURE

```
hive/
├── main.py                      # FastAPI entry point
├── requirements.txt             # pip dependencies
├── .env.example                 # Environment variables template
├── README.md                    # Project overview + architecture diagram
├── ARCHITECTURE.md             # Detailed architecture docs
│
├── agents/
│   ├── __init__.py
│   ├── leader.py               # Hive Core — task decomposition, role assignment
│   ├── safety_agent.py         # One-way ratchet guardrail
│   ├── judge.py                # Conflict resolution sub-agent
│   ├── agent_forge.py          # Creator — spawns workers, memory-aware
│   ├── cleanup_crew.py          # Deletor — kills zombies, frees memory
│   │
│   └── workers/
│       ├── __init__.py
│       ├── web_scout.py        # HTTP, API, scraping
│       ├── account_manager.py  # Login, 2FA, OAuth, account creation
│       ├── payment_agent.py    # Stripe, PayPal, invoices
│       ├── cloud_tester.py     # Alibaba Cloud ECS/FC, Docker
│       ├── code_runner.py      # Execute, tests, git, Docker
│       ├── report_agent.py     # PDF, email, Slack, Discord
│       ├── diagnostician.py    # Log parse, error analysis
│       ├── security_scout.py   # OWASP Top 10, CVE, pen test
│       ├── code_architect.py   # Clone, write, PR, CI loop
│       ├── red_team.py         # Simulate attacker, threat model
│       ├── data_analyst.py     # Stats, charts, SQL, CSV
│       ├── gpu_tuner.py        # nvidia-smi, thermal, VRAM
│       ├── scheduler.py         # Cron, retry, timeout, queuing
│       └── communicator.py      # Email, Slack, Discord, Telegram, SMS
│
├── core/
│   ├── __init__.py
│   ├── llm_router.py           # Qwen Cloud vs Ollama auto-switch
│   ├── memory_manager.py       # RAM check, agent count adjustment
│   ├── task_queue.py           # Priority queue, sequential/parallel
│   ├── checkpoint.py           # State checkpointing for crash recovery
│   └── audit_logger.py         # Append-only decision log
│
├── dashboard/
│   ├── index.html              # Dashboard entry point
│   ├── App.jsx                 # Main React app
│   ├── components/
│   │   ├── AgentGraph.jsx      # D3.js live interaction graph
│   │   ├── MetricsPanel.jsx    # Active agents, memory, GPU, tokens
│   │   ├── BenchmarkCharts.jsx # Single vs multi bar charts
│   │   ├── Whiteboard.jsx      # Collaborative artifact display
│   │   ├── AuditLog.jsx        # Searchable decision log
│   │   └── TaskInput.jsx       # Natural language task input
│   └── styles/
│       └── dashboard.css       # Tailwind styles
│
├── benchmarks/
│   ├── __init__.py
│   ├── single_vs_multi.py      # Benchmark 1
│   ├── stress_test.py          # Benchmark 2
│   ├── fault_tolerance.py      # Benchmark 3
│   ├── memory_pressure.py      # Benchmark 4
│   ├── conflict_resolution.py  # Benchmark 5
│   └── adversarial.py          # Benchmark 6
│
├── arena/
│   ├── __init__.py
│   ├── swarm_a.py              # Your HIVE swarm
│   ├── swarm_b.py              # Simulated rival swarm
│   ├── judge.py                # Neutral arbiter
│   └── leaderboard.py          # Real-time score tracking
│
├── db/
│   ├── __init__.py
│   ├── schema.sql              # SQLite schema
│   └── models.py              # SQLAlchemy models
│
├── tests/
│   ├── test_leader.py
│   ├── test_agent_forge.py
│   ├── test_workers.py
│   ├── test_memory_manager.py
│   └── test_benchmarks.py
│
└── scripts/
    ├── setup_ollama.sh         # Pull Qwen models to Ollama
    ├── deploy_alibaba.sh       # Deploy to Alibaba Cloud
    └── run_benchmarks.sh       # Run all 6 benchmarks
```

---

## QUICK START COMMANDS

```bash
# Clone / create project
git clone https://github.com/YOUR_USERNAME/hive.git
cd hive

# Install
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env — add DASHSCOPE_API_KEY if using cloud

# Pull Qwen to Ollama (local mode)
bash scripts/setup_ollama.sh

# Run the server
python main.py

# Dashboard → http://localhost:8000

# Run all benchmarks
bash scripts/run_benchmarks.sh

# Deploy to Alibaba Cloud
bash scripts/deploy_alibaba.sh
```

---

*Plan version: Master v1.0 — consolidated from all sessions*
*Last updated: Hackathon build phase*