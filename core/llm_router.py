"""
HIVE — LLM Router
Auto-switches between Qwen Cloud (DashScope) and local Ollama
All agents call llm_router.chat() — never call providers directly
"""

import os
import logging
from typing import Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# ─── Cloud ──────────────────────────────────────────────────────────────────

async def chat_cloud(
    messages: list[dict],
    model: str = "qwen-max",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    """Call Qwen Max via DashScope API."""
    import dashscope
    dashscope.api_key = settings.DASHSCOPE_API_KEY

    response = dashscope.MultiModelConversational.call(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        result_format="message",
    )

    if response.status_code != 200:
        raise RuntimeError(f"DashScope error {response.status_code}: {response.message}")

    msg = response.output.choices[0].message
    return {
        "content": msg.content,
        "model": model,
        "provider": "cloud",
        "tokens": getattr(response.usage, "total_tokens", 0),
    }


# ─── Local (Ollama) ──────────────────────────────────────────────────────────

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
            raise RuntimeError(f"Ollama timed out for model '{model}' after 30s. Try a lighter model (qwen2.5:7b) or increase timeout.")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama HTTP error {e.response.status_code}: {e.response.text[:200]}")

    return {
        "content": data["message"]["content"],
        "model": model,
        "provider": "local",
        "tokens": data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
    }


# ─── Router ─────────────────────────────────────────────────────────────────

async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    quality_mode: bool = False,
) -> dict:
    """
    Main entry point for ALL LLM calls.
    Auto-selects cloud vs local based on DASHSCOPE_API_KEY presence.
    
    Args:
        messages: OpenAI-style message list [{"role": "user", "content": "..."}]
        model: Override model name (default: auto based on quality_mode)
        temperature: 0.0 = deterministic, 0.7 = balanced, 1.0 = creative
        max_tokens: Max tokens to generate
        quality_mode: True = use larger/better model for critical tasks
    """
    if settings.uses_cloud:
        cloud_model = "qwen-max"
        if quality_mode:
            cloud_model = "qwen-long"  # better for complex reasoning
        logger.debug(f"[LLM] → DashScope ({cloud_model})")
        return await chat_cloud(messages, model=cloud_model, temperature=temperature, max_tokens=max_tokens)
    else:
        local_model = settings.OLLAMA_LARGE_MODEL if quality_mode else settings.OLLAMA_MODEL
        logger.debug(f"[LLM] → Ollama ({local_model})")
        return await chat_local(messages, model=local_model, temperature=temperature, max_tokens=max_tokens)


async def initialize():
    """Called at startup to verify LLM connectivity."""
    test_messages = [{"role": "user", "content": "Reply with just the word OK."}]
    try:
        result = await chat(test_messages, max_tokens=10)
        logger.info(f"LLM initialized: provider={result['provider']}, model={result['model']}")
    except Exception as e:
        logger.warning(f"LLM initialization failed: {e}. Will retry on first call.")


# ─── Per-agent model hints ───────────────────────────────────────────────────
# Use these via quality_mode=True for critical agents (Leader, Safety, Judge)

QUALITY_MODELS = {"leader", "safety", "judge"}
FAST_MODELS = {"web_scout", "report_agent", "diagnostician", "communicator"}