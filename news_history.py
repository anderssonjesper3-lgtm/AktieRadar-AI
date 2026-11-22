"""Persistent, deduplicated archive of verified news items.

The archive preserves what the scanner actually received. It does not fetch,
rewrite, or infer news content and is bounded to avoid unbounded disk growth.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY_PATH = Path(__file__).with_name("news_history.json")
MAX_ITEMS = 1000


def _published_value(item):
    value = item.get("published") or item.get("date")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            return None
    return None


def merge_history(existing, incoming, max_items=MAX_ITEMS):
    """Merge by stable news id; newest publication first, no future data added."""
    merged = {}
    for item in list(existing or []) + list(incoming or []):
        key = item.get("id") or item.get("url") or item.get("link")
        if not key:
            continue
        row = dict(item)
        published = _published_value(row)
        row["published"] = published.isoformat() if published else None
        merged[str(key)] = row
    rows = list(merged.values())
    rows.sort(key=lambda row: row.get("published") or "", reverse=True)
    return rows[:max_items]


def load_history(path=HISTORY_PATH):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_history(items, path=HISTORY_PATH):
    path = Path(path)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(incoming, path=HISTORY_PATH):
    rows = merge_history(load_history(path), incoming)
    save_history(rows, path)
    return rows


def latest_for_company(items, company):
    matches = [row for row in items if row.get("company") == company]
    return matches[0] if matches else None
