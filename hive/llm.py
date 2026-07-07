"""LLM client — Qwen via DashScope (OpenAI-compatible SDK)."""

import json
from openai import AsyncOpenAI
from hive.config import DASHSCOPE_API_KEY, QWEN_MODEL, QWEN_BASE_URL


class QwenClient:
    """Async Qwen API client using OpenAI SDK."""

    def __init__(self, api_key: str = DASHSCOPE_API_KEY,
                 model: str = QWEN_MODEL):
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=QWEN_BASE_URL,
        )

    async def chat(self, messages: list[dict],
                   tools: list[dict] | None = None,
                   tool_choice: str | dict = "auto",
                   temperature: float | None = None,
                   max_tokens: int | None = None) -> dict:
        """Send chat completion request."""
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        resp = await self.client.chat.completions.create(**kwargs)
        return resp.model_dump()

    async def stream(self, messages: list[dict],
                     tools: list[dict] | None = None,
                     tool_choice: str | dict = "auto"):
        """Stream chat completion. Yields parsed chunks."""
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            yield chunk.model_dump()

    def extract_response(self, result: dict) -> str:
        """Extract text content from chat response."""
        try:
            return result["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            return ""

    def extract_tool_calls(self, result: dict) -> list[dict]:
        """Extract tool calls from chat response."""
        try:
            return result["choices"][0]["message"].get("tool_calls") or []
        except (KeyError, IndexError):
            return []

    def build_tools_schema(self, tools: dict) -> list[dict]:
        """Convert tool registry to OpenAI function calling schema."""
        schema = []
        for name, spec in tools.items():
            # Determine which params are required vs optional
            required_params = []
            properties = {}
            for param_name, param_spec in spec["parameters"].items():
                properties[param_name] = {
                    "type": param_spec["type"],
                    "description": param_spec["description"],
                }
                # Mark first param (usually "query" or "path") as required
                # Everything else is optional
                if param_name == "query" or param_name == "path" or param_name == "command" or param_name == "url":
                    required_params.append(param_name)

            schema.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params,
                    },
                },
            })
        return schema
