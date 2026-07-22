from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Auth ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 60 * 24  # 1 day

    # --- Database ---
    database_url: str = "sqlite:///./chatbot.db"

    # --- LLM provider (OpenAI-compatible: OpenRouter, OpenAI, local, ...) ---
    # OpenRouter:  https://openrouter.ai/api/v1
    # OpenAI:      https://api.openai.com/v1
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-4o-mini"
    llm_timeout_s: float = 60.0

    # --- OpenAI (optional, only needed if using OpenAI Files API for file storage) ---
    openai_api_key: str = ""

    # --- Supabase Storage (free alternative to OpenAI Files for file uploads) ---
    supabase_url: str = ""           # e.g. https://xxxx.supabase.co
    supabase_service_key: str = ""   # service_role key from Supabase dashboard → API

    # --- CORS ---
    cors_origins: str = "http://localhost:5173"

    @property
    def effective_openai_api_key(self) -> str:
        return self.openai_api_key or self.llm_api_key

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]



@lru_cache
def get_settings() -> Settings:
    return Settings()
