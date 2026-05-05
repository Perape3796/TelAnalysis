# TelAnalysis

Streamlit-дашборд для анализа Telegram-чатов из локального экспорта.

Поддерживает оба формата выгрузки:
- **single chat** (`Settings → Export chat history`) — сразу загружается
- **full archive** (`Settings → Advanced → Export Telegram data`) — в сайдбаре появляется селектор чатов (с поиском и фильтром по типу)

Адаптируется под тип чата: для каналов/групп/личных/saved messages показываются только релевантные табы.

## Что внутри

**Overview**
- KPI: total messages / unique users / days active / media / service
- Plotly area-chart активности по дням
- Calendar heatmap (год × неделя × день)
- Hour × weekday heatmap
- Топ эмодзи и распределение reply latency

**Graph**
- Для групп — интерактивный force-directed pyvis-граф (drag/zoom/hover, толщина рёбер по частоте, цвет — Louvain communities)
- Для маленьких чатов — bar chart "кто отправлял / отвечал / получал ответы"
- Экспорт edges/nodes в CSV для Gephi

**Words**
- Топ слов по чату: wordcloud + bar chart + virtualized table
- Per-user picker: wordcloud юзера, его сообщения с sentiment-скором, top-words
- Извлечение email и телефонов

**Channel**
- Wordcloud + частотный анализ для broadcast-каналов

**Per-user**
- Daily timeline юзера, его hour×weekday heatmap, top emojis, reply latency, top words с wordcloud

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Открыть http://localhost:8501. В сайдбаре указать путь к `result.json` (для больших архивов лучше путь, чем upload — десятикратно быстрее).

## Источник

Проект построен на основе [**TelAnalysis** by Eduard Isaev](https://github.com/krakodjaba/TelAnalysis) ([@e_isaevsan](https://t.me/stdinio)). Спасибо автору за изначальный проект и логику разбора Telegram-экспорта.

Эта версия:
- Переписан UI с pywebio на Streamlit (виртуализованные таблицы — больше не зависает на чатах в десятки тысяч сообщений)
- Заменён matplotlib-граф на интерактивный pyvis с community detection
- Добавлены heatmaps активности (hour × weekday, calendar), emoji-аналитика, reply latency
- Добавлен Per-user tab
- Wordcloud в анализе чатов, не только каналов
- Чистка модулей: убран мёртвый код, исправлены баги в `remove_emojis` (уничтожал английский текст и обрезал после первой эмодзи), убрана гонка `ThreadPoolExecutor` где она ничего не давала из-за GIL

## Лицензия

GPL-3.0 (унаследована из оригинала). См. `LICENSE`.
