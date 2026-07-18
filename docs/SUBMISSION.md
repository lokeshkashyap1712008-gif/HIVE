# Devpost Submission Package — HIVE

Fill these fields on [Qwen Cloud Hackathon Devpost](https://qwencloud-hackathon.devpost.com/).  
**Deadline:** July 20, 2026 @ 2:00pm PDT.

---

## Track

**Agent Society**

---

## Project name

HIVE — Agent Operating System

---

## Tagline (one line)

AI agents form temporary societies — debate, economy, and reputation — powered by Qwen Cloud on Alibaba Cloud.

---

## Repository URL

https://github.com/lokeshkashyap1712008-gif/HIVE

- License: **MIT** ([LICENSE](../LICENSE)) — must show in GitHub About
- Deploy guide: [DEPLOY.md](../DEPLOY.md)

---

## Proof of Alibaba Cloud Deployment (code file link)

https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/llm.py

Supporting config: https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/config.py

Runtime health server (SAS/ECS): https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/deploy_server.py

Also attach Workbench screenshot(s) showing HIVE running and `GET /health` on port 8080.

---

## Architecture diagram

Upload [docs/architecture.png](architecture.png) to Devpost (also available as [architecture.svg](architecture.svg)).  
Same diagram is linked from the README.

---

## Demo video URL

Upload [`demo-preview.mp4`](demo-preview.mp4) (or your live recording) to YouTube/Vimeo/Facebook as **Public**, then paste the URL here and on Devpost.

See [DEMO_VIDEO.md](DEMO_VIDEO.md) for the live-demo shot list.

```
VIDEO_URL_HERE
```

---

## Text description (paste into Devpost)

### What it does

HIVE is an agent operating system where AI agents form **temporary hierarchical societies** to solve complex goals. A leader (HiveCore) allocates a credit budget, forges specialist workers, runs a structured multi-round debate when stakes are high, tracks reputation, and tears the society down when the job is done.

All intelligence runs through **Qwen Cloud (DashScope)** on Alibaba Cloud. The backend is designed to run on **Alibaba SAS/ECS** with a public `/health` proof endpoint.

### Features

- **Dynamic agent society** — spawn specialists via Agent Forge; retire them via Cleanup Crew
- **4-round debate protocol** — proposer, skeptic, architect, guardian → judge verdict
- **Credit economy** — finite budget forces better resource allocation
- **Reputation & confidence** — accuracy and confidence shape trust and next steps
- **Browser & tool workers** — web, security, code, reports, and more
- **Qwen Cloud first** — OpenAI-compatible DashScope client in `hive/llm.py`
- **Alibaba deploy** — Docker Compose + `hive.deploy_server` on port 8080

### How we built it

Python agent runtime + SQLite persistence + Ink/React terminal UI option. LLM routing targets `dashscope-intl.aliyuncs.com/compatible-mode/v1` with models such as `qwen3.7-plus`. Deployment uses Alibaba Simple Application Server with Docker.

### What’s next

Richer live society dashboard, stronger memory across sessions, and tighter MCP skill packs on Qwen Cloud.

---

## Optional — Blog / social post (Blog Post Prize)

Publish a short build journey (Medium, X, LinkedIn, or personal blog) covering:

1. Why agent societies beat single agents
2. Wiring HIVE to Qwen Cloud / DashScope
3. Deploying on Alibaba SAS + Workbench proof

Paste that public URL into the optional Devpost field.

---

## Pre-submit checklist

- [ ] Repo is **public**
- [ ] **LICENSE** visible in GitHub About (MIT)
- [ ] `DASHSCOPE_API_KEY` set on the Alibaba instance (not committed)
- [ ] `curl http://<PUBLIC_IP>:8080/health` returns JSON
- [ ] Code proof link points at `hive/llm.py`
- [ ] Architecture diagram uploaded
- [ ] Demo video public + URL pasted above and on Devpost
- [ ] Track set to **Agent Society**
- [ ] Submitted before **July 20, 2026 2:00pm PDT**
