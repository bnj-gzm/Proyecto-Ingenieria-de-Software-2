from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from threading import RLock


@dataclass
class LoginAttempt:
    failures: int = 0
    blocked_until: datetime | None = None


_attempts: dict[str, LoginAttempt] = {}
_lock = RLock()


def _email_key(email: str) -> str:
    return (email or "").strip().lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _block_minutes(failures: int) -> int:
    if failures < 3:
        return 0
    if failures == 3:
        return 3
    if failures == 4:
        return 10
    if failures == 5:
        return 30
    return 60


def remaining_block_minutes(email: str, now: datetime | None = None) -> int:
    key = _email_key(email)
    current_time = now or _now()
    with _lock:
        attempt = _attempts.get(key)
        if not attempt or not attempt.blocked_until:
            return 0
        remaining_seconds = (attempt.blocked_until - current_time).total_seconds()
        if remaining_seconds <= 0:
            attempt.blocked_until = None
            return 0
        return max(1, ceil(remaining_seconds / 60))


def record_login_failure(email: str, now: datetime | None = None) -> tuple[int, int]:
    key = _email_key(email)
    current_time = now or _now()
    with _lock:
        attempt = _attempts.setdefault(key, LoginAttempt())
        attempt.failures += 1
        minutes = _block_minutes(attempt.failures)
        attempt.blocked_until = current_time + timedelta(minutes=minutes) if minutes else None
        return attempt.failures, minutes


def reset_login_attempts(email: str) -> None:
    with _lock:
        _attempts.pop(_email_key(email), None)


def clear_all_login_attempts() -> None:
    """Limpia el estado en memoria; se usa durante pruebas y reinicios controlados."""
    with _lock:
        _attempts.clear()
