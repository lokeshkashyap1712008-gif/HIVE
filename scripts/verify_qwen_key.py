#!/usr/bin/env python3
"""Verify DASHSCOPE_API_KEY works against Qwen Cloud (DashScope).

Usage:
  export DASHSCOPE_API_KEY=sk-...
  python scripts/verify_qwen_key.py
"""

from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> int:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key or key.startswith("your_"):
        print("ERROR: Set DASHSCOPE_API_KEY to a pay-as-you-go key (sk-...).")
        print("Create one at: https://home.qwencloud.com/api-keys")
        return 1

    if key.startswith("sk-sp-"):
        print("ERROR: Token Plan keys (sk-sp-...) are not for backend scripts.")
        print("Use a pay-as-you-go key (sk-...) with dashscope-intl.aliyuncs.com.")
        return 1

    model = os.environ.get("QWEN_MODEL", "qwen3.7-plus")
    client = OpenAI(
        api_key=key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    print(f"Calling Qwen Cloud model={model} ...")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: HIVE_OK"}],
        max_tokens=16,
    )
    text = (completion.choices[0].message.content or "").strip()
    print(f"Response: {text}")
    if "HIVE_OK" in text.upper() or text:
        print("SUCCESS: DASHSCOPE_API_KEY is valid for Alibaba Qwen Cloud.")
        return 0
    print("WARNING: Unexpected empty response.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
