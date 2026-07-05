"""
HIVE — Configuration
All settings via environment variables + .env file
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuration loaded from environment variables."""

    # LLM — Cloud (DashScope)
    DASHSCOPE_API_KEY: str = os.environ.get("DASHSCOPE_API_KEY", "")

    # LLM — Local (Ollama)
    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    OLLAMA_LARGE_MODEL: str = os.environ.get("OLLAMA_LARGE_MODEL", "qwen2.5:14b")

    # System
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    MAX_CONCURRENT_AGENTS: int = int(os.environ.get("MAX_CONCURRENT_AGENTS", "8"))
    MEMORY_THRESHOLD_MB: int = int(os.environ.get("MEMORY_THRESHOLD_MB", "2048"))
    MIN_MEMORY_MB: int = int(os.environ.get("MIN_MEMORY_MB", "500"))
    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "auto")

    # Integrations
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
    STRIPE_API_KEY: str = os.environ.get("STRIPE_API_KEY", "")
    SENDGRID_API_KEY: str = os.environ.get("SENDGRID_API_KEY", "")

    @property
    def llm_provider(self) -> str:
        return (self.LLM_PROVIDER or "auto").strip().lower()

    @property
    def uses_cloud(self) -> bool:
        provider = self.llm_provider
        if provider == "cloud":
            return True
        if provider == "local":
            return False
        return bool(self.DASHSCOPE_API_KEY and self.DASHSCOPE_API_KEY.strip())

    @property
    def uses_local(self) -> bool:
        return not self.uses_cloud


settings = Settings()
