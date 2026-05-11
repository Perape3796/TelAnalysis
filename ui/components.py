"""Shared UI helpers: HTML cards, calendar heatmap figure builder.

Pure rendering — no analytics. All functions return Streamlit-renderable
artifacts (HTML strings or plotly Figures), never side-effect into the page.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analysis import theme as theme_mod


def fmt_int(n: int) -> str:
    """Thin-space-grouped integer (Russian convention)."""
    return f"{int(n):,}".replace(",", " ")


def bignum_html(label: str, value: str, context: str = "") -> str:
    ctx = f'<div class="tla-bignum-context">{context}</div>' if context else ""
    return (
        '<div class="tla-bignum">'
        f'<div class="tla-bignum-label">{label}</div>'
        f'<div class="tla-bignum-value">{value}</div>'
        f"{ctx}</div>"
    )


def hero_html(hero, chat_type: str, chat_id) -> str:
    """Render the hero block from HeroData. Used at the top of the page."""
    return (
        f'<div class="tla-hero">'
        f'<h1 class="tla-hero-title">{hero.title}</h1>'
        f'<p class="tla-hero-prose">{hero.prose_html}</p>'
        f'<div class="tla-hero-meta">{hero.meta}  ·  {chat_type}  ·  ID {chat_id}</div>'
        f"</div>"
    )


def highlights_grid_html(items) -> str:
    """Wrap a list of Highlight dataclass instances into the responsive grid."""
    if not items:
        return ""
    cards = "".join(
        '<div class="tla-hl-card">'
        f'<div class="tla-hl-label">{h.label}</div>'
        f'<div class="tla-hl-value">{h.value}</div>'
        f'<div class="tla-hl-sub">{h.sub}</div>'
        "</div>"
        for h in items
    )
    return f'<div class="tla-hl-grid">{cards}</div>'


def calendar_heatmap_fig(df: pd.DataFrame) -> go.Figure | None:
    """GitHub-contributions-style calendar heatmap. df has columns
    ['date', 'messages']. Returns None on empty df."""
    if df is None or len(df) == 0:
        return None
    cal = df.copy()
    cal["date"] = pd.to_datetime(cal["date"])
    full = pd.date_range(cal["date"].min(), cal["date"].max(), freq="D")
    cal = cal.set_index("date").reindex(full, fill_value=0).reset_index()
    cal.columns = ["date", "messages"]
    cal["year"] = cal["date"].dt.year
    cal["weekday"] = cal["date"].dt.weekday
    cal["week"] = cal["date"].dt.isocalendar().week

    years = sorted(cal["year"].unique())
    weekdays_lbl = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    fig = make_subplots(
        rows=len(years),
        cols=1,
        subplot_titles=[str(y) for y in years],
        vertical_spacing=0.08,
    )
    for idx, y in enumerate(years, start=1):
        sub = cal[cal["year"] == y].copy()
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
                colorscale=theme_mod.HEAT_SCALE,
                showscale=(idx == 1),
                hovertemplate="%{y} · week %{x}<br>messages: %{z}<extra></extra>",
            ),
            row=idx,
            col=1,
        )
    fig.update_layout(
        title="Calendar heatmap",
        template="telanalysis",
        height=180 * len(years) + 40,
        margin=dict(l=0, r=0, t=60, b=0),
    )
    for r in range(1, len(years) + 1):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    return fig


__all__ = [
    "fmt_int",
    "bignum_html",
    "hero_html",
    "highlights_grid_html",
    "calendar_heatmap_fig",
]
