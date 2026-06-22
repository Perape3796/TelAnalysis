import json
import re
import string
from pathlib import Path

import emoji
import jmespath

import i18n

spec_chars = string.punctuation + '\n\xa0«»\t—…"<>?!.,;:꧁@#$%^&*()_+=№%༺༺\\༺/༺•'


# Full-export support
def is_full_export(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("chats"), dict)
        and isinstance(data["chats"].get("list"), list)
    )


def sanitize_chat_filename(name, chat_id):
    base = name if name else "saved_messages"
    base = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE)
    base = base.strip("_")[:60] or "chat"
    return f"{base}_{chat_id}"


DEFAULT_CONF = {
    "select_type_stem": "Off",
}

# Anchored to the repo root (parent of analysis/) so reads/writes don't depend
# on the current working directory.
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"


def read_conf(option):
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return jmespath.search(option, data)
    except (FileNotFoundError, json.JSONDecodeError):
        try:
            write_conf(DEFAULT_CONF)
        except OSError:
            pass  # read-only / non-writable dir (e.g. non-root in Docker) — run on defaults
        return DEFAULT_CONF.get(option)


def write_conf(dct: dict) -> None:
    with open(CONFIG_PATH, "w") as fw:
        json.dump(dct, fw)


def remove_chars_from_text(text, char=None):
    if char is None:
        char = spec_chars

    pattern = f"[{re.escape(char)}]"
    text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_emojis(data):
    """Strip Unicode emoji codepoints from text.
    Preserves all non-emoji content: ASCII, cyrillic, punctuation, digits.
    Whitespace is collapsed."""
    if data is None:
        return ""
    if not isinstance(data, str):
        try:
            data = str(data)
        except Exception:
            return ""
    data = emoji.replace_emoji(data, replace="")
    data = re.sub(r"\s+", " ", data).strip()
    return data


_ID_PREFIXES = ("user", "channel", "chat")


def _short_id(uid) -> str:
    """Strip Telegram's `user`/`channel`/`chat` prefix off a from_id, leaving the
    bare numeric id used to disambiguate anonymous participants."""
    s = str(uid)
    for pre in _ID_PREFIXES:
        if s.startswith(pre):
            return s[len(pre):]
    return s


# Whitespace + zero-width / bidi-format chars + variation selectors. A name made
# of only these renders as a blank cell (some users set their name to a single
# U+FE0E), so we treat such names as no name at all.
_BLANK_NAME_RE = re.compile(r"[\s\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff\ufe00-\ufe0f]+")


def display_name(raw_from, uid) -> str:
    """Human label for a participant.

    Telegram Desktop exports leave `from` empty for deleted accounts and carry
    no username/phone anywhere, so when there's no name we show a stable
    "Аноним · <id>" instead of leaking the raw `userNNNN` from_id into the UI.
    The id keeps otherwise-identical anonymous rows distinguishable. Names that
    are only invisible glyphs are treated the same as missing.
    """
    if isinstance(raw_from, str):
        if _BLANK_NAME_RE.sub("", raw_from):  # at least one visible glyph remains
            return raw_from.strip()
    elif raw_from:
        return raw_from
    return f"{i18n.t('Аноним')} · {_short_id(uid)}"


def is_bot_name(name) -> bool:
    """Heuristic: a display name ending in "bot"/"бот" is an automated account
    (welcome/rules/moderation bots) whose canned reposts pollute word and phrase
    stats. The export carries no bot flag, so the name is the only signal."""
    if not isinstance(name, str):
        return False
    n = name.strip().lower()
    return n.endswith("bot") or n.endswith("бот")


# A long message reposted verbatim (pinned rules, spam, forwards) drowns out real
# vocabulary and phrases. We collapse such repeats to one occurrence — but only
# when they're long, so genuine short catchphrases ("доброе утро") are untouched.
DEDUP_MIN_CHARS = 80


def clear_user(user):
    # Убираем спецсимволы, эмодзи и очищаем текст
    user = str(user).replace(" ", "").replace('"', "").replace(".", "").replace("꧁", "")
    user = remove_chars_from_text(user)
    user = remove_emojis(user)

    return user.strip()  # Удаляем пробелы в начале и конце строки
