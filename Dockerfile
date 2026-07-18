# HIVE on Alibaba Cloud SAS / ECS — Qwen Cloud (DashScope) backend
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HIVE_HOME=/data/hive \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt README.md LICENSE setup.py ./
COPY hive ./hive
COPY scripts ./scripts

RUN pip install --upgrade pip \
    && pip install -e . \
    && mkdir -p /data/hive \
    && chmod +x /app/scripts/docker_entrypoint.sh /app/scripts/bootstrap_alibaba_sas.sh \
    && cp /app/scripts/docker_entrypoint.sh /usr/local/bin/hive-entrypoint

VOLUME ["/data/hive"]

# Lightweight health/proof endpoint + optional CLI attach
EXPOSE 8080

ENTRYPOINT ["hive-entrypoint"]
CMD ["serve"]
