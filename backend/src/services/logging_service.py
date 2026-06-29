import json
import sys

from backend.src.config.database import _connect

AUTH_LOGIN_OK = "AUTH_LOGIN_OK"
AUTH_LOGIN_FAIL = "AUTH_LOGIN_FAIL"
AUTH_LOGIN_BLOCKED = "AUTH_LOGIN_BLOCKED"
ART_CREATED = "ART_CREATED"
ART_UPDATED = "ART_UPDATED"
ART_STATUS_CHANGED = "ART_STATUS_CHANGED"
SUPPORT_TICKET_CREATED = "SUPPORT_TICKET_CREATED"
REALTIME_EVENT_SENT = "REALTIME_EVENT_SENT"
SECURITY_RATE_LIMIT = "SECURITY_RATE_LIMIT"
SYSTEM_ERROR_CAPTURED = "SYSTEM_ERROR_CAPTURED"
USER_CREATED = "USER_CREATED"
USER_ROLE_CHANGED = "USER_ROLE_CHANGED"


def log_event(event_type: str, username: str = "", ip_address: str = "", details: dict = None) -> None:
    try:
        details_str = json.dumps(details or {}, ensure_ascii=False)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO system_logs (event_type, username, ip_address, details) VALUES (%s, %s, %s, %s)",
                    (event_type, username or "", ip_address or "", details_str),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[logging_service] Failed to log {event_type}: {exc}", file=sys.stderr)


def get_logs(event_type: str = None, limit: int = 200, offset: int = 0) -> list:
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                if event_type:
                    cur.execute(
                        "SELECT id, event_type, username, ip_address, details, created_at"
                        " FROM system_logs WHERE event_type = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (event_type, limit, offset),
                    )
                else:
                    cur.execute(
                        "SELECT id, event_type, username, ip_address, details, created_at"
                        " FROM system_logs ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (limit, offset),
                    )
                rows = cur.fetchall()
        finally:
            conn.close()
        result = []
        for row in rows:
            try:
                details_parsed = json.loads(row[4]) if row[4] else {}
            except Exception:
                details_parsed = {}
            result.append({
                "id": row[0],
                "event_type": row[1],
                "username": row[2],
                "ip_address": row[3],
                "details": details_parsed,
                "created_at": row[5],
            })
        return result
    except Exception as exc:
        print(f"[logging_service] get_logs error: {exc}", file=sys.stderr)
        return []


def get_error_logs(limit: int = 100) -> list:
    return get_logs(event_type=SYSTEM_ERROR_CAPTURED, limit=limit)


def count_logs_by_type() -> dict:
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT event_type, COUNT(*) FROM system_logs GROUP BY event_type")
                rows = cur.fetchall()
        finally:
            conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as exc:
        print(f"[logging_service] count_logs_by_type error: {exc}", file=sys.stderr)
        return {}
