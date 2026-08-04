from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PipeGuard API"
    app_env: str = "development"
    database_url: str = "sqlite:///./pipeguard.db"
    null_rate_threshold: float = 0.05
    duplicate_rate_threshold: float = 0.01
    freshness_hours_threshold: float = 24.0
    row_count_drop_threshold: float = 0.30
    row_count_history_size: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
