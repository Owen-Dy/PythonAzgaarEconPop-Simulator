"""
viz/dashboard.py
----------------
Builds the interactive Plotly dashboard from simulation history.

Layout (5 rows × 2 columns)
----------------------------
Row 1 : Food production per state       | Stone production per state
Row 2 : Gold mined per tick             | State treasury (gold)
Row 3 : Market prices (food & stone)    | Unmet deficits (food & stone)
Row 4 : Food trade balance per state    | Stone trade balance per state
Row 5 : Global human population         | Global monster population
"""

from __future__ import annotations

from typing import List

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from constants import BASE_PRICE, STATE_COLORS
from world.model import ViliaEconomy


def build_dashboard(world: ViliaEconomy, history: List[dict]) -> go.Figure:
    """
    Build and return an interactive Plotly figure from simulation history.

    Parameters
    ----------
    world : ViliaEconomy
        The simulated world (used for state metadata).
    history : list[dict]
        Output of ``simulation.run()``.

    Returns
    -------
    go.Figure
        A Plotly figure ready for ``fig.show()`` or ``fig.write_html()``.
    """
    states      = world.states
    ticks       = [h["tick"] for h in history]
    state_names = [s["name"] for s in states]
    colors      = [STATE_COLORS[i % len(STATE_COLORS)] for i in range(len(states))]

    # ---- Time-series helpers -----------------------------------------------
    def _prod(res: str) -> dict[str, list]:
        return {
            s["name"]: [h["production"].get(s["name"], {}).get(res, 0) for h in history]
            for s in states
        }

    def _trade(key: str) -> dict[str, list]:
        return {
            s["name"]: [h["trade"].get(s["name"], {}).get(key, 0) for h in history]
            for s in states
        }

    food_series   = _prod("food")
    stone_series  = _prod("stone")
    gold_mined_s  = {s["name"]: [h["gold_mined"].get(s["name"], 0)   for h in history] for s in states}
    treasury_s    = {s["name"]: [h["treasury"].get(s["name"], 0)      for h in history] for s in states}
    unmet_food_s  = {s["name"]: [h["unmet"].get(s["name"], {}).get("food",  0) for h in history] for s in states}
    unmet_stone_s = {s["name"]: [h["unmet"].get(s["name"], {}).get("stone", 0) for h in history] for s in states}
    food_trade_s  = _trade("food")
    stone_trade_s = _trade("stone")
    price_food_s  = [h["prices"].get("food",  BASE_PRICE["food"])  for h in history]
    price_stone_s = [h["prices"].get("stone", BASE_PRICE["stone"]) for h in history]
    global_pop    = [h["total_pop"]       for h in history]
    global_mon    = [h["total_monsters"]  for h in history]

    # ---- Figure layout -----------------------------------------------------
    fig = make_subplots(
        rows=5, cols=2,
        subplot_titles=(
            "Food production per state",   "Stone production per state",
            "Gold mined per tick",         "State treasury (gold)",
            "Market price (gold / unit)",  "Unmet deficits",
            "Food trade balance",          "Stone trade balance",
            "Global human population",     "Global monster population",
        ),
        vertical_spacing=0.07,
        horizontal_spacing=0.09,
    )

    # ---- Rows 1 & 2: production + treasury ---------------------------------
    for series, row, col in [
        (food_series,  1, 1),
        (stone_series, 1, 2),
        (gold_mined_s, 2, 1),
        (treasury_s,   2, 2),
    ]:
        for idx, sname in enumerate(state_names):
            fig.add_trace(
                go.Scatter(
                    x=ticks, y=series[sname],
                    name=sname,
                    legendgroup=sname,
                    showlegend=(row == 1 and col == 1),
                    line=dict(color=colors[idx], width=2),
                    hovertemplate=(
                        f"<b>{sname}</b><br>Tick %{{x}}<br>%{{y:.2f}}<extra></extra>"
                    ),
                ),
                row=row, col=col,
            )

    # ---- Row 3 left: market prices (two global lines) ----------------------
    for label, series, color in [
        ("Food price",  price_food_s,  "#1D9E75"),
        ("Stone price", price_stone_s, "#BA7517"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=ticks, y=series,
                name=label,
                line=dict(color=color, width=2),
                hovertemplate=f"Tick %{{x}}<br>{label}: %{{y:.3f}} gold<extra></extra>",
                showlegend=True,
                legendgroup="prices",
            ),
            row=3, col=1,
        )

    # ---- Row 3 right: unmet deficits (stacked bars) ------------------------
    for idx, sname in enumerate(state_names):
        for unmet_series, label, opacity in [
            (unmet_food_s,  "unmet food",  0.70),
            (unmet_stone_s, "unmet stone", 0.35),
        ]:
            fig.add_trace(
                go.Bar(
                    x=ticks, y=unmet_series[sname],
                    name=sname,
                    legendgroup=sname,
                    showlegend=False,
                    marker_color=colors[idx],
                    opacity=opacity,
                    hovertemplate=(
                        f"<b>{sname}</b> {label}: %{{y:.2f}}<extra></extra>"
                    ),
                ),
                row=3, col=2,
            )

    # ---- Row 4: trade balance bars -----------------------------------------
    for res, series, col in [
        ("food",  food_trade_s,  1),
        ("stone", stone_trade_s, 2),
    ]:
        for idx, sname in enumerate(state_names):
            fig.add_trace(
                go.Bar(
                    x=ticks, y=series[sname],
                    name=sname,
                    legendgroup=sname,
                    showlegend=False,
                    marker_color=colors[idx],
                    opacity=0.75,
                    hovertemplate=(
                        f"<b>{sname}</b><br>Tick %{{x}}<br>"
                        f"Net {res} trade: %{{y:.2f}}<br>"
                        "(+ = received, − = exported)<extra></extra>"
                    ),
                ),
                row=4, col=col,
            )
        fig.add_hline(y=0, line_width=1, line_color="grey", row=4, col=col)

    # ---- Row 5: global population dynamics ---------------------------------
    for label, series, color, fill_color in [
        ("Humans",   global_pop, "#378ADD", "rgba(55,138,221,0.1)"),
        ("Monsters", global_mon, "#D85A30", "rgba(216,90,48,0.1)"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=ticks, y=series,
                name=label,
                line=dict(color=color, width=2.5),
                fill="tozeroy",
                fillcolor=fill_color,
                hovertemplate=f"Tick %{{x}}<br>{label}: %{{y:.1f}}<extra></extra>",
                showlegend=True,
                legendgroup="global",
            ),
            row=5, col=1 if label == "Humans" else 2,
        )

    # ---- Axis labels -------------------------------------------------------
    y_labels = {
        "yaxis":   "Food",         "yaxis2":  "Stone",
        "yaxis3":  "Gold / tick",  "yaxis4":  "Gold treasury",
        "yaxis5":  "Gold / unit",  "yaxis6":  "Units unmet",
        "yaxis7":  "Food net",     "yaxis8":  "Stone net",
        "yaxis9":  "Humans",       "yaxis10": "Monsters",
    }
    for axis, label in y_labels.items():
        if axis in fig.layout:
            fig.layout[axis].update(title_text=label)

    for i in range(1, 11):
        axis = "xaxis" if i == 1 else f"xaxis{i}"
        if axis in fig.layout:
            fig.layout[axis].update(title_text="Tick")

    fig.update_layout(
        title=dict(
            text="Vilia Economy & Population Simulator — Gold as Currency",
            font=dict(size=20),
            x=0.5,
            xanchor="center",
        ),
        height=1_700,
        template="plotly_white",
        hovermode="x unified",
        barmode="relative",
        legend=dict(
            title="States",
            orientation="v",
            x=1.02, y=1,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        font=dict(family="sans-serif", size=12),
        margin=dict(l=60, r=160, t=80, b=60),
    )

    return fig
