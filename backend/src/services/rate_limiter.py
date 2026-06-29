from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict, deque
from math import ceil
from threading import RLock

from fastapi import Request

from backend.src.config.settings import settings


logger = logging.getLogger("dart.security")


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()
        self._checks = 0

    def allow(self, key: str, limit: int, window_seconds: int, now: float | None = None) -> tuple[bool, int]:
        current = now if now is not None else time.monotonic()
        threshold = current - window_seconds
        with self._lock:
            self._checks += 1
            if self._checks % 512 == 0:
                stale_keys = [name for name, values in self._events.items() if not values or values[-1] <= threshold]
                for stale_key in stale_keys:
                    self._events.pop(stale_key, None)
                while len(self._events) > 20000:
                    self._events.pop(next(iter(self._events)))
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, ceil(window_seconds - (current - events[0])))
                return False, retry_after
            events.append(current)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._checks = 0


def get_client_ip(request: Request) -> str:
    fallback = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "") if settings.trust_proxy_headers else ""
    if not isinstance(fallback, str):
        fallback = "unknown"
    if not isinstance(forwarded, str):
        forwarded = ""
    # El extremo derecho no puede ser prefijado libremente por el cliente cuando
    # Railway agrega la IP observada al encabezado del proxy.
    candidate = forwarded.rsplit(",", 1)[-1].strip() if forwarded else fallback
    if candidate in {"", "unknown"}:
        return "unknown"
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        logger.warning("SECURITY_SUSPICIOUS_ACTIVITY cause=invalid_client_ip value=%s", candidate[:80])
        return fallback


def enforce_rate_limit(request: Request, limiter: SlidingWindowRateLimiter, scope: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    client_ip = get_client_ip(request)
    allowed, retry_after = limiter.allow(f"{scope}:{client_ip}", limit, window_seconds)
    if not allowed:
        logger.warning(
            "SECURITY_RATE_LIMIT_TRIGGERED scope=%s ip=%s limit=%s window_seconds=%s retry_after=%s",
            scope,
            client_ip,
            limit,
            window_seconds,
            retry_after,
        )
        logger.warning("SECURITY_SUSPICIOUS_ACTIVITY scope=%s ip=%s cause=rate_limit", scope, client_ip)
    return allowed, retry_after


login_rate_limiter = SlidingWindowRateLimiter()
registration_rate_limiter = SlidingWindowRateLimiter()
support_rate_limiter = SlidingWindowRateLimiter()
