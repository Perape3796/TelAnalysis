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
from analysis import loader, overview, render as render_mod, words as words_mod

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
    most_com = st.slider("Top words to show", 10, 200, 30, step=5)
    st.caption(f"Chat ID: `{chat.id}`")

# Cache key — change identity when chat changes so caches invalidate
cache_key = f"{json_path}::{chat.id}::{chat.type}"
sections = loader.sections_for_type(chat.type)

st.title(chat.name)
st.caption(f"Type: `{chat.type}` · ID: `{chat.id}`")

# KPI row
kpis = _kpis(cache_key, chat.messages)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total messages", f"{kpis.total_messages:,}")
k2.metric("Unique users", f"{kpis.unique_users:,}")
k3.metric("Days active", f"{kpis.days_active:,}")
k4.metric("Media", f"{kpis.media_messages:,}")
k5.metric("Service", f"{kpis.service_messages:,}")
if kpis.first_date and kpis.last_date:
    st.caption(f"📅 {kpis.first_date} → {kpis.last_date}")

if kpis.total_messages == 0:
    st.warning("This chat has no messages.")
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

tabs = st.tabs([t[0] for t in tab_specs])

for tab, (_, key) in zip(tabs, tab_specs):
    with tab:
        if key == "overview":
            t0 = time.time()
            per_day = _per_day(cache_key, chat.messages)
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
            grid = _hour_weekday(cache_key, chat.messages)
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

            participants = _participants(cache_key, chat.messages)
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
            es = _emojis(cache_key, chat.messages)
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

            # Reply latency (chat-wide)
            lat = _latency(cache_key, chat.messages)
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
            g = _graph_data(cache_key, chat.messages)
            cgraph1, cgraph2 = st.columns(2)
            cgraph1.metric("Nodes", f"{len(g.nodes):,}")
            cgraph2.metric("Edges", f"{len(g.edges):,}")

            if not g.nodes:
                st.info("No participants found in this chat (only service events?).")
            else:
                # Interaction summary (always useful)
                summary = graph_mod.interaction_summary(chat.messages)
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
            res = _words(cache_key, chat.messages, most_com)

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
                st.caption(
                    f"Average sentiment (VADER, English-only): "
                    f"{res.chat_avg_sentiment:+.2f}. "
                    f"For Russian text expect ~0.0 — see TODO."
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
                        st.caption(f"Average sentiment: {pick.avg_sentiment:+.2f}")
                        if pick.top_words:
                            tw = pd.DataFrame(pick.top_words, columns=["word", "count"])
                            st.dataframe(
                                tw,
                                use_container_width=True,
                                hide_index=True,
                                height=300,
                            )
                    with cu2:
                        m_df = pd.DataFrame(
                            pick.messages,
                            columns=["text", "sentiment"],
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
            res = _channel(cache_key, chat.messages, most_com)
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
            participants = _participants(cache_key, chat.messages)
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
                    for m in chat.messages
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
                    es = _emojis(cache_key, chat.messages)
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
                    lat = _latency(cache_key, chat.messages)
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
                wres = _words(cache_key, chat.messages, most_com)
                user_stat = wres.users.get(user_id)
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
            st.caption(f"Rendered in {time.time() - t0:.1f}s")
