"""
Central configuration for the Lead Pipeline Orchestrator.
All secrets loaded from .env file via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "LeadPipeline"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://pipeline:pipeline@localhost:5432/leadpipeline"
    REDIS_URL: str = "redis://localhost:6379"
def get_settings() -> Settings:
    return Settings()
