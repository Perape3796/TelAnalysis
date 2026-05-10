"""Conversation sessions — group messages into 'conversations' separated by
silences ≥ N minutes. Reframes raw message counts as actual back-and-forth
sessions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median


@dataclass
class Session:
    start: datetime
    end: datetime
    msg_count: int
    participants: list[str]  # user_id list (preserves insertion order, deduped)


@dataclass
class SessionStats:
    sessions: list[Session]
    avg_messages: float
    median_messages: int
    longest: Session | None
    duration_buckets: dict[str, int]  # by length-of-session in messages


def _parse(s) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def split_into_sessions(messages: list[dict], gap_minutes: int = 30) -> list[Session]:
    """Walk messages in time order; cut a new session whenever the gap to
    the previous message is > `gap_minutes`."""
    rows: list[tuple[datetime, dict]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        d = _parse(m.get("date"))
        if d is None:
            continue
        rows.append((d, m))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return []

    gap_seconds = gap_minutes * 60
    sessions: list[Session] = []
    cur_msgs: list[dict] = [rows[0][1]]
    cur_start = rows[0][0]
    cur_end = rows[0][0]

    def _close(start, end, msgs):
        ps = []
        for m in msgs:
            uid = m.get("from_id")
            if uid and uid not in ps:
                ps.append(uid)
        return Session(start=start, end=end, msg_count=len(msgs), participants=ps)

    for ts, m in rows[1:]:
        if (ts - cur_end).total_seconds() > gap_seconds:
            sessions.append(_close(cur_start, cur_end, cur_msgs))
            cur_msgs = []
            cur_start = ts
        cur_msgs.append(m)
        cur_end = ts
    sessions.append(_close(cur_start, cur_end, cur_msgs))
    return sessions


def stats(sessions: list[Session]) -> SessionStats:
    if not sessions:
        return SessionStats(
            sessions=[],
            avg_messages=0.0,
            median_messages=0,
            longest=None,
            duration_buckets={},
        )
    counts = [s.msg_count for s in sessions]
    longest = max(sessions, key=lambda s: s.msg_count)
    # Bucket by session size for distribution display
    buckets = Counter()
    for c in counts:
        if c <= 2:
            buckets["1-2"] += 1
        elif c <= 5:
            buckets["3-5"] += 1
        elif c <= 15:
            buckets["6-15"] += 1
        elif c <= 50:
            buckets["16-50"] += 1
        elif c <= 200:
            buckets["51-200"] += 1
        else:
            buckets["200+"] += 1
    # Preserve order
    ordered = {}
    for k in ["1-2", "3-5", "6-15", "16-50", "51-200", "200+"]:
        if k in buckets:
            ordered[k] = buckets[k]
    return SessionStats(
        sessions=sessions,
        avg_messages=sum(counts) / len(counts),
        median_messages=int(median(counts)),
        longest=longest,
        duration_buckets=ordered,
    )
