from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")
    

class Settings:
    def __init__(self) -> None:
        self.database_url = self._required("DATABASE_URL")
        self.secret_key = self._required_any("SECRET_KEY", "JWT_SECRET")
        self.jwt_secret = self._required_any("JWT_SECRET", "SECRET_KEY")
        self.auth_cookie_name = os.getenv("AUTH_COOKIE_NAME", "dart_auth")
        self.csrf_cookie_name = os.getenv("CSRF_COOKIE_NAME", "dart_csrf")
        self.cookie_secure = self._as_bool(os.getenv("COOKIE_SECURE", "false"))
        self.cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "120"))
        domains = os.getenv("ALLOWED_EMAIL_DOMAINS", "dart-mineria.lat")
        self.allowed_email_domains = {
            domain.strip().lower().lstrip("@")
            for domain in domains.split(",")
            if domain.strip()
        }
        self.email_enabled = self._as_bool(os.getenv("EMAIL_ENABLED", "false"))
        self.email_provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
        self.public_base_url = os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_BASE_URL", "")
        self.public_base_url = self.public_base_url.rstrip("/")
        self.email_from = os.getenv("EMAIL_FROM", "").strip()
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")
        self.smtp_host = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port = self._as_int(os.getenv("SMTP_PORT", "587"), 587)
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "").strip()
        self.smtp_use_tls = self._as_bool(os.getenv("SMTP_USE_TLS", "true"))

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"Falta configurar {name} en el archivo .env")
        return value

    @staticmethod
    def _required_any(*names: str) -> str:
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        raise RuntimeError(f"Falta configurar una de estas variables en el archivo .env: {', '.join(names)}")

    @staticmethod
    def _as_bool(value: str) -> bool:
        return value.lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _as_int(value: str, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


settings = Settings()
