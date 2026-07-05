"""
HIVE — LLM Router
Wraps hive.llm.QwenClient for use by core/agent modules.
All agents call llm_router.chat() — never call providers directly
"""

import logging
from typing import Optional

from hive.llm import QwenClient
from hive.core.config import settings

logger = logging.getLogger(__name__)

# ─── Model Names ─────────────────────────────────────────────────────────────
QWEN_TURBO = "qwen-max"
QWEN_PLUS = "qwen-max"
QWEN_MAX = "qwen-max"
QWEN_CODER = "qwen-max"
QWEN_REASON = "qwen-max"

DEFAULT_MODEL = QWEN_MAX

# Singleton client
_client: Optional[QwenClient] = None


def _get_client() -> QwenClient:
    global _client
    if _client is None:
        _client = QwenClient(api_key=settings.DASHSCOPE_API_KEY, model=QWEN_MAX)
    return _client


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    quality: bool = False,
) -> dict:
    """
    Main entry point for ALL LLM calls.

    Returns:
        {"content": str, "model": str, "provider": "cloud", "tokens": int}
    """
    client = _get_client()
    selected_model = model or (QWEN_MAX if quality else QWEN_TURBO)

    try:
        result = await client.chat(messages)
        content = client.extract_response(result)
        tokens = result.get("usage", {}).get("total_tokens", 0) if isinstance(result.get("usage"), dict) else 0

        return {
            "content": content,
            "model": selected_model,
            "provider": "cloud",
            "tokens": tokens,
        }
    except Exception as e:
        logger.error(f"[LLM] Chat failed: {e}")
        raise


async def initialize() -> bool:
    """Called at startup to verify LLM connectivity."""
    test_messages = [{"role": "user", "content": "Reply with just the word OK."}]
    try:
        result = await chat(test_messages, model=QWEN_TURBO, max_tokens=10)
        logger.info(f"LLM ready: provider={result['provider']}, model={result['model']}")
        return True
    except Exception as e:
        logger.warning(f"LLM init failed: {e}. Will retry on first call.")
        return False
