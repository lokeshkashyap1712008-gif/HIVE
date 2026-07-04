"""
HIVE — LLM Router
Auto-switches between Qwen Cloud (DashScope OpenAI-compatible) and local Ollama
All agents call llm_router.chat() — never call providers directly
"""

import logging
from typing import Optional

import httpx
from openai import OpenAI

from core.config import settings

logger = logging.getLogger(__name__)

# ─── DashScope Model Names ───────────────────────────────────────────────────
# Real DashScope model names — DO NOT use qwen3.7-plus (doesn't exist)
#
# Model selection strategy:
# - qwen-turbo: fastest, good for workers, pings, safety checks (100k tokens/sec)
# - qwen-plus:  medium quality, good for report, data analysis
# - qwen-max:   best quality, for leader decisions, judge, conflict resolution
# - qwen-coder: code-specific, for Code Architect
# - qwen-reasoner: advanced reasoning, for Judge and high-stakes debates
#
# Check available models: https://help.aliyun.com/article/2413498
QWEN_TURBO   = "qwen-turbo"       # fastest — workers, pings, safety
QWEN_PLUS    = "qwen-plus"       # medium — report, data analysis
QWEN_MAX     = "qwen-max"         # best quality — leader decisions
QWEN_CODER   = "qwen-coder"      # code — Code Architect
QWEN_REASON  = "qwen-reasoner"   # best reasoning — Judge, conflicts

# Default to qwen-max for the leader
DEFAULT_MODEL = QWEN_MAX

# ─── Cloud (DashScope OpenAI-compatible API) ─────────────────────────────────

def get_cloud_client() -> OpenAI:
    """Create OpenAI-compatible DashScope client."""
    return OpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )


async def chat_cloud(
    messages: list[dict],
    model: str = "qwen-plus",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    """Call Qwen via DashScope OpenAI-compatible API (async using httpx)."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    def _sync_call():
        client = get_cloud_client()
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    # Run synchronous OpenAI call in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        response = await loop.run_in_executor(pool, _sync_call)
    
    choice = response.choices[0]
    content = choice.message.content or ""
    
    return {
        "content": content,
        "model": model,
        "provider": "cloud",
        "tokens": response.usage.total_tokens if response.usage else 0,
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


# ─── Router (main entry point) ───────────────────────────────────────────────

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
        quality: True → use quality model for critical tasks (leader, judge)

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