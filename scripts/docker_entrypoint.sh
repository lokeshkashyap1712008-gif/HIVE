#!/bin/sh
set -e

MODE="${1:-serve}"

if [ -z "$DASHSCOPE_API_KEY" ] || [ "$DASHSCOPE_API_KEY" = "your_dashscope_key_here" ]; then
  echo "ERROR: DASHSCOPE_API_KEY is required (pay-as-you-go sk-...)."
  echo "Get a key: https://home.qwencloud.com/api-keys"
  exit 1
fi

mkdir -p "${HIVE_HOME:-/data/hive}"

case "$MODE" in
  serve)
    exec python -m hive.deploy_server
    ;;
  cli)
    shift
    exec python -m hive "$@"
    ;;
  verify)
    exec python /app/scripts/verify_qwen_key.py
    ;;
  *)
    exec "$@"
    ;;
esac
