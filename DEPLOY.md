# Deploy HIVE on Alibaba Cloud + Qwen Cloud

HIVE’s brain is **Qwen Cloud (DashScope)** on Alibaba Cloud. This guide runs the HIVE backend on **Alibaba Simple Application Server (SAS)** so judges can see compute + API proof.

**Hackathon deadline:** July 20, 2026 @ 2:00pm PDT — [Devpost](https://qwencloud-hackathon.devpost.com/)

**Track:** Agent Society

---

## 1. Get a Qwen Cloud API key

1. Sign up at [qwencloud.com](https://qwencloud.com)
2. Create a **pay-as-you-go** key at [home.qwencloud.com/api-keys](https://home.qwencloud.com/api-keys) (`sk-...`, **not** Token Plan `sk-sp-...`)
3. Locally:

```bash
cp .env.example .env
# Edit .env — set DASHSCOPE_API_KEY=sk-...
export $(grep -v '^#' .env | xargs)
python scripts/verify_qwen_key.py
```

---

## 2. Proof of Alibaba Cloud APIs (required for Devpost)

Submit this public file link:

**https://github.com/lokeshkashyap1712008-gif/HIVE/blob/main/hive/llm.py**

That module calls DashScope’s OpenAI-compatible endpoint:

- Base URL: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Env: `DASHSCOPE_API_KEY`
- Default model: `qwen3.7-plus`

Config mirror: [`hive/config.py`](hive/config.py)

---

## 3. Create Alibaba Simple Application Server (SAS)

Recommended for LLM-API agents (no local GPU needed).

1. Open **Alibaba Cloud Console** → **Simple Application Server** → **Create Server**
2. Region: any international region you prefer
3. Image: **Docker** application image
4. Plan: **≥ 2 GB RAM** (4 GB if you use browser tools)
5. After create: **Reset root password**
6. Firewall: allow **TCP 22** (SSH) and **TCP 8080** (HIVE health/proof endpoint)
7. Connect with **Workbench** (console → Connect) — screenshot this for runtime proof

### ECS alternative

Same steps on ECS (Ubuntu 22.04/24.04): install Docker, open security-group ports 22 + 8080, then follow section 4.

---

## 4. Deploy HIVE on the instance

### Option A — Docker Compose (recommended)

```bash
git clone https://github.com/lokeshkashyap1712008-gif/HIVE.git /opt/hive
cd /opt/hive
cp .env.example .env
nano .env   # set DASHSCOPE_API_KEY=sk-...

docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/health
```

From your laptop (replace with the instance public IP):

```bash
curl http://<PUBLIC_IP>:8080/health
```

### Option B — Bare metal + systemd

```bash
sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv git
git clone https://github.com/lokeshkashyap1712008-gif/HIVE.git /opt/hive
cd /opt/hive
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env && nano .env   # DASHSCOPE_API_KEY

sudo tee /etc/systemd/system/hive.service << 'EOF'
[Unit]
Description=HIVE Agent OS (Qwen Cloud)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/hive
EnvironmentFile=/opt/hive/.env
Environment=HIVE_HOME=/var/lib/hive
ExecStart=/opt/hive/venv/bin/python -m hive.deploy_server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo mkdir -p /var/lib/hive
sudo systemctl daemon-reload
sudo systemctl enable --now hive
sudo systemctl status hive
curl http://127.0.0.1:8080/health
```

### Interactive CLI on the same box (demo)

```bash
cd /opt/hive && source venv/bin/activate   # or: docker compose exec hive hive-entrypoint cli
python -m hive
```

---

## 5. Screenshots for Devpost

1. **Workbench Overview** with HIVE running (`docker compose ps` or `systemctl status hive`)
2. Browser or `curl` showing `http://<public-ip>:8080/health` JSON (`cloud: Alibaba Cloud`, `llm.provider: Qwen Cloud / DashScope`)

---

## 6. Architecture

See [docs/architecture.svg](docs/architecture.svg) and the diagram embedded in [README.md](README.md).

```
User (CLI / TUI)
    → HIVE Core on Alibaba SAS/ECS (:8080 health + agent runtime)
        → SQLite (~/.hive or /data/hive)
        → Worker agents (forge, debate, scouts, …)
        → Qwen Cloud DashScope API (dashscope-intl.aliyuncs.com)
```

---

## 7. Local quick start (no cloud VM)

```bash
pip install -e .
cp .env.example .env   # set DASHSCOPE_API_KEY
python -m hive
# optional proof server:
python -m hive.deploy_server
```
