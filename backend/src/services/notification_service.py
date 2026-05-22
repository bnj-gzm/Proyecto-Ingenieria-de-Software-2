import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _storage_path() -> Path:
    # store notifications in frontend static uploads folder
    base = Path(__file__).resolve().parents[3]
    uploads = base / "frontend" / "static" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads / "notifications.json"


def _read_all() -> list:
    p = _storage_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_all(items: list):
    p = _storage_path()
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_notification(username: str, title: str, message: str):
    items = _read_all()
    item = {
        "id": str(uuid4()),
        "user": username,
        "title": title,
        "message": message,
        "read": False,
        "created_at": datetime.now().isoformat(),
    }
    items.append(item)
    _write_all(items)
    return item


def get_notifications(username: str, limit: int = 50) -> list:
    items = [i for i in _read_all() if i.get("user") == username]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit]


def mark_read(notification_id: str, username: str) -> bool:
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
