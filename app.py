"""TelAnalysis — Streamlit dashboard.

Run with:
    streamlit run app.py

Auto-detects single-chat vs full-archive Telegram exports.
Tabs adapt to chat type (channel/group/personal/saved).
"""

from __future__ import annotations

import os
import tempfile
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import channel as ch_mod
from analysis import emoji_stats as emoji_mod
from analysis import graph as graph_mod
from analysis import latency as latency_mod
from analysis import media as media_mod
from analysis import (
    loader,
    overview,
    render as render_mod,
    speaking as speaking_mod,
    words as words_mod,
)

st.set_page_config(
    page_title="TelAnalysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner="Loading JSON…")
def _load_data(path: str, mtime: float) -> dict:
    """Cached load by (path, mtime). mtime ensures cache invalidates on edit."""
    return loader.load_json(path)


# cache key is `cache_key` (a hashable id); `_messages` is excluded from hashing
# by the leading underscore (Streamlit convention).


@st.cache_data(show_spinner="Computing KPIs…")
def _kpis(cache_key: str, _messages: list) -> overview.Kpis:
    return overview.compute_kpis(_messages)


@st.cache_data(show_spinner="Computing daily activity…")
def _per_day(cache_key: str, _messages: list):
    return overview.messages_per_day(_messages)


@st.cache_data(show_spinner="Computing hour-of-day map…")
def _hour_weekday(cache_key: str, _messages: list):
    return overview.hour_weekday_heatmap(_messages)


@st.cache_data(show_spinner="Computing participants…")
def _participants(cache_key: str, _messages: list):
    return overview.participants_table(_messages)


@st.cache_data(show_spinner="Building graph…")
def _graph_data(cache_key: str, _messages: list) -> graph_mod.GraphData:
    return graph_mod.build(_messages)


@st.cache_data(show_spinner="Analysing words…")
def _words(cache_key: str, _messages: list, most_com: int):
    return words_mod.analyze(_messages, most_com=most_com)


@st.cache_data(show_spinner="Analysing channel…")
def _channel(cache_key: str, _messages: list, most_com: int):
    return ch_mod.analyze(_messages, most_com=most_com)


@st.cache_data(show_spinner="Counting emojis…")
def _emojis(cache_key: str, _messages: list):
    return emoji_mod.analyze(_messages)


@st.cache_data(show_spinner="Computing reply latency…")
def _latency(cache_key: str, _messages: list):
    return latency_mod.compute(_messages)


@st.cache_data(show_spinner="Counting media…")
def _media(cache_key: str, _messages: list):
    return media_mod.analyze(_messages)


@st.cache_data(show_spinner="Profiling speaking style…")
def _speaking(cache_key: str, _messages: list):
    return speaking_mod.analyze(_messages)


@st.cache_data(show_spinner="Filtering by date…")
def _filter_by_date(cache_key: str, _messages: list, from_d: str, to_d: str):
    return overview.filter_by_date(_messages, from_d, to_d)


def _calendar_heatmap_fig(df: pd.DataFrame) -> go.Figure | None:
    """GitHub-contributions-style calendar heatmap.

    Splits per-year, lays out weeks horizontally and weekdays vertically.
    df must have columns ['date', 'messages']. Returns None on empty df.
    """
    if df is None or len(df) == 0:
        return None
    cal = df.copy()
    cal["date"] = pd.to_datetime(cal["date"])
    # Fill missing days with 0 so the calendar is dense
    full = pd.date_range(cal["date"].min(), cal["date"].max(), freq="D")
    cal = cal.set_index("date").reindex(full, fill_value=0).reset_index()
    cal.columns = ["date", "messages"]
    cal["year"] = cal["date"].dt.year
    cal["weekday"] = cal["date"].dt.weekday  # 0 Mon … 6 Sun
    cal["week"] = cal["date"].dt.isocalendar().week

    years = sorted(cal["year"].unique())
    fig = go.Figure()

    weekdays_lbl = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Build separate panel per year stacked vertically using subplots? Simpler:
    # one big heatmap with year offset on the y axis. Stack via subplot rows.
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=len(years),
        cols=1,
        subplot_titles=[str(y) for y in years],
        vertical_spacing=0.08,
    )
    for idx, y in enumerate(years, start=1):
        sub = cal[cal["year"] == y].copy()
        # Re-index weeks 1..max so each year starts at week 1
        sub["week"] = sub["date"].dt.strftime("%U").astype(int)
        pivot = sub.pivot_table(
            index="weekday",
            columns="week",
            values="messages",
            aggfunc="sum",
            fill_value=0,
        ).reindex(range(7), fill_value=0)
        fig.add_trace(
            go.Heatmap(
                z=pivot.values,
                x=[f"W{w}" for w in pivot.columns],
                y=weekdays_lbl,
                colorscale="Greens",
                showscale=(idx == 1),
                hovertemplate=("%{y} · week %{x}<br>messages: %{z}<extra></extra>"),
            ),
            row=idx,
            col=1,
        )
    fig.update_layout(
        title="Calendar heatmap",
        template="plotly_dark",
        height=180 * len(years) + 40,
        margin=dict(l=0, r=0, t=60, b=0),
    )
    for r in range(1, len(years) + 1):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    return fig


# Sidebar — file picker + chat selector
with st.sidebar:
    st.title("📊 TelAnalysis")
    st.caption("Telegram chat analytics")

    src_mode = st.radio(
        "Source",
        ["File path", "Upload"],
        horizontal=True,
        help="65 MB+ exports — use path. Faster, no base64 over WebSocket.",
    )

    json_path: str | None = None
    if src_mode == "File path":
        path_input = st.text_input(
            "Path to result.json",
            value=st.session_state.get("last_path", ""),
            placeholder="/Users/me/.../result.json",
        )
        if path_input:
            if os.path.exists(path_input):
                json_path = path_input
                st.session_state["last_path"] = path_input
            else:
                st.error("File not found")
    else:
        upload = st.file_uploader("Telegram export JSON", type=["json"])
        if upload is not None:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".json", prefix="tla_"
            )
            tmp.write(upload.read())
            tmp.close()
            json_path = tmp.name

if json_path is None:
    st.info(
        "👈 Pick a Telegram export JSON in the sidebar.\n\n"
        "**Single-chat** export → `Settings → Export chat history`.\n\n"
        "**Full archive** → `Settings → Advanced → Export Telegram data`. "
        "You'll get a chat picker."
    )
    st.stop()

data = _load_data(json_path, os.path.getmtime(json_path))
chats = loader.list_chats(data)

with st.sidebar:
    st.divider()
    if len(chats) == 1:
        chat = chats[0]
        st.success(f"Single-chat export: **{chat.name}**")
    else:
        st.success(f"Full archive: **{len(chats)} chats**")
        type_filter = st.multiselect(
            "Filter by type",
            sorted({c.type for c in chats}),
            default=[],
            help="Empty = all types",
        )
        filtered = [c for c in chats if not type_filter or c.type in type_filter]
        # Selectbox has built-in search by typing
        idx = st.selectbox(
            "Pick a chat",
            options=range(len(filtered)),
            format_func=lambda i: loader.chat_label(filtered[i]),
        )
        chat = filtered[idx]

    st.divider()

    # Date range filter
    bounds = overview.date_bounds(chat.messages)
    if bounds is not None:
        import datetime as _dt

        min_d = _dt.date.fromisoformat(bounds[0])
        max_d = _dt.date.fromisoformat(bounds[1])
        date_range = st.date_input(
            "Date range",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            help="Limits all analysis to this period.",
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            from_d, to_d = date_range[0].isoformat(), date_range[1].isoformat()
        else:
            from_d, to_d = bounds
        is_filtered = (from_d, to_d) != bounds
    else:
        from_d, to_d = "0000-01-01", "9999-12-31"
        is_filtered = False

    most_com = st.slider("Top words to show", 10, 200, 30, step=5)
    st.caption(f"Chat ID: `{chat.id}`")

# Cache key — change identity when chat or date range changes so caches invalidate
cache_key = f"{json_path}::{chat.id}::{chat.type}::{from_d}::{to_d}"
sections = loader.sections_for_type(chat.type)

# Filter messages once and pass everywhere
if is_filtered:
    messages = _filter_by_date(cache_key, chat.messages, from_d, to_d)
else:
    messages = chat.messages

st.title(chat.name)
st.caption(f"Type: `{chat.type}` · ID: `{chat.id}`")
if is_filtered:
    st.info(
        f"📅 Filtered: {from_d} → {to_d} "
        f"({len(messages):,} of {len(chat.messages):,} messages)"
    )

# KPI row (computed on filtered set)
kpis = _kpis(cache_key, messages)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total messages", f"{kpis.total_messages:,}")
k2.metric("Unique users", f"{kpis.unique_users:,}")
k3.metric("Days active", f"{kpis.days_active:,}")
k4.metric("Media", f"{kpis.media_messages:,}")
k5.metric("Service", f"{kpis.service_messages:,}")
if kpis.first_date and kpis.last_date:
    st.caption(f"📅 {kpis.first_date} → {kpis.last_date}")

if kpis.total_messages == 0:
    st.warning("No messages in selected range.")
    st.stop()

# Build the tab list dynamically based on chat type
tab_specs = []
if "overview" in sections:
    tab_specs.append(("📈 Overview", "overview"))
if "graph" in sections:
    tab_specs.append(("🕸️ Graph", "graph"))
if "words" in sections:
    tab_specs.append(("💬 Words", "words"))
if "channel" in sections:
    tab_specs.append(("📺 Channel", "channel"))
if "perusers" in sections:
    tab_specs.append(("👤 Per-user", "perusers"))
if "highlights" in sections:
    tab_specs.append(("✨ Highlights", "highlights"))

tabs = st.tabs([t[0] for t in tab_specs])

for tab, (_, key) in zip(tabs, tab_specs):
    with tab:
        if key == "overview":
            t0 = time.time()
            per_day = _per_day(cache_key, messages)
            if per_day:
                df = pd.DataFrame(per_day, columns=["date", "messages"])
                df["date"] = pd.to_datetime(df["date"])
                fig = px.area(
                    df,
                    x="date",
                    y="messages",
                    title="Messages per day",
                    template="plotly_dark",
                )
                fig.update_layout(height=350, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig, use_container_width=True)

                # Calendar heatmap (GitHub-style)
                cal_fig = _calendar_heatmap_fig(df)
                if cal_fig is not None:
                    st.plotly_chart(cal_fig, use_container_width=True)
            else:
                st.info("No dated messages.")

            # Hour × weekday heatmap
            grid = _hour_weekday(cache_key, messages)
            if any(any(row) for row in grid):
                weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hours = list(range(24))
                heat = go.Figure(
                    data=go.Heatmap(
                        z=grid,
                        x=hours,
                        y=weekdays,
                        colorscale="Plasma",
                        hovertemplate=("%{y} %{x}:00<br>messages: %{z}<extra></extra>"),
                    )
                )
                heat.update_layout(
                    title="Activity heatmap — hour × weekday",
                    template="plotly_dark",
                    height=300,
                    margin=dict(l=0, r=0, t=40, b=0),
                    xaxis=dict(title="hour", dtick=2),
                    yaxis=dict(title=""),
                )
                st.plotly_chart(heat, use_container_width=True)

            # Active-hours overlap (only for 1-1 chats)
            user_hours = overview.hour_distribution_per_user(messages)
            if len(user_hours) == 2:
                (uid_a, (name_a, hrs_a)), (uid_b, (name_b, hrs_b)) = list(
                    user_hours.items()
                )
                # Normalise per user (so heavy texters don't dominate)
                total_a = sum(hrs_a) or 1
                total_b = sum(hrs_b) or 1
                norm_a = [h / total_a for h in hrs_a]
                norm_b = [h / total_b for h in hrs_b]
                overlap = [min(a, b) for a, b in zip(norm_a, norm_b)]

                fig_ovl = go.Figure()
                fig_ovl.add_trace(
                    go.Bar(
                        x=list(range(24)),
                        y=norm_a,
                        name=name_a,
                        marker_color="rgba(91,143,249,0.6)",
                    )
                )
                fig_ovl.add_trace(
                    go.Bar(
                        x=list(range(24)),
                        y=norm_b,
                        name=name_b,
                        marker_color="rgba(232,100,82,0.6)",
                    )
                )
                fig_ovl.add_trace(
                    go.Bar(
                        x=list(range(24)),
                        y=overlap,
                        name="overlap (both active)",
                        marker_color="rgba(90,216,166,0.95)",
                    )
                )
                fig_ovl.update_layout(
                    title="Active-hours overlap (normalised)",
                    template="plotly_dark",
                    height=320,
                    margin=dict(l=0, r=0, t=40, b=0),
                    xaxis=dict(title="hour", dtick=2),
                    yaxis=dict(title="share of own messages"),
                    barmode="overlay",
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig_ovl, use_container_width=True)
                peak_overlap = max(range(24), key=lambda i: overlap[i])
                st.caption(
                    f"Peak overlap hour: **{peak_overlap}:00** "
                    f"(both write the most around this time). "
                    f"Bars normalised per-user — fair comparison even when "
                    f"one user texts more overall."
                )

            participants = _participants(cache_key, messages)
            if participants:
                st.subheader(f"Participants ({len(participants):,})")
                p_df = pd.DataFrame(
                    participants, columns=["user_id", "name", "messages"]
                )
                # st.dataframe is virtualised — handles 75k rows fine
                st.dataframe(
                    p_df,
                    use_container_width=True,
                    hide_index=True,
                    height=400,
                )

            # Top emojis (chat-wide)
            es = _emojis(cache_key, messages)
            if es.chat_top:
                with st.expander(
                    f"😄 Top emojis · {es.total_emojis:,} total in "
                    f"{es.messages_with_emoji:,} messages"
                ):
                    emo_df = pd.DataFrame(es.chat_top, columns=["emoji", "count"])
                    fig_emo = px.bar(
                        emo_df.head(30),
                        x="emoji",
                        y="count",
                        template="plotly_dark",
                    )
                    fig_emo.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig_emo, use_container_width=True)
                    st.dataframe(
                        emo_df,
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                    )

            # Media / voice / links breakdown
            ms = _media(cache_key, messages)
            if ms.by_kind:
                voice_min = ms.voice_total_seconds // 60
                voice_label = (
                    f"📦 Media · {sum(ms.by_kind.values()):,} msgs · "
                    f"{ms.voice_count:,} voice ({media_mod.humanize_duration(ms.voice_total_seconds)}) · "
                    f"{ms.total_links:,} links"
                )
                with st.expander(voice_label):
                    # Pie chart of message kinds
                    pie_df = pd.DataFrame(
                        [
                            {"kind": media_mod.kind_label(k), "count": v}
                            for k, v in sorted(ms.by_kind.items(), key=lambda x: -x[1])
                        ]
                    )
                    fig_pie = px.pie(
                        pie_df,
                        names="kind",
                        values="count",
                        template="plotly_dark",
                        title="Message types",
                    )
                    fig_pie.update_layout(height=350, margin=dict(l=0, r=0, t=40, b=0))
                    fig_pie.update_traces(
                        textposition="inside", textinfo="percent+label"
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

                    if ms.voice_count:
                        vc1, vc2, vc3 = st.columns(3)
                        vc1.metric("Voice messages", f"{ms.voice_count:,}")
                        vc2.metric(
                            "Voice total",
                            media_mod.humanize_duration(ms.voice_total_seconds),
                        )
                        avg = (
                            ms.voice_total_seconds // ms.voice_count
                            if ms.voice_count
                            else 0
                        )
                        vc3.metric("Voice avg", media_mod.humanize_duration(avg))

                    if ms.top_domains:
                        st.subheader(f"🔗 Top domains ({ms.total_links:,} links total)")
                        dom_df = pd.DataFrame(
                            ms.top_domains, columns=["domain", "count"]
                        )
                        fig_dom = px.bar(
                            dom_df.head(20),
                            x="domain",
                            y="count",
                            template="plotly_dark",
                        )
                        fig_dom.update_layout(
                            height=320, margin=dict(l=0, r=0, t=10, b=0)
                        )
                        st.plotly_chart(fig_dom, use_container_width=True)
                        st.dataframe(
                            dom_df,
                            use_container_width=True,
                            hide_index=True,
                            height=300,
                        )

            # Reply latency (chat-wide)
            lat = _latency(cache_key, messages)
            if lat.overall_seconds:
                with st.expander(
                    f"⏱️ Reply latency · median "
                    f"{latency_mod.humanize_seconds(lat.median_seconds)}, "
                    f"p90 {latency_mod.humanize_seconds(lat.p90_seconds)} "
                    f"({len(lat.overall_seconds):,} replies, capped at 24h)"
                ):
                    lat_minutes = [s / 60 for s in lat.overall_seconds]
                    fig_lat = px.histogram(
                        x=lat_minutes,
                        nbins=80,
                        template="plotly_dark",
                        log_y=True,
                    )
                    fig_lat.update_layout(
                        height=300,
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="minutes to reply",
                        yaxis_title="count (log)",
                    )
                    st.plotly_chart(fig_lat, use_container_width=True)
            st.caption(f"Rendered in {time.time() - t0:.1f}s")

        elif key == "graph":
            t0 = time.time()
            g = _graph_data(cache_key, messages)
            cgraph1, cgraph2 = st.columns(2)
            cgraph1.metric("Nodes", f"{len(g.nodes):,}")
            cgraph2.metric("Edges", f"{len(g.edges):,}")

            if not g.nodes:
                st.info("No participants found in this chat (only service events?).")
            else:
                # Interaction summary (always useful)
                summary = graph_mod.interaction_summary(messages)
                if summary:
                    sdf = pd.DataFrame(summary)
                    sdf_chart = sdf.melt(
                        id_vars=["user"],
                        value_vars=["sent", "replies_sent", "replies_received"],
                        var_name="metric",
                        value_name="count",
                    )
                    fig_int = px.bar(
                        sdf_chart,
                        x="user",
                        y="count",
                        color="metric",
                        barmode="group",
                        template="plotly_dark",
                        title="Who messages, who replies",
                    )
                    fig_int.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0))
                    st.plotly_chart(fig_int, use_container_width=True)
                    st.dataframe(
                        sdf.drop(columns=["user_id"]),
                        use_container_width=True,
                        hide_index=True,
                        height=240,
                    )

                # Force-directed graph only when there's structure to see
                if len(g.nodes) <= 3:
                    st.caption(
                        f"📌 Force-directed graph hidden: only {len(g.nodes)} "
                        f"participants — the bar chart above tells the whole story."
                    )
                else:
                    with st.spinner("Drawing interactive graph…"):
                        html = graph_mod.render_pyvis_html(g, height="700px")
                    if html:
                        import streamlit.components.v1 as components

                        st.subheader("🕸️ Interactive reply graph")
                        components.html(html, height=720, scrolling=False)
                        st.caption(
                            "Drag nodes · scroll to zoom · hover for details. "
                            "Edges merged by reply count, thickness ~ frequency. "
                            "Colours = communities (Louvain modularity)."
                        )
                    else:
                        st.warning(
                            f"Graph too large to render interactively "
                            f"({len(g.nodes)} nodes). Use the CSVs below in Gephi."
                        )

            with st.expander("Download CSVs (Gephi-compatible)"):
                nodes_df = pd.DataFrame(g.nodes, columns=["id", "label", "weight"])
                edges_df = pd.DataFrame(g.edges, columns=["source", "target", "label"])
                c1, c2 = st.columns(2)
                c1.download_button(
                    "nodes.csv",
                    nodes_df.to_csv(index=False),
                    file_name=f"nodes_{chat.id}.csv",
                    mime="text/csv",
                )
                c2.download_button(
                    "edges.csv",
                    edges_df.to_csv(index=False),
                    file_name=f"edges_{chat.id}.csv",
                    mime="text/csv",
                )
            st.caption(f"Rendered in {time.time() - t0:.1f}s")

        elif key == "words":
            t0 = time.time()
            res = _words(cache_key, messages, most_com)

            cwords1, cwords2, cwords3 = st.columns(3)
            cwords1.metric("Users analysed", f"{len(res.users):,}")
            cwords2.metric("Emails", f"{len(res.emails):,}")
            cwords3.metric("Phones", f"{len(res.phones):,}")

            st.subheader(f"Top {len(res.chat_top_words)} words across the chat")
            if res.chat_top_words:
                wc_png = render_mod.wordcloud_png(res.chat_top_words)
                if wc_png:
                    st.image(wc_png, caption="Wordcloud (chat-wide)")

                top_df = pd.DataFrame(res.chat_top_words, columns=["word", "count"])
                fig_top = px.bar(
                    top_df.head(30),
                    x="word",
                    y="count",
                    template="plotly_dark",
                    title=f"Top 30 of {len(top_df)}",
                )
                fig_top.update_layout(height=350, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_top, use_container_width=True)
                st.dataframe(
                    top_df, use_container_width=True, hide_index=True, height=300
                )
                if res.sentiment_available:
                    sarcasm_note = (
                        f" · {res.sarcasm_marked:,} fragments halved by sarcasm-emoji heuristic (🙃🤡🙄💀…)"
                        if res.sarcasm_marked
                        else ""
                    )
                    st.caption(
                        f"Average sentiment "
                        f"(rubert-tiny2-russian-sentiment, RU/EN): "
                        f"{res.chat_avg_sentiment:+.3f} "
                        f"(range −1 negative … +1 positive){sarcasm_note}. "
                        f"⚠ Не понимает сарказм, шутки и слэнг — числа берите со скепсисом."
                    )
                else:
                    st.info(
                        "💡 Sentiment analysis is **disabled** — install optional "
                        "deps to enable RU/EN sentiment scores:\n\n"
                        "```\npip install -r requirements-sentiment.txt\n```\n\n"
                        "Adds ~1GB (torch + transformers) plus a 50MB model on "
                        "first use. Restart Streamlit after install. "
                        "⚠ Модель не выкупает сарказм, шутки и слэнг — это curiosity-фича, не диагностика."
                    )

            # Sentiment over time (chat-wide + per-user)
            if res.sentiment_available and res.dated_scores:
                with st.expander("📊 Sentiment over time"):
                    series_chat = words_mod.sentiment_period_series(
                        res.dated_scores, granularity="week", per_user=False
                    )
                    if series_chat:
                        s_df = pd.DataFrame(series_chat)
                        s_df["period"] = pd.to_datetime(s_df["period"])
                        fig_chat = px.line(
                            s_df,
                            x="period",
                            y="avg",
                            template="plotly_dark",
                            markers=True,
                            title="Chat-wide weekly average sentiment",
                        )
                        fig_chat.add_hline(y=0, line_dash="dot", line_color="gray")
                        fig_chat.update_layout(
                            height=320,
                            margin=dict(l=0, r=0, t=40, b=0),
                            yaxis_title="avg compound",
                        )
                        st.plotly_chart(fig_chat, use_container_width=True)

                    # per-user overlay if 2+ users
                    if len(res.users) >= 2:
                        per_u = words_mod.sentiment_period_series(
                            res.dated_scores, granularity="week", per_user=True
                        )
                        if per_u:
                            u_df = pd.DataFrame(per_u)
                            u_df["period"] = pd.to_datetime(u_df["period"])
                            u_df["user"] = u_df["user_id"].map(
                                lambda uid: (
                                    res.users.get(uid).name
                                    if res.users.get(uid)
                                    else uid
                                )
                            )
                            fig_u = px.line(
                                u_df,
                                x="period",
                                y="avg",
                                color="user",
                                template="plotly_dark",
                                markers=True,
                                title="Per-user weekly average sentiment",
                            )
                            fig_u.add_hline(y=0, line_dash="dot", line_color="gray")
                            fig_u.update_layout(
                                height=380,
                                margin=dict(l=0, r=0, t=40, b=0),
                                yaxis_title="avg compound",
                                legend_title="",
                            )
                            st.plotly_chart(fig_u, use_container_width=True)
                    st.caption(
                        "⚠ Sentiment не выкупает сарказм, шутки и слэнг. "
                        "Используй для тренда, не для абсолютных значений."
                    )

            # Extreme messages drill-down
            if res.sentiment_available and res.users:
                st.subheader("🎯 Extreme messages")
                # Build a flat list of (text, sentiment, user_name)
                all_msgs = []
                for u in res.users.values():
                    for txt, s in u.messages:
                        if isinstance(s, float) and txt and abs(s) > 0.05:
                            all_msgs.append((txt, s, u.name))
                if all_msgs:
                    extr_n = st.slider(
                        "How many extremes to show",
                        5,
                        50,
                        10,
                        step=5,
                        key="extr_n",
                    )
                    most_pos = sorted(all_msgs, key=lambda r: -r[1])[:extr_n]
                    most_neg = sorted(all_msgs, key=lambda r: r[1])[:extr_n]
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        st.caption(f"💚 Most positive ({extr_n})")
                        st.dataframe(
                            pd.DataFrame(
                                most_pos, columns=["text", "sentiment", "user"]
                            ),
                            use_container_width=True,
                            hide_index=True,
                            height=400,
                        )
                    with ec2:
                        st.caption(f"💔 Most negative ({extr_n})")
                        st.dataframe(
                            pd.DataFrame(
                                most_neg, columns=["text", "sentiment", "user"]
                            ),
                            use_container_width=True,
                            hide_index=True,
                            height=400,
                        )

            # Word trend over time
            st.subheader("📈 Word usage over time")
            term_input = st.text_input(
                "Words to track (comma-separated)",
                placeholder="например: привет, спасибо, люблю",
                key="word_trend_input",
            )
            if term_input.strip():
                terms = [t.strip() for t in term_input.split(",") if t.strip()]
                granularity = st.radio(
                    "Granularity",
                    ["week", "day", "month"],
                    index=0,
                    horizontal=True,
                    key="word_trend_gran",
                )
                with st.spinner("Counting…"):
                    trends = words_mod.word_timeline(
                        messages, terms, granularity=granularity
                    )
                series_rows = []
                for term, series in trends.items():
                    for date_iso, count in series:
                        series_rows.append(
                            {"date": date_iso, "count": count, "term": term}
                        )
                if series_rows:
                    tdf = pd.DataFrame(series_rows)
                    tdf["date"] = pd.to_datetime(tdf["date"])
                    fig_tr = px.line(
                        tdf,
                        x="date",
                        y="count",
                        color="term",
                        template="plotly_dark",
                        markers=True,
                    )
                    fig_tr.update_layout(
                        height=380,
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend_title="",
                    )
                    st.plotly_chart(fig_tr, use_container_width=True)
                    totals = (
                        tdf.groupby("term")["count"]
                        .sum()
                        .reset_index()
                        .sort_values("count", ascending=False)
                    )
                    st.dataframe(
                        totals,
                        use_container_width=True,
                        hide_index=True,
                        height=200,
                    )
                else:
                    st.caption("No matches.")

            # Vocabulary richness (TTR)
            if res.users and any(u.total_tokens > 0 for u in res.users.values()):
                st.subheader("🧠 Vocabulary richness")
                voc_rows = [
                    {
                        "user": u.name,
                        "total_tokens": u.total_tokens,
                        "unique_tokens": u.unique_tokens,
                        "TTR": round(u.ttr, 3),
                    }
                    for u in res.users.values()
                    if u.total_tokens > 0
                ]
                voc_df = pd.DataFrame(voc_rows).sort_values(
                    "total_tokens", ascending=False
                )
                st.caption(
                    "TTR = unique / total tokens (after stop-word filtering). "
                    "Higher = more diverse vocabulary. "
                    "TTR is length-sensitive — shorter samples score higher; "
                    "compare users with similar token counts."
                )
                st.dataframe(
                    voc_df,
                    use_container_width=True,
                    hide_index=True,
                    height=240,
                )

            if res.users:
                st.subheader("Per-user")
                user_options = sorted(
                    res.users.values(),
                    key=lambda u: -len(u.messages),
                )
                pick = st.selectbox(
                    "User",
                    options=user_options,
                    format_func=lambda u: f"{u.name} · {len(u.messages):,} msgs",
                )
                if pick is not None:
                    if pick.top_words:
                        u_wc = render_mod.wordcloud_png(pick.top_words)
                        if u_wc:
                            st.image(u_wc, caption=f"Wordcloud — {pick.name}")
                    cu1, cu2 = st.columns(2)
                    with cu1:
                        if res.sentiment_available:
                            st.caption(
                                f"Average sentiment: {pick.avg_sentiment:+.2f} "
                                f"⚠ не учитывает сарказм/шутки/слэнг"
                            )
                        if pick.top_words:
                            tw = pd.DataFrame(pick.top_words, columns=["word", "count"])
                            st.dataframe(
                                tw,
                                use_container_width=True,
                                hide_index=True,
                                height=300,
                            )
                    with cu2:
                        if res.sentiment_available:
                            m_df = pd.DataFrame(
                                pick.messages,
                                columns=["text", "sentiment"],
                            )
                        else:
                            m_df = pd.DataFrame(
                                [(t,) for t, _ in pick.messages],
                                columns=["text"],
                            )
                        st.caption(f"All {len(m_df):,} message fragments")
                        st.dataframe(
                            m_df,
                            use_container_width=True,
                            hide_index=True,
                            height=400,
                        )

            if res.emails or res.phones:
                with st.expander(
                    f"Found contacts: {len(res.emails)} emails, "
                    f"{len(res.phones)} phones"
                ):
                    cc1, cc2 = st.columns(2)
                    cc1.dataframe(
                        pd.DataFrame(res.emails, columns=["email"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                    cc2.dataframe(
                        pd.DataFrame(res.phones, columns=["phone"]),
                        use_container_width=True,
                        hide_index=True,
                    )
            st.caption(f"Rendered in {time.time() - t0:.1f}s")

        elif key == "channel":
            t0 = time.time()
            res = _channel(cache_key, messages, most_com)
            cc1, cc2 = st.columns(2)
            cc1.metric("Top words", f"{len(res.top_words):,}")
            cc2.metric("Tokens (raw)", f"{res.token_count:,}")

            if res.wordcloud_png:
                st.image(res.wordcloud_png, caption="Wordcloud")
            else:
                st.info("Not enough text for a wordcloud.")

            if res.top_words:
                top_df = pd.DataFrame(res.top_words, columns=["word", "count"])
                fig_top = px.bar(
                    top_df.head(50),
                    x="word",
                    y="count",
                    template="plotly_dark",
                    title=f"Top 50 of {len(top_df)}",
                )
                fig_top.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_top, use_container_width=True)
                st.dataframe(
                    top_df, use_container_width=True, hide_index=True, height=400
                )
            st.caption(f"Rendered in {time.time() - t0:.1f}s")

        elif key == "perusers":
            t0 = time.time()
            participants = _participants(cache_key, messages)
            if not participants:
                st.info("No identifiable participants in this chat.")
            else:
                # Pick a user
                pu_options = participants  # already sorted desc by msg count
                pick_idx = st.selectbox(
                    "Pick a user",
                    options=range(len(pu_options)),
                    format_func=lambda i: (
                        f"{pu_options[i][1]} · {pu_options[i][2]:,} msgs"
                    ),
                    key="pu_pick",
                )
                user_id, user_name, user_msg_count = pu_options[pick_idx]

                # Filter messages by this user once
                user_msgs = [
                    m
                    for m in messages
                    if isinstance(m, dict)
                    and (m.get("from_id") == user_id or m.get("actor_id") == user_id)
                ]

                pu_k1, pu_k2, pu_k3 = st.columns(3)
                pu_k1.metric("User", user_name)
                pu_k2.metric("Messages", f"{user_msg_count:,}")
                pu_k3.metric(
                    "Share of chat",
                    f"{100 * user_msg_count / max(kpis.total_messages, 1):.1f}%",
                )

                # Speaking style
                speak = _speaking(cache_key, messages)
                style = speak.get(user_id)
                if style is not None:
                    st.subheader("✍️ Speaking style")
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Avg msg length", f"{style.avg_chars:.0f} chars")
                    s2.metric("Avg words/msg", f"{style.avg_words:.1f}")
                    s3.metric("Median chars", f"{style.median_chars:,}")
                    s4.metric("Longest", f"{style.longest_chars:,} chars")
                    s5, s6, s7 = st.columns(3)
                    s5.metric(
                        "Question rate",
                        f"{style.question_ratio * 100:.1f}%",
                        help="Share of messages containing '?'",
                    )
                    s6.metric(
                        "Exclamation rate",
                        f"{style.exclamation_ratio * 100:.1f}%",
                        help="Share of messages containing '!'",
                    )
                    s7.metric(
                        "ALL-CAPS rate",
                        f"{style.caps_ratio * 100:.1f}%",
                        help="Share of messages where >60% of letters are uppercase (≥5 letters)",
                    )
                    if style.longest_text:
                        with st.expander(
                            f"📜 Longest message ({style.longest_chars:,} chars)"
                        ):
                            st.text(style.longest_text[:5000])
                            if len(style.longest_text) > 5000:
                                st.caption(
                                    f"… (truncated, full length {style.longest_chars:,})"
                                )

                # Daily timeline
                pu_per_day = overview.messages_per_day(user_msgs)
                if pu_per_day:
                    pu_df = pd.DataFrame(pu_per_day, columns=["date", "messages"])
                    pu_df["date"] = pd.to_datetime(pu_df["date"])
                    fig_pu = px.area(
                        pu_df,
                        x="date",
                        y="messages",
                        template="plotly_dark",
                        title=f"{user_name} — daily activity",
                    )
                    fig_pu.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0))
                    st.plotly_chart(fig_pu, use_container_width=True)

                # Hour × weekday
                pu_grid = overview.hour_weekday_heatmap(user_msgs)
                if any(any(row) for row in pu_grid):
                    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                    heat = go.Figure(
                        data=go.Heatmap(
                            z=pu_grid,
                            x=list(range(24)),
                            y=weekdays,
                            colorscale="Plasma",
                            hovertemplate=(
                                "%{y} %{x}:00<br>messages: %{z}<extra></extra>"
                            ),
                        )
                    )
                    heat.update_layout(
                        title=f"{user_name} — hour × weekday",
                        template="plotly_dark",
                        height=280,
                        margin=dict(l=0, r=0, t=40, b=0),
                        xaxis=dict(title="hour", dtick=2),
                    )
                    st.plotly_chart(heat, use_container_width=True)

                col_a, col_b = st.columns(2)

                # Top emojis for this user
                with col_a:
                    es = _emojis(cache_key, messages)
                    user_emo = es.per_user.get(user_id, [])
                    st.subheader("😄 Top emojis")
                    if user_emo:
                        emo_df = pd.DataFrame(user_emo, columns=["emoji", "count"])
                        st.dataframe(
                            emo_df,
                            use_container_width=True,
                            hide_index=True,
                            height=300,
                        )
                    else:
                        st.caption("No emojis found.")

                # Reply latency for this user (responder)
                with col_b:
                    lat = _latency(cache_key, messages)
                    user_lats = lat.per_user_seconds.get(user_id, [])
                    st.subheader("⏱️ Reply latency")
                    if user_lats:
                        sorted_lats = sorted(user_lats)
                        median = sorted_lats[len(sorted_lats) // 2]
                        p90 = sorted_lats[int(len(sorted_lats) * 0.9)]
                        st.caption(
                            f"Median {latency_mod.humanize_seconds(median)} · "
                            f"p90 {latency_mod.humanize_seconds(p90)} · "
                            f"{len(user_lats):,} replies"
                        )
                        fig_lat_pu = px.histogram(
                            x=[s / 60 for s in user_lats],
                            nbins=60,
                            template="plotly_dark",
                            log_y=True,
                        )
                        fig_lat_pu.update_layout(
                            height=260,
                            margin=dict(l=0, r=0, t=10, b=0),
                            xaxis_title="minutes",
                            yaxis_title="count (log)",
                        )
                        st.plotly_chart(fig_lat_pu, use_container_width=True)
                    else:
                        st.caption("No replies recorded for this user.")

                # Top words for this user (reuse words analyzer)
                wres = _words(cache_key, messages, most_com)
                user_stat = wres.users.get(user_id)
                if user_stat and user_stat.total_tokens > 0:
                    vk1, vk2, vk3 = st.columns(3)
                    vk1.metric("Total tokens", f"{user_stat.total_tokens:,}")
                    vk2.metric("Unique tokens", f"{user_stat.unique_tokens:,}")
                    vk3.metric(
                        "TTR (diversity)",
                        f"{user_stat.ttr:.3f}",
                        help="Type-token ratio. 1.0 = every word is unique. "
                        "Length-sensitive: shorter samples score higher.",
                    )
                if user_stat and user_stat.top_words:
                    st.subheader(f"💬 Top {len(user_stat.top_words)} words")
                    u_wc = render_mod.wordcloud_png(user_stat.top_words)
                    if u_wc:
                        st.image(u_wc, caption=f"Wordcloud — {user_name}")
                    tw_df = pd.DataFrame(user_stat.top_words, columns=["word", "count"])
                    st.dataframe(
                        tw_df,
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                    )

                # Per-user extreme messages
                if user_stat and wres.sentiment_available and user_stat.messages:
                    user_msgs_scored = [
                        (txt, s)
                        for txt, s in user_stat.messages
                        if isinstance(s, float) and txt and abs(s) > 0.05
                    ]
                    if user_msgs_scored:
                        st.subheader(f"🎯 {user_name}'s extreme messages")
                        u_extr_n = st.slider(
                            "How many",
                            5,
                            30,
                            10,
                            step=5,
                            key=f"extr_pu_{user_id}",
                        )
                        u_pos = sorted(user_msgs_scored, key=lambda r: -r[1])[:u_extr_n]
                        u_neg = sorted(user_msgs_scored, key=lambda r: r[1])[:u_extr_n]
                        e1, e2 = st.columns(2)
                        with e1:
                            st.caption(f"💚 {user_name}'s most positive")
                            st.dataframe(
                                pd.DataFrame(u_pos, columns=["text", "sentiment"]),
                                use_container_width=True,
                                hide_index=True,
                                height=320,
                            )
                        with e2:
                            st.caption(f"💔 {user_name}'s most negative")
                            st.dataframe(
                                pd.DataFrame(u_neg, columns=["text", "sentiment"]),
                                use_container_width=True,
                                hide_index=True,
                                height=320,
                            )
            st.caption(f"Rendered in {time.time() - t0:.1f}s")

        elif key == "highlights":
            t0 = time.time()
            st.subheader(
                f"✨ {chat.name} — highlights"
                + (f" · {from_d} → {to_d}" if is_filtered else "")
            )

            # Big KPIs at the top
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Messages", f"{kpis.total_messages:,}")
            h2.metric("Days active", f"{kpis.days_active:,}")
            ms_h = _media(cache_key, messages)
            voice_total_min = ms_h.voice_total_seconds // 60
            h3.metric(
                "Voice talked",
                media_mod.humanize_duration(ms_h.voice_total_seconds),
            )
            h4.metric("Links shared", f"{ms_h.total_links:,}")

            # Most active day
            per_day_h = _per_day(cache_key, messages)
            if per_day_h:
                most_active = max(per_day_h, key=lambda r: r[1])
                st.markdown(
                    f"📅 **Most active day:** `{most_active[0]}` — "
                    f"**{most_active[1]:,}** messages"
                )

            # Peak hour overall
            grid_h = _hour_weekday(cache_key, messages)
            total_by_hour = [sum(grid_h[wd][h] for wd in range(7)) for h in range(24)]
            peak_h = max(range(24), key=lambda i: total_by_hour[i])
            st.markdown(
                f"🕒 **Peak chat hour:** `{peak_h}:00` "
                f"({total_by_hour[peak_h]:,} messages)"
            )

            # Top 3 emojis
            es_h = _emojis(cache_key, messages)
            if es_h.chat_top:
                top3_emoji = " ".join(f"{e} ({c:,})" for e, c in es_h.chat_top[:5])
                st.markdown(f"😄 **Top emojis:** {top3_emoji}")

            # Top 3 link domains
            if ms_h.top_domains:
                top3_dom = ", ".join(f"`{d}` ({c})" for d, c in ms_h.top_domains[:5])
                st.markdown(f"🔗 **Top domains:** {top3_dom}")

            # Reply latency snapshot
            lat_h = _latency(cache_key, messages)
            if lat_h.overall_seconds:
                st.markdown(
                    f"⏱️ **Reply speed:** median "
                    f"`{latency_mod.humanize_seconds(lat_h.median_seconds)}`, "
                    f"p90 `{latency_mod.humanize_seconds(lat_h.p90_seconds)}` "
                    f"({len(lat_h.overall_seconds):,} replies)"
                )

            # Speaking style snapshot
            speak_h = _speaking(cache_key, messages)
            if speak_h:
                st.markdown("✍️ **Speaking style:**")
                style_rows = []
                for s in sorted(speak_h.values(), key=lambda s: -s.msg_count):
                    style_rows.append(
                        {
                            "user": s.name,
                            "msgs": s.msg_count,
                            "avg chars": round(s.avg_chars, 1),
                            "median": s.median_chars,
                            "Q%": round(s.question_ratio * 100, 1),
                            "!%": round(s.exclamation_ratio * 100, 1),
                            "CAPS%": round(s.caps_ratio * 100, 1),
                        }
                    )
                st.dataframe(
                    pd.DataFrame(style_rows),
                    use_container_width=True,
                    hide_index=True,
                )

            # Words highlight: top 30 chat-wide
            wres_h = _words(cache_key, messages, most_com)
            if wres_h.chat_top_words:
                wc_h = render_mod.wordcloud_png(wres_h.chat_top_words)
                if wc_h:
                    st.markdown("💬 **Word cloud:**")
                    st.image(wc_h, caption=None)

            # Extreme messages (only when sentiment is on)
            if wres_h.sentiment_available:
                all_extr = []
                for u in wres_h.users.values():
                    for txt, s in u.messages:
                        if isinstance(s, float) and abs(s) > 0.3 and txt:
                            all_extr.append((txt, s, u.name))
                if all_extr:
                    most_pos = sorted(all_extr, key=lambda r: -r[1])[:5]
                    most_neg = sorted(all_extr, key=lambda r: r[1])[:5]
                    eh1, eh2 = st.columns(2)
                    eh1.markdown("💚 **Top 5 positive moments**")
                    eh1.dataframe(
                        pd.DataFrame(most_pos, columns=["text", "sentiment", "user"]),
                        use_container_width=True,
                        hide_index=True,
                        height=240,
                    )
                    eh2.markdown("💔 **Top 5 negative moments**")
                    eh2.dataframe(
                        pd.DataFrame(most_neg, columns=["text", "sentiment", "user"]),
                        use_container_width=True,
                        hide_index=True,
                        height=240,
                    )

            st.caption(f"Rendered in {time.time() - t0:.1f}s")
