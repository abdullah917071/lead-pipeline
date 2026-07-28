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
    DATABASE_URL: str = "postgresql+asyncpg://pipeline:pipeline@postgres:5432/leadpipeline"
    REDIS_URL: str = "redis://:pipeline@redis:6379/0"

    # Dograh Voice AI
    DOGRAH_API_URL: str = "http://dograh:8000"
    DOGRAH_API_KEY: str = ""
    DOGRAH_TRIGGER_PATH: str = "suppremo-onboarding"
    DOGRAH_TELEPHONY_CONFIG_ID: int = 1
    DOGRAH_WORKFLOW_ID: int = 1
    # Dograh's own postgres (for mid-call polling of gathered_context)
    DOGRAH_DATABASE_URL: str = "postgresql+asyncpg://dograh:dograh_pg@dograh-postgres:5432/dograh"
    MIDCALL_POLL_INTERVAL_SECONDS: int = 8

    # WhatsApp
    WA_API_URL: str = "https://graph.facebook.com/v21.0"
    WA_PHONE_NUMBER_ID: str = ""
    WA_ACCESS_TOKEN: str = ""
    WA_WEBHOOK_VERIFY_TOKEN: str = ""
    WA_OPTIN_TEMPLATE_NAME: str = ""
    WA_OPTIN_IMAGE_URL: str = ""

    # Razorpay / Payments
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_API_URL: str = "https://api.razorpay.com/v1"
    MIN_AMOUNT_INR: int = 1
    MAX_AMOUNT_INR: int = 100000
    UPI_MERCHANT_NAME: str = "Sai Bhai"
    PAYMENT_SESSION_EXPIRY_MINUTES: int = 15

    # Platform
    PLATFORM_API_URL: str = "http://platform:8000"
    PLATFORM_API_KEY: str = ""
    PLATFORM_APP_DOWNLOAD_URL: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
