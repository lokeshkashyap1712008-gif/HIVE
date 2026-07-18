# Go-live runbook (account steps only)

Repo packaging for the hackathon is done. Finish these four account steps before **July 20, 2026 2:00pm PDT**.

## A. Qwen API key (~3 min)

1. Open https://home.qwencloud.com/api-keys
2. Create a **pay-as-you-go** key (`sk-...`)
3. On your machine or SAS instance:

```bash
cp .env.example .env
# paste DASHSCOPE_API_KEY=sk-...
python scripts/verify_qwen_key.py
```

## B. Alibaba SAS deploy (~15 min)

1. Console → Simple Application Server → Create (Docker image, ≥2 GB RAM)
2. Reset root password · firewall TCP **22** + **8080**
3. Workbench:

```bash
git clone https://github.com/lokeshkashyap1712008-gif/HIVE.git /opt/hive
cd /opt/hive
# after pushing latest: git pull
bash scripts/bootstrap_alibaba_sas.sh
# first run creates .env — set key — run script again
```

4. Screenshot Workbench + `curl http://<PUBLIC_IP>:8080/health`

## C. Demo video (~20 min)

**Fast path (upload tonight):** upload [`docs/demo-preview.mp4`](demo-preview.mp4) to YouTube as **Public**, then record a better live cut when SAS is up.

**Best path:** follow [`DEMO_VIDEO.md`](DEMO_VIDEO.md) with Workbench + live `python -m hive`, using [`demo-slides.html`](demo-slides.html) for the intro.

## D. Devpost submit (~10 min)

1. https://qwencloud-hackathon.devpost.com/ → Join → Create project
2. Copy fields from `docs/SUBMISSION.md`
3. Track: **Agent Society**
4. Code proof: `https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/llm.py`
5. Upload `docs/architecture.png`
6. Submit before the deadline
