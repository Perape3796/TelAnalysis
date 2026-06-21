import string

import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist
from nltk.stem.snowball import SnowballStemmer

from . import stopwords_list
from .utils import read_conf, remove_chars_from_text, spec_chars


def _ensure_nltk_data() -> None:
    """Idempotent download of required NLTK corpora on first import.
    word_tokenize needs `punkt_tab` (>=3.8.2); stopwords are obvious."""
    for resource, path in (
        ("stopwords", "corpora/stopwords"),
        ("punkt_tab", "tokenizers/punkt_tab"),
    ):
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(resource, quiet=True)


_ensure_nltk_data()
stemmer = SnowballStemmer("russian")

# Действия, которые нужно игнорировать в тексте
action_map = ["Invite Member", "Kicked Members", "Joined by Link", "Pinned Message"]

# Chat-specific colloquial fillers NLTK's stopword corpora don't cover.
# Without these, "yeah", "ok", "btw" dominate Top Words in EN-heavy chats
# and "это", "ну" do the same in RU.
_RU_EXTRA_STOPWORDS = ["это", "ну", "но", "еще", "ещё", "оно", "типа", "вот", "там", "тут"]
_EN_EXTRA_STOPWORDS = [
    "yeah",
    "yep",
    "nope",
    "ok",
    "okay",
    "lol",
    "lmao",
    "rofl",
    "btw",
    "tho",
    "bc",
    "imo",
    "imho",
    "afaik",
    "ngl",
    "tbh",
    "rly",
    "really",
    "kinda",
    "sorta",
    "gonna",
    "wanna",
    "gotta",
    "im",
    "youre",
    "hes",
    "shes",
    "theyre",
    "weve",
    "youve",
    "dont",
    "doesnt",
    "didnt",
    "wont",
    "wouldnt",
    "couldnt",
    "shouldnt",
    "isnt",
    "arent",
    "wasnt",
    "werent",
    "havent",
    "hasnt",
    "hadnt",
]


def analyse(data, most_com):
    # Настройка стоп-слов
    russian_stopwords = stopwords.words("russian")
    russian_stopwords.extend(_RU_EXTRA_STOPWORDS)
    english_stopwords = stopwords.words("english")
    english_stopwords.extend(_EN_EXTRA_STOPWORDS)

    # Приведение текста к нижнему регистру и удаление лишних символов
    text = (
        str(data)
        .lower()
        .replace("'", "")
        .replace(",", "")
        .replace("[", "")
        .replace("]", "")
        .replace("-", " ")
    )

    for action in action_map:
        text = text.replace(action.lower(), "")

    text = remove_chars_from_text(text, spec_chars)
    text = remove_chars_from_text(text, string.digits)

    # Проверка, что текст не пустой
    if len(text) < 1:
        return [], []

    # Токенизация текста
    text_tokens = word_tokenize(text)

    # Стемминг токенов, если выбран
    if read_conf("select_type_stem") == "On":
        text_tokens = [stemmer.stem(word) for word in text_tokens]

    # Фильтрация токенов
    text_tokens = [
        token.strip()
        for token in text_tokens
        if token not in russian_stopwords
        and len(token) >= 3
        and len(token) < 26
        and token not in english_stopwords
        and "http" not in token
        and token not in stopwords_list.stopword_txt
    ]

    # Частотное распределение
    text = nltk.Text(text_tokens)
    fdist = FreqDist(text)
    fdist = fdist.most_common(most_com)

    return fdist, text_tokens


def analyse_all(data, most_com):
    # Настройка стоп-слов
    russian_stopwords = stopwords.words("russian")
    english_stopwords = stopwords.words("english")
    russian_stopwords.extend(_RU_EXTRA_STOPWORDS)
    english_stopwords.extend(_EN_EXTRA_STOPWORDS)

    # Приведение текста к нижнему регистру и удаление лишних символов
    text = (
        str(data)
        .lower()
        .replace("'", "")
        .replace(",", "")
        .replace("[", "")
        .replace("]", "")
        .replace("-", " ")
    )
    text = remove_chars_from_text(text, spec_chars)
    text = remove_chars_from_text(text, string.digits)
    # text = remove_emojis(text)

    if len(text) >= 1:
        text_tokens = word_tokenize(text)
    else:
        return [], []

    # Стемминг токенов, если выбран
    if read_conf("select_type_stem") == "On":
        text_tokens = [stemmer.stem(word) for word in text_tokens]

    # Фильтрация токенов
    text_tokens = [
        token.strip()
        for token in text_tokens
        if token not in russian_stopwords
        and len(token) >= 4
        and len(token) < 26
        and token not in english_stopwords
        and "http" not in token
        and token not in stopwords_list.stopword_txt
    ]

    # Частотное распределение
    text = nltk.Text(text_tokens)
    fdist = FreqDist(text)
    fdist = fdist.most_common(most_com)

    data = [i[0] for i in fdist]
    return fdist, data
