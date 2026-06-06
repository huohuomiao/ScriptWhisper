from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI 小说转剧本工具"
    ai_api_key: str | None = Field(default=None, validation_alias="AI_API_KEY")
    ai_api_base_url: str | None = Field(default=None, validation_alias="AI_API_BASE_URL")
    ai_model: str | None = Field(default=None, validation_alias="AI_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
