"""Application settings, loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    llm_api_keys: str = ""
    llm_model: str = "gemini/gemini-2.5-flash"
    llm_models: str = ""
    database_url: str = "sqlite:////data/app.db"
    allowed_origins: str = "http://localhost:3000"
    enable_failure_simulation: bool = False
    default_system_prompt: str = "You are a helpful, concise AI assistant."
    cache_enabled: bool = True
    cache_type: str = "local"  # "local" (in-memory) or "disk"
    cache_ttl_seconds: int = 3600
    cache_disk_dir: str = "/data/litellm_cache"
    llm_timeout_seconds: float = 30.0

    @property
    def api_keys(self) -> list[str]:
        return [k.strip() for k in self.llm_api_keys.split(",") if k.strip()]

    @property
    def per_key_models(self) -> list[str]:
        """Model for each key, in key order (LLM_MODELS overrides LLM_MODEL)."""
        keys = self.api_keys
        overrides = [m.strip() for m in self.llm_models.split(",") if m.strip()]
        if overrides:
            if len(overrides) == 1:
                return overrides * len(keys)
            if len(overrides) != len(keys):
                raise ValueError("LLM_MODELS must list one model per key in LLM_API_KEYS")
            return overrides
        return [self.llm_model] * len(keys)

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]
