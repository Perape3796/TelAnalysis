"""Per-user word + sentiment + contact extraction.
Pure functions: take messages, return structured results."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import jmespath
import phonenumbers
from validate_email import validate_email

import nltk_analyse

from . import sentiment as _sentiment_mod

_action_map = {
    "invite_members": "Invite Member",
    "remove_members": "Kicked Members",
    "join_group_by_link": "Joined by Link",
    "pin_message": "Pinned Message",
}


@dataclass
class UserStats:
    user_id: str
    name: str
    messages: list[tuple[str, float]] = field(default_factory=list)
    avg_sentiment: float = 0.0
    top_words: list[tuple[str, int]] = field(default_factory=list)
    total_tokens: int = 0
    unique_tokens: int = 0

    @property
    def ttr(self) -> float:
        """Type-token ratio. 1.0 = every word is unique, 0.0 = no diversity."""
        return self.unique_tokens / self.total_tokens if self.total_tokens else 0.0


@dataclass
class WordsResult:
    users: dict[str, UserStats]
    emails: list[str]
    phones: list[str]
    chat_top_words: list[tuple[str, int]]
    chat_avg_sentiment: float
    sentiment_available: bool = False
    # (date_iso, score, user_id) for every scored fragment with a date.
    # Used to build sentiment-over-time charts without re-running the model.
    dated_scores: list[tuple[str, float, str]] = field(default_factory=list)
    # Number of fragments where a sarcasm-marker emoji caused score attenuation.
    sarcasm_marked: int = 0


def _score_all(texts: list[str]) -> list[float]:
    """Batch-score texts via rubert-tiny2. Falls back to zeros on failure."""
    if not texts:
        return []
    try:
        return _sentiment_mod.score_batch(texts)
    except Exception as ex:
        # If transformers / model load fails, don't kill analysis.
        print(f"[words] sentiment failed, returning zeros: {ex}")
        return [0.0] * len(texts)


def _extract_contacts(text: str) -> tuple[list[str], list[str]]:
    emails: list[str] = []
    for e in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        if validate_email(e, verify=False):
            emails.append(e)
    phones: list[str] = []
    for p in re.findall(
        r"\+?[0-9]{1,3}?[-. (]?[0-9]{1,4}[-. )]?[0-9]{1,4}[-. ]?[0-9]{1,9}", text
    ):
        try:
            parsed = phonenumbers.parse(p, None)
            if phonenumbers.is_valid_number(parsed):
                phones.append(p)
        except Exception:
            pass
    return emails, phones


def _extract_text(message) -> set[str]:
    """Recursively collect text fragments from a message dict."""
    out: set[str] = set()
    if isinstance(message, dict):
        t = message.get("text")
        if isinstance(t, str) and t.strip():
            out.add(t)
        elif isinstance(t, list):
            for item in t:
                if isinstance(item, str):
                    out.add(item)
        c = message.get("caption")
        if isinstance(c, str) and c.strip():
            out.add(c)
        ents = jmespath.search("text_entities[*].text", message)
        if ents:
            for e in ents:
                out.add(e)
        if "forwarded_from" in message:
            out.update(_extract_text(message["forwarded_from"]))
        if "reply_to_message" in message:
            out.update(_extract_text(message["reply_to_message"]))
        for v in message.values():
            if isinstance(v, (list, dict)):
                out.update(_extract_text(v))
    elif isinstance(message, list):
        for item in message:
            out.update(_extract_text(item))
    return out


def analyze(messages: list[dict], most_com: int = 30) -> WordsResult:
    """Process messages → per-user stats + global aggregates."""
    # Use mutable lists internally so we can fill in sentiment scores after
    # batched inference. Convert to tuples at the end.
    user_msgs: dict[str, list[list]] = defaultdict(list)
    user_names: dict[str, str] = {}
    emails: list[str] = []
    phones: list[str] = []

    # Pass 1: walk messages, accumulate placeholder records, track which need scoring.
    to_score: list[tuple[str, int]] = []  # (uid, slot_index)
    score_inputs: list[str] = []
    score_dates: list[str | None] = []  # message date for each entry in score_inputs

    for m in messages:
        if not isinstance(m, dict):
            continue
        uid = m.get("from_id")
        if not uid:
            uid = m.get("actor_id")
            if uid is None:
                continue
            uid = str(uid).replace(" ", "")
            action = m.get("action")
            if action:
                tex = m.get("text") or ""
                action_text = _action_map.get(action, action)
                if action in ("invite_members", "remove_members"):
                    members = m.get("members") or []
                    members_str = ",".join(str(x) for x in members if x)
                    user_msgs[uid].append([f"{action_text} - {members_str}", 0.0])
                else:
                    user_msgs[uid].append([f"{action_text} {tex}", 0.0])
                continue

        uid = str(uid).replace(" ", "")
        if uid not in user_names:
            user_names[uid] = m.get("from") or uid

        m_date = m.get("date") if isinstance(m.get("date"), str) else None
        for fragment in _extract_text(m):
            if not fragment:
                continue
            slot = len(user_msgs[uid])
            user_msgs[uid].append([fragment, 0.0])  # placeholder score
            to_score.append((uid, slot))
            score_inputs.append(fragment)
            score_dates.append(m_date)
            ex_emails, ex_phones = _extract_contacts(fragment)
            emails.extend(ex_emails)
            phones.extend(ex_phones)

    # Pass 2: batch-score all fragments at once (much faster than per-call).
    sentiment_available = _sentiment_mod.is_available()
    dated_scores: list[tuple[str, float, str]] = []
    sarcasm_marked = 0
    if sentiment_available:
        raw_scores = _score_all(score_inputs)
        adjusted: list[float] = []
        for (uid, slot), text, raw, date_str in zip(
            to_score, score_inputs, raw_scores, score_dates
        ):
            s, marked = _sentiment_mod.attenuate_sarcasm(text, float(raw))
            if marked:
                sarcasm_marked += 1
            user_msgs[uid][slot][1] = s
            adjusted.append(s)
            if date_str:
                dated_scores.append((date_str, s, uid))
        scores = adjusted
    else:
        scores = []  # leave placeholder zeros

    # Per-user aggregates
    users: dict[str, UserStats] = {}
    all_tokens: list[str] = []
    for uid, msgs in user_msgs.items():
        msgs_t = [tuple(r) for r in msgs]
        sentiments = [s for _, s in msgs_t if isinstance(s, float)]
        avg = sum(sentiments) / len(sentiments) if sentiments else 0.0
        try:
            top, tokens = nltk_analyse.analyse(msgs_t, most_com)
        except Exception:
            top, tokens = [], []
        all_tokens.extend(tokens)
        users[uid] = UserStats(
            user_id=uid,
            name=user_names.get(uid, uid),
            messages=msgs_t,
            avg_sentiment=avg,
            top_words=list(top),
            total_tokens=len(tokens),
            unique_tokens=len(set(tokens)),
        )

    # Chat-wide aggregates: average across all fragment scores (not per-word).
    try:
        chat_top, _ = nltk_analyse.analyse_all(all_tokens, most_com)
    except Exception:
        chat_top = []
    chat_top_pairs = list(chat_top)
    if scores:
        chat_avg = sum(scores) / len(scores)
    else:
        chat_avg = 0.0

    return WordsResult(
        users=users,
        emails=sorted(set(emails)),
        phones=sorted(set(phones)),
        chat_top_words=chat_top_pairs,
        chat_avg_sentiment=chat_avg,
        sentiment_available=sentiment_available,
        dated_scores=dated_scores,
        sarcasm_marked=sarcasm_marked,
    )


def sentiment_period_series(
    dated_scores: list[tuple[str, float, str]],
    granularity: str = "week",
    per_user: bool = False,
) -> list[dict]:
    """Group scored fragments into time buckets, return [(period, avg, count[, user])].

    `dated_scores`: list of (iso_date, score, user_id) from WordsResult.
    Granularity: 'day' | 'week' | 'month'. Default week.
    Set per_user=True for an extra "user_id" key (caller resolves the name).
    """
    buckets: dict = defaultdict(list)
    for date_iso, score, uid in dated_scores:
        try:
            d = datetime.fromisoformat(date_iso)
        except ValueError:
            continue
        period = _period_key(d, granularity)
        key = (uid, period) if per_user else period
        buckets[key].append(score)

    rows: list[dict] = []
    if per_user:
        for (uid, period), vs in sorted(buckets.items(), key=lambda kv: kv[0][1]):
            rows.append(
                {
                    "user_id": uid,
                    "period": period,
                    "avg": sum(vs) / len(vs),
                    "count": len(vs),
                }
            )
    else:
        for period, vs in sorted(buckets.items()):
            rows.append(
                {
                    "period": period,
                    "avg": sum(vs) / len(vs),
                    "count": len(vs),
                }
            )
    return rows


def _msg_text_blob(message: dict) -> str:
    """Concatenate all text content from a message into a lowercase string."""
    parts: list[str] = []
    t = message.get("text")
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
    c = message.get("caption")
    if isinstance(c, str):
        parts.append(c)
    ents = jmespath.search("text_entities[*].text", message)
    if ents:
        parts.extend(e for e in ents if isinstance(e, str))
    return " ".join(parts).lower()


def _period_key(d: datetime, granularity: str) -> str:
    if granularity == "day":
        return d.strftime("%Y-%m-%d")
    if granularity == "month":
        return d.strftime("%Y-%m-01")
    # default: ISO week, Monday-anchored
    start = d - timedelta(days=d.weekday())
    return start.strftime("%Y-%m-%d")


def word_timeline(
    messages: list[dict],
    terms: list[str],
    granularity: str = "week",
) -> dict[str, list[tuple[str, int]]]:
    """For each term, return [(period_start_iso, count)] sorted ascending.

    Match is case-insensitive substring. For full-word matching,
    the term must be alphanumeric (we apply word boundaries).
    Granularity: 'day' | 'week' | 'month'.
    """
    if not terms:
        return {}

    patterns = {}
    for raw in terms:
        t = (raw or "").strip().lower()
        if not t:
            continue
        # word-boundary match if term is alphanumeric, else substring
        if re.fullmatch(r"[\w\-]+", t, flags=re.UNICODE):
            patterns[t] = re.compile(rf"(?<![\w]){re.escape(t)}(?![\w])", re.UNICODE)
        else:
            patterns[t] = re.compile(re.escape(t), re.UNICODE)

    counts: dict[str, Counter] = {t: Counter() for t in patterns}

    for m in messages:
        if not isinstance(m, dict):
            continue
        date_str = m.get("date")
        if not isinstance(date_str, str):
            continue
        try:
            d = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        blob = _msg_text_blob(m)
        if not blob:
            continue
        key = _period_key(d, granularity)
        for term, pat in patterns.items():
            n = len(pat.findall(blob))
            if n:
                counts[term][key] += n

    return {t: sorted(c.items()) for t, c in counts.items()}
