"""KPIs and timeline data for the Overview tab.

All functions take a list of message dicts (Telegram export shape) and
return primitive structures that Streamlit can render directly. No UI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Kpis:
    total_messages: int
    unique_users: int
    first_date: str | None
    last_date: str | None
    days_active: int
    media_messages: int
    service_messages: int


def _parse_date(s: str) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def compute_kpis(messages: list[dict]) -> Kpis:
    total = len(messages)
    users = set()
    media = 0
    service = 0
    first = None
    last = None
    for m in messages:
        if not isinstance(m, dict):
            continue
        mtype = m.get("type")
        if mtype == "service":
            service += 1
        if any(k in m for k in ("photo", "file", "media_type", "voice_message")):
            media += 1
        uid = m.get("from_id") or m.get("actor_id")
        if uid:
            users.add(uid)
        d = _parse_date(m.get("date"))
        if d:
            if first is None or d < first:
                first = d
            if last is None or d > last:
                last = d
    days_active = 0
    if first and last:
        days_active = (last.date() - first.date()).days + 1
    return Kpis(
        total_messages=total,
        unique_users=len(users),
        first_date=first.strftime("%Y-%m-%d") if first else None,
        last_date=last.strftime("%Y-%m-%d") if last else None,
        days_active=days_active,
        media_messages=media,
        service_messages=service,
    )


def messages_per_day(messages: list[dict]) -> list[tuple[str, int]]:
    """Return [(YYYY-MM-DD, count)] sorted ascending."""
    counts: Counter[str] = Counter()
    for m in messages:
        if not isinstance(m, dict):
            continue
        d = _parse_date(m.get("date"))
        if d:
            counts[d.strftime("%Y-%m-%d")] += 1
    return sorted(counts.items())


def hour_weekday_heatmap(messages: list[dict]) -> list[list[int]]:
    """Return a 7×24 matrix [weekday][hour] of message counts.
    Weekdays: 0 = Monday … 6 = Sunday."""
    grid = [[0] * 24 for _ in range(7)]
    for m in messages:
        if not isinstance(m, dict):
            continue
        d = _parse_date(m.get("date"))
        if d is None:
            continue
        grid[d.weekday()][d.hour] += 1
    return grid


def calendar_data(messages: list[dict]) -> list[tuple[str, int]]:
    """Per-day counts as (date_iso, count). Same as messages_per_day, but
    explicit name for the calendar heatmap consumer."""
    return messages_per_day(messages)


def participants_table(messages: list[dict]) -> list[tuple[str, str, int]]:
    """[(user_id, display_name, message_count)] sorted by count desc."""
    counts: Counter[str] = Counter()
    name_index: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        uid = m.get("from_id")
        if not uid:
            continue
        counts[uid] += 1
        if uid not in name_index:
            name_index[uid] = m.get("from") or uid
    return [(uid, name_index[uid], c) for uid, c in counts.most_common()]
