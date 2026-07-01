from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect


SUPPORT_TYPES = {"bug", "error", "mejora", "otro"}
SUPPORT_STATUSES = {"open", "in_progress", "resolved"}


def find_recent_duplicate(user_id: int | None, email: str, ticket_type: str, subject: str, message: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, status, created_at
            FROM support_tickets
            WHERE user_id IS NOT DISTINCT FROM %s
              AND email = %s AND type = %s AND COALESCE(subject, '') = %s AND message = %s
              AND created_at >= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, email, ticket_type, subject, message),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def create_ticket(
    user_id: int | None,
    email: str,
    ticket_type: str,
    message: str,
    contact_name: str = "",
    subject: str = "",
) -> dict[str, Any]:
    ticket_id = str(uuid4())
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            INSERT INTO support_tickets (id, user_id, email, type, message, contact_name, subject, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'open')
            RETURNING id, user_id, email, type, message, contact_name, subject, status, created_at
            """,
            (ticket_id, user_id, email, ticket_type, message, contact_name or None, subject or None),
        )
        ticket = dict(cur.fetchone())
        conn.commit()
        return ticket
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def list_tickets() -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT st.id, st.user_id, st.email, st.type, st.message, st.subject, st.status, st.created_at,
                   COALESCE(u.nombre, u.username, NULLIF(st.contact_name, ''), 'Usuario') AS user_name
            FROM support_tickets st
            LEFT JOIN users u ON u.id = st.user_id
            ORDER BY
                CASE st.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
                st.created_at DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def update_ticket_status(ticket_id: str, status: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE support_tickets SET status = %s WHERE id = %s", (status, ticket_id))
        changed = cur.rowcount == 1
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
