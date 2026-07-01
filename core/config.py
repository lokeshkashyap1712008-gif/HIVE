"""
HIVE — Configuration
All settings via environment variables + .env file
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # LLM — Cloud (DashScope)
    DASHSCOPE_API_KEY: Optional[str] = None

    # LLM — Local (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_LARGE_MODEL: str = "qwen2.5:14b"

    # System
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    MAX_CONCURRENT_AGENTS: int = 8
    MEMORY_THRESHOLD_MB: int = 2048  # below this: reduce agents
    MIN_MEMORY_MB: int = 500         # below this: run one at a time
    LLM_PROVIDER: str = "auto"      # "cloud", "local", or "auto"

    # Integrations
    GITHUB_TOKEN: Optional[str] = None
    STRIPE_API_KEY: Optional[str] = None
    SENDGRID_API_KEY: Optional[str] = None

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