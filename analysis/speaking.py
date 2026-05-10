"""Speaking-style metrics per user.

Pure functions. Counts characters/words, message extremes, and tone signals
(questions, exclamations, ALL-CAPS bursts).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class SpeakingStyle:
    user_id: str
    name: str
    msg_count: int
    avg_chars: float
    avg_words: float
    median_chars: int
    longest_text: str
    longest_chars: int
    question_ratio: float  # share of msgs with '?'
    exclamation_ratio: float  # share of msgs with '!'
    caps_ratio: float  # share of msgs that are mostly uppercase


def _msg_text(m: dict) -> str:
    """Combine text + caption + text_entities into one string per message."""
    parts: list[str] = []
    t = m.get("text")
    if isinstance(t, str):
        parts.append(t)
    elif isinstance(t, list):
        for item in t:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                v = item.get("text")
                if isinstance(v, str):
                    parts.append(v)
    c = m.get("caption")
    if isinstance(c, str):
        parts.append(c)
    return " ".join(parts).strip()


def _is_caps(text: str) -> bool:
    """Heuristic: message is 'shouting' if it has ≥5 letters and >60% uppercase."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 5:
        return False
    uppers = sum(1 for c in letters if c.isupper())
    return uppers / len(letters) > 0.6


def analyze(messages: list[dict]) -> dict[str, SpeakingStyle]:
    """Return {user_id: SpeakingStyle}. Skips users with no text messages."""
    user_texts: dict[str, list[str]] = defaultdict(list)
    user_names: dict[str, str] = {}

    for m in messages:
        if not isinstance(m, dict):
            continue
        uid = m.get("from_id")
        if not uid:
            continue
        uid = str(uid).replace(" ", "")
        user_names.setdefault(uid, m.get("from") or uid)
        text = _msg_text(m)
        if text:
            user_texts[uid].append(text)

    out: dict[str, SpeakingStyle] = {}
    for uid, texts in user_texts.items():
        n = len(texts)
        if n == 0:
            continue
        chars = [len(t) for t in texts]
        words = [len(t.split()) for t in texts]
        sorted_chars = sorted(chars)
        median_c = sorted_chars[n // 2]
        longest_idx = max(range(n), key=lambda i: chars[i])
        questions = sum(1 for t in texts if "?" in t)
        excl = sum(1 for t in texts if "!" in t)
        caps = sum(1 for t in texts if _is_caps(t))
        out[uid] = SpeakingStyle(
            user_id=uid,
            name=user_names.get(uid, uid),
            msg_count=n,
            avg_chars=sum(chars) / n,
            avg_words=sum(words) / n,
            median_chars=median_c,
            longest_text=texts[longest_idx],
            longest_chars=chars[longest_idx],
            question_ratio=questions / n,
            exclamation_ratio=excl / n,
            caps_ratio=caps / n,
        )
    return out
