# Demo Video Script — HIVE (≈3 minutes)

Upload the final cut as a **public** video on YouTube, Vimeo, or Facebook Video. Paste the URL into Devpost.

**Target length:** 2:30–3:00 (hackathon asks ~3 minutes).

---

## What to show on screen

Keep two windows ready before recording:

1. **Alibaba Workbench** — SAS instance with `docker compose ps` / `curl localhost:8080/health`
2. **HIVE CLI** — `python -m hive` (on the same instance or local with the same DashScope key)
3. Optional slide deck for recording intros: open `docs/demo-slides.html` in a browser (arrow keys to advance).

---

## Shot list / narration

### 0:00–0:20 — Hook + track

> “HIVE is an agent operating system. Instead of one chatbot, AI agents form temporary **societies** to solve hard goals. We’re submitting to the **Agent Society** track, powered by **Qwen Cloud** on **Alibaba Cloud**.”

Show: README title + architecture SVG.

### 0:20–0:50 — Architecture

> “The user talks to HIVE Core running on Alibaba Simple Application Server. Agents collaborate over a message bus with credits and reputation. Every LLM call goes to Qwen via DashScope — here’s `hive/llm.py` calling `dashscope-intl.aliyuncs.com`.”

Show: architecture diagram → scroll `hive/llm.py` on GitHub.

### 0:50–1:20 — Proof of Alibaba deployment

> “Here’s our SAS Workbench. Docker Compose is up. Hitting the public health endpoint shows Alibaba compute with Qwen Cloud configured.”

Show:

```bash
docker compose ps
curl http://127.0.0.1:8080/health
# or browser: http://<PUBLIC_IP>:8080/health
```

### 1:20–2:40 — Live society run

Run a short goal, e.g.:

```text
Plan a secure approach to scrape public competitor pricing pages and summarize risks.
```

Narrate while agents spawn / debate / respond:

> “HiveCore allocates credits. Security and Architect debate. The judge returns a verdict with confidence — that’s the society, not a single prompt.”

### 2:40–3:00 — Close

> “HIVE: temporary agent societies, debate, economy, reputation — all on Qwen Cloud. Repo: github.com/lokeshkashyap1712008-gif/HIVE. Thanks.”

Show: repo URL + `/health` JSON one more time.

---

## Recording tips

- 1080p, clear terminal font, hide API keys (blur `.env`)
- Prefer Workbench + CLI over slides-only
- Make the YouTube/Vimeo video **Public** (or Unlisted only if Devpost accepts it — Public is safer)

## After upload

1. Copy the public URL into [docs/SUBMISSION.md](SUBMISSION.md) → Video field
2. Paste the same URL into Devpost
