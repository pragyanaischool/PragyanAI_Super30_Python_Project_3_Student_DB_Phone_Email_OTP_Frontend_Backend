"""Application configuration settings."""

import os
from typing import Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings
    except ImportError:
        # Fallback basic object if neither is available in runtime
        class BaseSettings:
            pass


class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "EduPortal Student DB & Verification System"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./students.db")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./students.db")

    # OTP Lifespan
    OTP_EXPIRY_SECONDS: int = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))

    # Twilio SMS Credentials
    TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID", None)
    TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN", None)
    TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER", "+15139603890")

    # SMTP Mail Server Credentials (Defaulted to Gmail port 587 STARTTLS)
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "True").lower() in ("true", "1", "t")
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME", None)
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD", None)

    @property
    def is_twilio_configured(self) -> bool:
        """Evaluates whether all required Twilio credentials are provided."""
        return bool(
            self.TWILIO_ACCOUNT_SID
            and self.TWILIO_AUTH_TOKEN
            and self.TWILIO_PHONE_NUMBER
            and not str(self.TWILIO_ACCOUNT_SID).strip().startswith("your_")
            and not str(self.TWILIO_PHONE_NUMBER).strip().startswith("your_")
        )

    @property
    def is_smtp_configured(self) -> bool:
        """Evaluates whether all required SMTP credentials are provided."""
        return bool(
            self.SMTP_USERNAME
            and self.SMTP_PASSWORD
            and not str(self.SMTP_USERNAME).strip().startswith("your_")
            and not str(self.SMTP_PASSWORD).strip().startswith("your_")
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
