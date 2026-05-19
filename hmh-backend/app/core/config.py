"""
Application configuration — reads from .env via pydantic-settings.
All environment variables are typed and validated at startup.

SMTP field aliases (all equivalent):
  SMTP_USERNAME  ← preferred
  SMTP_USER      ← legacy alias (auto-mapped)
  GMAIL_USER     ← alternate alias
  GMAIL_APP_PASSWORD / SMTP_PASSWORD ← password aliases
"""

import os
from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "dev_secret_change_before_production_minimum_64_chars_long!!"

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/hmh_system"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_postgres_scheme(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File storage — local path (set to a Render Persistent Disk mount for permanence)
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 5

    # Supabase Storage (optional — set these env vars to enable persistent cloud storage)
    # If set, uploaded files are stored in Supabase Storage instead of the local disk.
    # Create a public bucket named "hmh-uploads" in your Supabase project.
    SUPABASE_URL:         str = ""   # e.g. https://xyz.supabase.co
    SUPABASE_SERVICE_KEY: str = ""   # service_role key (never ANON key for uploads)

    # OCR provider: "local" (pytesseract), "google_vision", or "disabled"
    OCR_PROVIDER: str = "local"
    # Google Cloud Vision credentials (JSON key file path or inline JSON)
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # Alert thresholds — read by alert_scan and reactive alert logic
    LOW_STOCK_THRESHOLD:     float = 5.0    # items below this trigger LOW_STOCK alert
    BOQ_VARIANCE_ALERT_PCT:  float = 10.0   # BOQ usage variance % that triggers BOQ_VARIANCE alert
    PENDING_MR_DAYS:         int   = 5      # MR pending longer than this triggers REQUEST_PENDING_TOO_LONG

    # CORS — comma-separated allowed origins
    # Render env var should set the production domain(s)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://app.hmhgroup.co.za"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # WhatsApp Cloud API
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "hmh_verify_token"
    WHATSAPP_API_VERSION: str = "v25.0"
    WHATSAPP_TEST_TO: str = ""

    # WhatsApp alert templates (used when 24-hour conversation window is closed)
    WHATSAPP_ALERT_TEMPLATE_NAME: str = ""       # e.g. "hmh_alert_notification"
    WHATSAPP_ALERT_TEMPLATE_LANGUAGE: str = "en_US"

    # Alert escalation
    CRITICAL_ALERT_MAX_ATTEMPTS: int = 5
    CRITICAL_ALERT_FIRST_REMINDER_MINUTES: int = 5
    HIGH_ALERT_MAX_ATTEMPTS: int = 2
    HIGH_ALERT_FIRST_REMINDER_MINUTES: int = 15

    # ── SMTP / Email ──────────────────────────────────────────────────────────
    # CANONICAL fields (use these in .env):
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_SSL: bool = False     # True → SMTP_SSL on port 465; False → STARTTLS on port 587
    SMTP_USERNAME: str = ""        # Gmail address — PREFERRED field name
    SMTP_PASSWORD: str = ""        # App password (spaces stripped automatically)
    SMTP_FROM_EMAIL: str = ""      # Defaults to SMTP_USERNAME if blank
    SMTP_FROM_NAME: str = "HMH Procurement"
    PROCUREMENT_EMAIL_CC: str = ""
    PROCUREMENT_EMAIL_BCC: str = ""

    # ALIAS fields — pydantic-settings reads these from .env just like any other field.
    # The model_validator below maps them to the canonical fields above.
    SMTP_USER: str = ""            # alias for SMTP_USERNAME (many tutorials use this)
    GMAIL_USER: str = ""           # alias for SMTP_USERNAME
    GMAIL_APP_PASSWORD: str = ""   # alias for SMTP_PASSWORD
    EMAIL_FROM: str = ""           # alias for SMTP_FROM_EMAIL

    # Explicit mock-mode flag — set EMAIL_MOCK_MODE=true to block real sends in staging
    EMAIL_MOCK_MODE: bool = False

    # IMAP / Gmail inbox reader
    IMAP_ENABLED: bool = False
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_USERNAME: str = ""
    IMAP_PASSWORD: str = ""

    @model_validator(mode="after")
    def resolve_smtp_aliases_and_clean(self) -> "Settings":
        """
        Map alias fields → canonical fields, strip password spaces, apply defaults.
        pydantic-settings reads alias fields from .env automatically since they're
        declared as model fields — no need for os.getenv().
        """
        # ── Username: SMTP_USER / GMAIL_USER → SMTP_USERNAME ─────────────
        if not self.SMTP_USERNAME:
            self.SMTP_USERNAME = self.SMTP_USER or self.GMAIL_USER or ""

        # ── Password: GMAIL_APP_PASSWORD → SMTP_PASSWORD ──────────────────
        if not self.SMTP_PASSWORD:
            self.SMTP_PASSWORD = self.GMAIL_APP_PASSWORD or ""

        # ── Strip spaces (Gmail app passwords are shown with spaces) ───────
        if self.SMTP_PASSWORD:
            self.SMTP_PASSWORD = self.SMTP_PASSWORD.replace(" ", "")
        if self.IMAP_PASSWORD:
            self.IMAP_PASSWORD = self.IMAP_PASSWORD.replace(" ", "")

        # ── Defaults from username ─────────────────────────────────────────
        if not self.SMTP_FROM_EMAIL:
            self.SMTP_FROM_EMAIL = self.EMAIL_FROM or self.SMTP_USERNAME
        if not self.IMAP_USERNAME:
            self.IMAP_USERNAME = self.SMTP_USERNAME
        if not self.IMAP_PASSWORD:
            self.IMAP_PASSWORD = self.SMTP_PASSWORD

        return self

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def procurement_cc_list(self) -> List[str]:
        return [e.strip() for e in self.PROCUREMENT_EMAIL_CC.split(",") if e.strip()]

    @property
    def procurement_bcc_list(self) -> List[str]:
        return [e.strip() for e in self.PROCUREMENT_EMAIL_BCC.split(",") if e.strip()]

    @property
    def smtp_sender_address(self) -> str:
        return self.SMTP_FROM_EMAIL or self.SMTP_USERNAME

    @property
    def email_mock_active(self) -> bool:
        """True when email should be mocked (not really sent)."""
        return self.EMAIL_MOCK_MODE or not self.SMTP_ENABLED

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_long(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Use this everywhere instead of Settings()."""
    return Settings()


# Module-level singleton
settings = get_settings()
