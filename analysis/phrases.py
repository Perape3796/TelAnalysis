"""N-gram (bigram/trigram) phrase extraction — catchphrases per chat or per user.

Builds n-grams within message boundaries (don't cross messages — that produces
spurious phrases). Filters stopwords from edges and short tokens."""

from __future__ import annotations

import re
import string
from collections import Counter, defaultdict

import jmespath
import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords as nltk_stopwords

from . import stopwords_list
from .utils import DEDUP_MIN_CHARS, display_name, is_bot_name, remove_emojis, spec_chars

_RUS_SW: set[str] | None = None
_ENG_SW: set[str] | None = None
_CUSTOM_SW = set(stopwords_list.stopword_txt)
_DIGITS_SW = set(string.digits)


def _ensure_stopwords() -> None:
    """Lazy-load NLTK stopword corpora (not at import time, to avoid a network
    poke when the analysis module is just imported)."""
    global _RUS_SW, _ENG_SW
    if _RUS_SW is None:
        try:
            _RUS_SW = set(nltk_stopwords.words("russian"))
        except LookupError:
            nltk.download("stopwords", quiet=True)
            _RUS_SW = set(nltk_stopwords.words("russian"))
        _RUS_SW.update({"это", "ну", "но", "еще", "ещё", "оно", "типа"})
    if _ENG_SW is None:
        _ENG_SW = set(nltk_stopwords.words("english"))


def _is_stop(tok: str) -> bool:
    if (
        not tok
        or tok in _RUS_SW
        or tok in _ENG_SW
        or tok in _CUSTOM_SW
        or len(tok) < 3
        or "http" in tok
    ):
        return True
    return False


def _msg_text(m: dict) -> str:
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
    ents = jmespath.search("text_entities[*].text", m)
    if ents:
        parts.extend(e for e in ents if isinstance(e, str))
    return " ".join(parts)


_PUNCT_PATTERN = re.compile(f"[{re.escape(spec_chars)}]")


def _tokenize_clean(text: str) -> list[str]:
    text = remove_emojis(text or "").lower()
    text = _PUNCT_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    try:
        tokens = word_tokenize(text)
    except LookupError:
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        tokens = word_tokenize(text)
    return [t for t in tokens if t and t not in _DIGITS_SW]


def _ngrams_no_stop_at_edges(tokens: list[str], n: int) -> list[str]:
    """N-grams where the FIRST and LAST tokens are not stopwords. Internal
    stopwords are allowed (for natural phrases like 'я не знаю'). Skips
    n-grams containing pure-digit tokens."""
    out: list[str] = []
    for i in range(len(tokens) - n + 1):
        gram = tokens[i : i + n]
        if _is_stop(gram[0]) or _is_stop(gram[-1]):
            continue
        if any(t.isdigit() for t in gram):
            continue
        out.append(" ".join(gram))
    return out


def top_phrases(
    messages: list[dict],
    n: int = 2,
    top: int = 30,
    min_count: int = 2,
    filter_uid: str | None = None,
) -> list[tuple[str, int]]:
    """Return top N phrases of size `n` (bigrams or trigrams) by frequency.
    Phrases occurring fewer than `min_count` times are dropped.
    `filter_uid` restricts to one user's messages."""
    _ensure_stopwords()
    counter: Counter = Counter()
    seen_long: set[str] = set()
    for m in messages:
        if not isinstance(m, dict):
            continue
        if filter_uid is not None and m.get("from_id") != filter_uid:
            continue
        if filter_uid is None and is_bot_name(m.get("from")):
            continue  # skip bot reposts from the chat-wide phrase pool
        text = _msg_text(m)
        if not text:
            continue
        tokens = _tokenize_clean(text)
        if len(tokens) < n:
            continue
        key = " ".join(tokens)
        if len(key) >= DEDUP_MIN_CHARS:
            if key in seen_long:
                continue  # same long block already counted (rules/spam repost)
            seen_long.add(key)
        for ng in _ngrams_no_stop_at_edges(tokens, n):
            counter[ng] += 1
    return [(p, c) for p, c in counter.most_common(top * 2) if c >= min_count][:top]


def per_user_phrases(
    messages: list[dict], n: int = 2, top: int = 15, min_count: int = 2
) -> dict[str, list[tuple[str, int]]]:
    """Per-user top phrases. Returns {user_id: [(phrase, count)]}."""
    _ensure_stopwords()
    by_user: dict[str, Counter] = defaultdict(Counter)
    user_names: dict[str, str] = {}
    seen_long: dict[str, set[str]] = defaultdict(set)
    for m in messages:
        if not isinstance(m, dict):
            continue
        uid = m.get("from_id")
        if not uid:
            continue
        if is_bot_name(m.get("from")):
            continue  # bots aren't conversational participants
        user_names.setdefault(uid, display_name(m.get("from"), uid))
        text = _msg_text(m)
        if not text:
            continue
        tokens = _tokenize_clean(text)
        if len(tokens) < n:
            continue
        key = " ".join(tokens)
        if len(key) >= DEDUP_MIN_CHARS:
            if key in seen_long[uid]:
                continue  # this user's reposted long block — count once
            seen_long[uid].add(key)
        for ng in _ngrams_no_stop_at_edges(tokens, n):
            by_user[uid][ng] += 1
    return {
        uid: [(p, c) for p, c in cnt.most_common(top * 2) if c >= min_count][:top]
        for uid, cnt in by_user.items()
    }
