#!/usr/bin/env bash
# Bootstrap HIVE on a fresh Alibaba SAS/ECS host (Ubuntu + Docker).
# Run as root or a user in the docker group.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/lokeshkashyap1712008-gif/HIVE.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/hive}"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — edit DASHSCOPE_API_KEY before continuing:"
  echo "  nano $INSTALL_DIR/.env"
  exit 1
fi

if grep -q 'your_dashscope_key_here' .env || ! grep -q '^DASHSCOPE_API_KEY=sk-' .env; then
  echo "ERROR: Set a real pay-as-you-go DASHSCOPE_API_KEY (sk-...) in .env"
  exit 1
fi

docker compose up -d --build
sleep 2
curl -fsS "http://127.0.0.1:8080/health" | tee /tmp/hive-health.json
echo
echo "HIVE is up. Open firewall TCP 8080 and visit http://<PUBLIC_IP>:8080/health"
echo "Screenshot Workbench + this health JSON for Devpost proof."
