"""
HIVE — LLM Router
Auto-switches between Qwen Cloud (DashScope) and local Ollama
All agents call llm_router.chat() — never call providers directly
"""

import logging
from typing import Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# ─── DashScope Model Names (your available models) ──────────────────────────
#
# Use these when calling chat(..., model=XXX)
# Default is QWEN_MAX for quality, QWEN_TURBO for speed
#
QWEN_TURBO   = "qwen-flash-2025-07-28"        # fastest — workers, pings, safety
QWEN_PLUS    = "qwen-plus-latest"              # medium — report, data analysis
QWEN_MAX     = "qwen-max"                      # best quality — leader decisions
QWEN_CODER   = "qwen3-coder-plus-2025-07-22"   # code — Code Architect
QWEN_REASON  = "qwen3-max-2025-09-23"          # best reasoning — Judge, conflicts
QWEN_VISION  = "qwen-vl-plus-2025-08-15"        # vision + text


# ─── Cloud (DashScope) ───────────────────────────────────────────────────────

async def chat_cloud(
    messages: list[dict],
    model: str = "qwen-max",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    """Call Qwen via DashScope API."""
    try:
        import dashscope
    except ImportError:
        raise RuntimeError("dashscope not installed. Run: pip install dashscope")

    dashscope.api_key = settings.DASHSCOPE_API_KEY

    response = dashscope.MultiModalConversation.call(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if response.status_code != 200:
        raise RuntimeError(f"DashScope error {response.status_code}: {getattr(response, 'message', response)}")

    msg = response.output.choices[0].message
    return {
        "content": msg.get("content", "") if hasattr(msg, "get") else str(msg),
        "model": model,
        "provider": "cloud",
        "tokens": getattr(response.usage, "total_tokens", 0) if hasattr(response, "usage") else 0,
    }


# ─── Local (Ollama) ─────────────────────────────────────────────────────────

async def chat_local(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    """Call Qwen via local Ollama."""
    model = model or settings.OLLAMA_MODEL

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            raise RuntimeError(f"Ollama timed out for model '{model}' after 30s. Try qwen2.5:7b instead.")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama HTTP error {e.response.status_code}: {e.response.text[:200]}")

    return {
        "content": data["message"]["content"],
        "model": model,
        "provider": "local",
        "tokens": data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
    }


# ─── Router (main entry point) ──────────────────────────────────────────────

async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    quality: bool = False,
) -> dict:
    """
    Main entry point for ALL LLM calls.

    Args:
        messages: [{"role": "user", "content": "..."}]
        model: Override model name (use QWEN_* constants above)
        temperature: 0.0=deterministic, 0.7=balanced, 1.0=creative
        max_tokens: Max tokens to generate
        quality: True → use QWEN_MAX ("qwen-max") for quality tasks

    Returns:
        {"content": str, "model": str, "provider": "cloud"|"local", "tokens": int}
    """
    if settings.uses_cloud:
        selected = model or (QWEN_MAX if quality else QWEN_TURBO)
        logger.debug(f"[LLM] → DashScope ({selected})")
        return await chat_cloud(messages, model=selected, temperature=temperature, max_tokens=max_tokens)
    else:
        local_model = model or settings.OLLAMA_MODEL
        logger.debug(f"[LLM] → Ollama ({local_model})")
        return await chat_local(messages, model=local_model, temperature=temperature, max_tokens=max_tokens)


async def initialize() -> bool:
    """Called at startup to verify LLM connectivity. Returns True if successful."""
    test_messages = [{"role": "user", "content": "Reply with just the word OK."}]
    try:
        result = await chat(test_messages, model=QWEN_TURBO, max_tokens=10)
        logger.info(f"LLM ready: provider={result['provider']}, model={result['model']}")
        return True
    except Exception as e:
        logger.warning(f"LLM init failed: {e}. Will retry on first call.")
        return False