# HIVE — Autonomous Hierarchical Agent Swarm

> **Track 3: Agent Society** | Qwen Cloud Hackathon 2026
> A leader-led multi-agent system where specialized agents coordinate, self-spawn, self-cleanup, and adapt to available memory.

## Architecture

```
HiveCore (Leader)
├── Safety Agent ────── one-way ratchet, blocks dangerous actions
├── Agent Forge ─────── spawns workers, memory-aware
├── Cleanup Crew ─────── kills zombies, enforces 3-failure kill rule
└── Worker Pool ─────── 14 specialized agents (stateless)
    └── Web Scout | Account Manager | Payment Agent | Cloud Tester
        Code Runner | Report Agent | Diagnostician | Security Scout
        Code Architect | Red Team Agent | Data Analyst | GPU Tuner
        Scheduler Agent | Communicator Agent
```

## Features

- **Cloud + Local**: Qwen everywhere — auto-switches between DashScope and Ollama
- **Memory auto-adjust**: Spawns fewer agents when RAM is low (2048MB / 1024MB / 500MB thresholds)
- **3-failure kill rule**: Workers that fail 3 times are automatically terminated
- **One-way Safety ratchet**: Safety Agent can block anything, never unblocks
- **Audit log**: Every Leader decision is logged in SQLite with reason + timestamp
- **6 automated benchmarks**: Prove swarm quality vs single agent
- **Live dashboard**: Real-time agent graph, task queue, memory/GPU metrics

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/lokeshkashyap1712008-gif/HIVE.git
cd HIVE
pip install -r requirements.txt

# 2. Configure (cloud = Qwen, local = Ollama fallback)
cp .env.example .env
# Add DASHSCOPE_API_KEY to .env for Qwen Cloud mode

# 3. Pull Qwen to Ollama (local mode only)
ollama pull qwen2.5:7b

# 4. Run
python main.py
# Dashboard → http://localhost:8000
```

## Demo

```bash
# Submit a natural language task
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Scan https://example.com for security vulnerabilities and generate a report", "mode": "swarm"}'

# Run benchmarks
curl -X POST http://localhost:8000/api/benchmark/single_vs_multi
curl -X POST http://localhost:8000/api/benchmark/adversarial
curl -X POST http://localhost:8000/api/benchmark/fault_tolerance
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + LangGraph |
| LLM | Qwen Max (DashScope) / Qwen2.5 (Ollama) |
| Database | SQLite |
| Agents | 14 specialized workers |
| Cloud | Alibaba Cloud ECS + Function Compute |

## License

MIT