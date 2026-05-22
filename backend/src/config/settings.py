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


settings = Settings()
