import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

_LOCK = RLock()
_CACHE_ITEMS: list[dict] | None = None
_CACHE_MTIME_NS = -1


def _storage_path() -> Path:
    # store notifications in frontend static uploads folder
    base = Path(__file__).resolve().parents[3]
    uploads = base / "frontend" / "static" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads / "notifications.json"


def _read_all() -> list:
    global _CACHE_ITEMS, _CACHE_MTIME_NS
    p = _storage_path()
    if not p.exists():
        return []
    try:
        mtime_ns = p.stat().st_mtime_ns
        if _CACHE_ITEMS is not None and mtime_ns == _CACHE_MTIME_NS:
            return [dict(item) for item in _CACHE_ITEMS]
        items = json.loads(p.read_text(encoding="utf-8"))
        _CACHE_ITEMS = items if isinstance(items, list) else []
        _CACHE_MTIME_NS = mtime_ns
        return [dict(item) for item in _CACHE_ITEMS]
    except Exception:
        return []


def _write_all(items: list):
    global _CACHE_ITEMS, _CACHE_MTIME_NS
    p = _storage_path()
    temporary = p.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(p)
    _CACHE_ITEMS = [dict(item) for item in items]
    _CACHE_MTIME_NS = p.stat().st_mtime_ns


def add_notification(username: str, title: str, message: str, action_url: str = "", event_type: str = "GENERIC"):
    with _LOCK:
        items = _read_all()
        item = {
            "id": str(uuid4()),
            "user": username,
            "title": title,
            "message": message,
            "action_url": action_url,
            "event_type": event_type,
            "read": False,
            "created_at": datetime.now().isoformat(),
        }
        items.append(item)
        _write_all(items)
        return item


def get_notifications(username: str, limit: int = 50) -> list:
    with _LOCK:
        items = [i for i in _read_all() if i.get("user") == username]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[:limit]


def mark_read(notification_id: str, username: str) -> bool:
    with _LOCK:
        items = _read_all()
        changed = False
        for i in items:
            if i.get("id") == notification_id and i.get("user") == username:
                i["read"] = True
                changed = True
                break
        if changed:
            _write_all(items)
        return changed
