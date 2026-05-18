"""
Vilia Economy & Population Simulator  v2
=========================================
Gold is a CURRENCY, not a traded commodity.

  - States mine gold each tick → accumulated in state treasury.
  - Food and stone are traded.  Payment is settled in gold at a
    dynamically-priced market rate (supply/demand per resource).
  - A state with an empty treasury cannot buy imports.
    Unmet food deficit → starvation penalty on pop growth.
    Unmet stone deficit → construction penalty (slower growth ceiling).
  - Lotka-Volterra monster / human predator-prey dynamics.

Run:
    python villiatestdashboard_v2.py                       # procedural world
    python villiatestdashboard_v2.py --json ViliaFull.json
    python villiatestdashboard_v2.py --ticks 500 --density 0.05
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from typing import Dict, List, Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Biome yield tables
# ---------------------------------------------------------------------------
GRAIN_BIOME = {
    0: 0.00, 1: 0.05, 2: 0.05,  3: 0.80,  4: 1.00,
    5: 1.15, 6: 1.15, 7: 1.44,  8: 1.34,  9: 0.40,
   10: 0.20, 11: 0.06, 12: 1.12,
}
STONE_BIOME = {
    0: 0.00, 1: 0.13, 2: 1.15,  3: 0.50,  4: 0.40,
    5: 0.12, 6: 0.23, 7: 0.08,  8: 0.21,  9: 0.40,
   10: 0.70, 11: 0.06, 12: 0.30,
}
GOLD_BIOME = {
    0: 0.00, 1: 0.06, 2: 0.65,  3: 0.25,  4: 0.20,
    5: 0.06, 6: 0.11, 7: 0.04,  8: 0.10,  9: 0.20,
   10: 0.35, 11: 0.03, 12: 0.15,
}

# ---------------------------------------------------------------------------
# Demand (food & stone per unit population)
# Gold is not demanded — it is earned and spent.
# ---------------------------------------------------------------------------
BASE_DEMAND = {"food": 0.5, "stone": 0.2}   # gold removed from demand loop

# ---------------------------------------------------------------------------
# Market pricing
# ---------------------------------------------------------------------------
# Starting price in gold per unit of each traded resource.
BASE_PRICE = {"food": 1.0, "stone": 2.0}

# How fast prices adjust toward the supply/demand signal each tick.
# 0.0 = fixed prices, 1.0 = instant adjustment.
PRICE_ADAPT_RATE = 0.15

# Min / max price bounds (gold per unit) to prevent runaway deflation/inflation.
PRICE_MIN = {"food": 0.1, "stone": 0.2}
PRICE_MAX = {"food": 20.0, "stone": 40.0}

# ---------------------------------------------------------------------------
# Resource replenishment
# ---------------------------------------------------------------------------
STONE_REPLENISH_RATE = 0.002   # fraction of stone_max restored per tick
GOLD_REPLENISH_RATE  = 0.0005  # fraction of gold_max  restored per tick

# ---------------------------------------------------------------------------
# War trade
# ---------------------------------------------------------------------------
WAR_TRADE_MUL = 0.0
WAR_STATUS    = "war"

# ---------------------------------------------------------------------------
# Population / Lotka-Volterra constants
# ---------------------------------------------------------------------------
FOOD_PER_POP        = 1.0
GROWTH_RATE_BASE    = 0.02
STARVATION_RATE     = 0.05
# Stone deprivation damps the carrying-capacity ceiling
# (no construction materials → can't grow cities)
STONE_PENALTY_RATE  = 0.01     # extra negative growth when stone deficit unmet
CARRYING_CAPACITY_K = 500.0
MIN_CELL_POP        = 0.001

DEFAULT_LV = dict(alpha=0.10, mu=0.08, beta=0.02, delta=0.01, gamma=0.08)

TRADE_RESOURCES = ["food", "stone"]   # resources actually traded for gold

STATE_COLORS = [
    "#378ADD", "#D85A30", "#1D9E75", "#BA7517",
    "#993556", "#534AB7", "#3B6D11", "#888780",
    "#5DCAA5", "#F09595", "#EF9F27", "#AFA9EC",
]


# ---------------------------------------------------------------------------
# World object
# ---------------------------------------------------------------------------
class ViliaEconomy:
    def __init__(self, fmg_json: dict):
        pack            = fmg_json["pack"]
        self.routes     = pack.get("routes", [])
        self.biomes     = fmg_json.get("biomesData", {})
        self.states     = [s for s in pack["states"]    if isinstance(s, dict)]
        self.provinces  = [p for p in pack.get("provinces", []) if isinstance(p, dict)]
        self.cells      = [c for c in pack["cells"]     if isinstance(c, dict)]
        self.year       = fmg_json.get("settings", {}).get("options", {}).get("year", 1)

        # Dynamic market prices (gold per unit) — mutated each tick
        self.prices: Dict[str, float] = dict(BASE_PRICE)

        # State treasuries: state_i → gold amount
        self.treasury: Dict[int, float] = {}


def load_from_file(path: str) -> ViliaEconomy:
    with open(path, "r", encoding="utf-8") as f:
        world = ViliaEconomy(json.load(f))
    _init_reserves(world)
    _init_treasuries(world)
    return world


# ---------------------------------------------------------------------------
# Reserve & treasury initialisation
# ---------------------------------------------------------------------------
def _init_reserves(world: ViliaEconomy):
    """
    Seed stone_reserve / gold_reserve for every habitable cell.
    stone_max / gold_max are stored so replenishment has a ceiling.
    """
    STONE_YEARS = 2000
    GOLD_YEARS  = 500

    for c in world.cells:
        if c.get("h", 0) <= 20:
            c["stone_reserve"] = c["stone_max"] = 0.0
            c["gold_reserve"]  = c["gold_max"]  = 0.0
            continue
        biome = c.get("biome", 0)
        h     = c.get("height", c.get("h", 0))
        river = c.get("river", False)
        coast = c.get("coast", False)

        st = STONE_BIOME.get(biome, 0)
        if river: st *= 1.2
        if coast: st *= 0.8
        st *= 1 + h / 1000

        gd = GOLD_BIOME.get(biome, 0)
        if river: gd *= 1.6
        if coast: gd *= 0.8
        gd *= 1 + h / 1000

        c["stone_max"]     = st * STONE_YEARS
        c["gold_max"]      = gd * GOLD_YEARS
        c["stone_reserve"] = c["stone_max"]
        c["gold_reserve"]  = c["gold_max"]


def _init_treasuries(world: ViliaEconomy):
    """
    Give each state a starting treasury equal to ~20 ticks of gold income
    at base yields (no pop multiplier) so early-game trade isn't blocked.
    """
    for s in world.states:
        sid   = s["i"]
        total = 0.0
        for c in world.cells:
            if c.get("state") != sid or c.get("h", 0) <= 20:
                continue
            biome = c.get("biome", 0)
            h     = c.get("height", c.get("h", 0))
            river = c.get("river", False)
            coast = c.get("coast", False)
            gd = GOLD_BIOME.get(biome, 0)
            if river: gd *= 1.6
            if coast: gd *= 0.8
            gd *= 1 + h / 1000
            total += gd
        world.treasury[sid] = total * 20.0

# ---------------------------------------------------------------------------
# Diplomacy helpers
# ---------------------------------------------------------------------------
def get_at_war_pairs(world: ViliaEconomy) -> set:
    at_war = set()
    for s in world.states:
        sid = s.get("i")
        for oid, status in enumerate(s.get("diplomacy", [])):
            if isinstance(status, str) and status.lower() == WAR_STATUS:
                at_war.add(frozenset((sid, oid)))
    return at_war


# ---------------------------------------------------------------------------
# Economy tick
# ---------------------------------------------------------------------------
def tick(world: ViliaEconomy) -> tuple[dict, dict, dict]:
    """
    One simulation step.

    Returns
    -------
    production  : {state_name: {"food": float, "stone": float}}
                  Post-trade food & stone per state.
    gold_mined  : {state_name: float}
                  Gold extracted this tick (added to treasury externally).
    trade_flows : {state_name: {"food": float, "stone": float, "gold_spent": float, "gold_earned": float}}
                  Net flow this tick — positive = received / earned.
    unmet       : {state_name: {"food": float, "stone": float}}
                  Deficit that could not be covered (seller willing but buyer broke).
    """
    name_to_id = {s["name"]: s["i"] for s in world.states}
    id_to_name = {s["i"]: s["name"] for s in world.states}
    war_pairs  = get_at_war_pairs(world)

    # ------------------------------------------------------------------
    # 1. Raw production — food, stone, gold (all from cell loops)
    # ------------------------------------------------------------------
    production = {s["name"]: {"food": 0.0, "stone": 0.0} for s in world.states}
    gold_mined = {s["name"]: 0.0 for s in world.states}

    for c in world.cells:
        if c.get("h", 0) <= 20:
            continue
        sid   = c.get("state")
        sname = id_to_name.get(sid)
        if sname is None:
            continue
        biome = c.get("biome", 0)
        h     = c.get("height", c.get("h", 0))
        pop   = c.get("pop", 0)

        # Food — renewable, no reserve
        g = GRAIN_BIOME.get(biome, 0)
        if c.get("river"): g *= 1.2
        if c.get("coast"): g *= 1.1
        if pop > 0: g *= 1 + pop
        g -= h * 0.01
        production[sname]["food"] += max(g, 0)

        # Stone — replenish then extract
        c["stone_reserve"] = min(
            c.get("stone_reserve", 0) + c.get("stone_max", 0) * STONE_REPLENISH_RATE,
            c.get("stone_max", 0),
        )
        st = STONE_BIOME.get(biome, 0)
        if c.get("river"): st *= 1.2
        if c.get("coast"): st *= 0.8
        if pop > 0: st *= 1 + pop
        st *= 1 + h / 1000
        actual_st = min(st, c.get("stone_reserve", 0))
        c["stone_reserve"] = max(c.get("stone_reserve", 0) - actual_st, 0)
        production[sname]["stone"] += actual_st

        # Gold — replenish then extract → goes to treasury, not to "production"
        c["gold_reserve"] = min(
            c.get("gold_reserve", 0) + c.get("gold_max", 0) * GOLD_REPLENISH_RATE,
            c.get("gold_max", 0),
        )
        gd = GOLD_BIOME.get(biome, 0)
        if c.get("river"): gd *= 1.6
        if c.get("coast"): gd *= 0.8
        if pop > 0: gd *= 1 + pop
        gd *= 1 + h / 1000
        actual_gd = min(gd, c.get("gold_reserve", 0))
        c["gold_reserve"] = max(c.get("gold_reserve", 0) - actual_gd, 0)
        gold_mined[sname] += actual_gd

    # Deposit mined gold into treasuries immediately
    for s in world.states:
        world.treasury[s["i"]] = world.treasury.get(s["i"], 0.0) + gold_mined[s["name"]]

    # ------------------------------------------------------------------
    # 2. Update world prices based on global supply vs demand
    #
    # price_signal = (global_production / global_demand)
    #   ratio < 1  → scarcity  → price rises
    #   ratio > 1  → surplus   → price falls
    #
    # Target price = BASE_PRICE / ratio  (inverse: scarcity multiplies price)
    # We move current price toward target by PRICE_ADAPT_RATE each tick.
    # ------------------------------------------------------------------
    for res in TRADE_RESOURCES:
        global_prod   = sum(production[s["name"]][res] for s in world.states)
        global_demand = sum(
            (s.get("rural", 0) + s.get("urban", 0)) * BASE_DEMAND[res]
            for s in world.states
        )
        if global_demand > 0 and global_prod > 0:
            ratio        = global_prod / global_demand
            target_price = BASE_PRICE[res] / ratio      # scarcity → higher price
            target_price = max(PRICE_MIN[res], min(PRICE_MAX[res], target_price))
            world.prices[res] += PRICE_ADAPT_RATE * (target_price - world.prices[res])
        world.prices[res] = max(PRICE_MIN[res], min(PRICE_MAX[res], world.prices[res]))

    # ------------------------------------------------------------------
    # 3. Gold-mediated trade
    #
    # For each resource:
    #   a) Identify surplus states (exporters) and deficit states (importers).
    #   b) Each importer bids with available gold at current world price.
    #   c) Surplus is allocated proportionally to affordable bids.
    #   d) Gold moves from importer treasury → exporter treasury.
    #   e) Any deficit left over after gold runs out is "unmet".
    # ------------------------------------------------------------------
    trade_flows = {s["name"]: {"food":   0.0, "stone":      0.0,
                               "gold_spent": 0.0, "gold_earned": 0.0}
                  for s in world.states}
    unmet = {s["name"]: {"food": 0.0, "stone": 0.0} for s in world.states}

    for res in TRADE_RESOURCES:
        price = world.prices[res]

        surplus_states = {}   # name → surplus units
        deficit_states = {}   # name → deficit units

        for s in world.states:
            sname  = s["name"]
            pop    = s.get("rural", 0) + s.get("urban", 0)
            demand = pop * BASE_DEMAND[res]
            gap    = production[sname][res] - demand
            if gap > 0:
                surplus_states[sname] = gap
            elif gap < 0:
                deficit_states[sname] = -gap

        if not surplus_states or not deficit_states:
            # No trade possible; record unmet deficits
            for sname, def_amt in deficit_states.items():
                unmet[sname][res] += def_amt
            continue

        for exp_name, avail in surplus_states.items():
            exp_id = name_to_id[exp_name]

            # Each importer's effective bid = min(deficit, affordable units)
            bids = {}
            for imp_name, def_amt in deficit_states.items():
                imp_id = name_to_id[imp_name]
                at_war = frozenset((exp_id, imp_id)) in war_pairs
                if at_war and WAR_TRADE_MUL == 0.0:
                    continue   # embargo — no trade
                treasury = world.treasury.get(imp_id, 0.0)
                affordable = treasury / price if price > 0 else 0.0
                effective  = min(def_amt, affordable)
                if effective > 0:
                    bids[imp_name] = effective

            total_bid = sum(bids.values())
            if total_bid == 0:
                # No one can afford to buy — all deficits are unmet
                for imp_name, def_amt in deficit_states.items():
                    unmet[imp_name][res] += def_amt
                continue

            # Distribute available surplus proportionally to bids
            for imp_name, bid in bids.items():
                imp_id   = name_to_id[imp_name]
                fraction = bid / total_bid
                transfer = avail * fraction   # units of the resource

                gold_cost = transfer * price
                treasury  = world.treasury.get(imp_id, 0.0)
                # Cap by what buyer can actually pay
                if gold_cost > treasury:
                    transfer  = treasury / price
                    gold_cost = treasury

                if transfer <= 0:
                    continue

                # Move resource
                production[exp_name][res] -= transfer
                production[imp_name][res] += transfer

                # Move gold
                world.treasury[imp_id]    = max(world.treasury.get(imp_id,  0.0) - gold_cost, 0.0)
                world.treasury[exp_id]    = world.treasury.get(exp_id, 0.0) + gold_cost

                # Record flows
                trade_flows[exp_name][res]          -= transfer
                trade_flows[imp_name][res]          += transfer
                trade_flows[exp_name]["gold_earned"] += gold_cost
                trade_flows[imp_name]["gold_spent"]  += gold_cost

            # Any importer with no bids still has unmet deficit
            for imp_name, def_amt in deficit_states.items():
                if imp_name not in bids:
                    unmet[imp_name][res] += def_amt

    return production, gold_mined, trade_flows, unmet


# ---------------------------------------------------------------------------
# Food production per cell (for pop update)
# ---------------------------------------------------------------------------
def food_production_per_cell(world: ViliaEconomy) -> dict:
    out = {}
    for c in world.cells:
        if c.get("h", 0) <= 20:
            continue
        g = GRAIN_BIOME.get(c.get("biome", 0), 0)
        if c.get("river"): g *= 1.2
        if c.get("coast"): g *= 1.1
        if c.get("pop", 0) > 0: g *= 1 + c["pop"]
        g -= c.get("height", c.get("h", 0)) * 0.01
        out[c["i"]] = max(g, 0)
    return out


# ---------------------------------------------------------------------------
# Population update (food-driven, stone deprivation penalty)
# ---------------------------------------------------------------------------
def update_population(world: ViliaEconomy,
                      food_map:  Optional[dict] = None,
                      unmet:     Optional[dict] = None):
    """
    Growth is food-driven as before. Additionally:
      - If a state has unmet stone deficit, each cell in that state
        suffers a small extra negative growth (STONE_PENALTY_RATE).
        Rationale: no building materials → disease, crowding, no expansion.
    """
    if food_map is None:
        food_map = food_production_per_cell(world)
    if unmet is None:
        unmet = {}

    # Build a per-state stone penalty scalar (0 = no penalty, 1 = full penalty)
    stone_penalty = {}
    for s in world.states:
        sname    = s["name"]
        pop      = s.get("rural", 0) + s.get("urban", 0)
        demand   = pop * BASE_DEMAND["stone"]
        unmet_st = unmet.get(sname, {}).get("stone", 0.0)
        # Fraction of stone demand unmet → penalty proportional to severity
        stone_penalty[s["i"]] = (unmet_st / demand) if demand > 0 else 0.0

    for c in world.cells:
        pop = c.get("pop", 0)
        if pop <= 0:
            continue
        food_needed   = pop * FOOD_PER_POP
        food_produced = food_map.get(c["i"], 0)
        raw = (food_produced - food_needed) / food_needed if food_needed > 0 else 0.0
        fr  = max(-1.0, min(1.0, raw))

        if fr >= 0:
            brake  = max(0.0, 1.0 - pop / CARRYING_CAPACITY_K)
            growth = GROWTH_RATE_BASE * fr * pop * brake
        else:
            growth = STARVATION_RATE * fr * pop

        # Stone deprivation damps growth (caps city expansion)
        sp = stone_penalty.get(c.get("state", 0), 0.0)
        if sp > 0:
            growth -= STONE_PENALTY_RATE * sp * pop

        c["pop"] = max(pop + growth, MIN_CELL_POP)


# ---------------------------------------------------------------------------
# Lotka-Volterra
# ---------------------------------------------------------------------------
def seed_monsters(world: ViliaEconomy, density: float = 0.05) -> dict:
    return {c["i"]: c["pop"] * density
            for c in world.cells if c.get("pop", 0) > 0 and c.get("h", 0) > 20}


def lv_step(world: ViliaEconomy, monsters: dict, lv: dict):
    alpha, mu, beta, delta, gamma = (lv["alpha"], lv["mu"],
                                     lv["beta"], lv["delta"], lv["gamma"])
    for c in world.cells:
        H = c.get("pop", 0)
        M = monsters.get(c["i"], 0)
        if H <= 0:
            continue
        dH = (alpha - mu) * H - beta * H * M
        dM = delta * beta * H * M - gamma * M
        c["pop"]         = max(H + dH, MIN_CELL_POP)
        monsters[c["i"]] = max(M + dM, 0.0)


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------
def sim_loop(world: ViliaEconomy,
             n_ticks: int = 500,
             lv_params: Optional[dict] = None,
             monster_density: float = 0.05) -> List[dict]:
    if lv_params is None:
        lv_params = DEFAULT_LV.copy()

    monsters = seed_monsters(world, monster_density)
    history  = []

    for t in range(n_ticks):
        food_map                              = food_production_per_cell(world)
        production, gold_mined, trade_flows, unmet = tick(world)
        update_population(world, food_map, unmet)
        lv_step(world, monsters, lv_params)

        total_pop = sum(c.get("pop", 0) for c in world.cells)
        total_mon = sum(monsters.values())

        pop_by_state = defaultdict(float)
        for c in world.cells:
            pop_by_state[c.get("state", 0)] += c.get("pop", 0)

        history.append({
            "tick":           t,
            "production":     {s["name"]: dict(production.get(s["name"], {}))
                               for s in world.states},
            "gold_mined":     {s["name"]: gold_mined.get(s["name"], 0.0)
                               for s in world.states},
            "treasury":       {s["name"]: world.treasury.get(s["i"], 0.0)
                               for s in world.states},
            "trade":          {s["name"]: dict(trade_flows.get(s["name"], {}))
                               for s in world.states},
            "unmet":          {s["name"]: dict(unmet.get(s["name"], {}))
                               for s in world.states},
            "prices":         dict(world.prices),
            "pop_by_state":   dict(pop_by_state),
            "total_pop":      total_pop,
            "total_monsters": total_mon,
        })

    return history


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def build_dashboard(world: ViliaEconomy, history: List[dict]) -> go.Figure:
    states      = world.states
    ticks       = [h["tick"] for h in history]
    state_names = [s["name"] for s in states]
    colors      = [STATE_COLORS[i % len(STATE_COLORS)] for i in range(len(states))]

    # Series helpers
    def prod(res):
        return {s["name"]: [h["production"].get(s["name"], {}).get(res, 0) for h in history]
                for s in states}
    def trd(key):
        return {s["name"]: [h["trade"].get(s["name"], {}).get(key, 0) for h in history]
                for s in states}

    food_series     = prod("food")
    stone_series    = prod("stone")
    gold_mined_s    = {s["name"]: [h["gold_mined"].get(s["name"], 0) for h in history] for s in states}
    treasury_s      = {s["name"]: [h["treasury"].get(s["name"], 0)   for h in history] for s in states}
    unmet_food_s    = {s["name"]: [h["unmet"].get(s["name"], {}).get("food", 0)  for h in history] for s in states}
    unmet_stone_s   = {s["name"]: [h["unmet"].get(s["name"], {}).get("stone", 0) for h in history] for s in states}
    food_trade_s    = trd("food")
    stone_trade_s   = trd("stone")
    gold_spent_s    = trd("gold_spent")
    gold_earned_s   = trd("gold_earned")
    price_food_s    = [h["prices"].get("food",  BASE_PRICE["food"])  for h in history]
    price_stone_s   = [h["prices"].get("stone", BASE_PRICE["stone"]) for h in history]
    global_pop      = [h["total_pop"]      for h in history]
    global_mon      = [h["total_monsters"] for h in history]

    # ---- Layout: 5 rows × 2 cols ------------------------------------------
    # Row 1: Food production       | Stone production
    # Row 2: Gold mined per tick   | State treasuries
    # Row 3: Market prices         | Unmet deficits (food+stone)
    # Row 4: Trade flows (food)    | Trade flows (stone)
    # Row 5: Global human pop      | Global monsters
    fig = make_subplots(
        rows=5, cols=2,
        subplot_titles=(
            "Food production per state",   "Stone production per state",
            "Gold mined per tick",         "State treasury (gold)",
            "Market price (gold/unit)",    "Unmet deficits",
            "Food trade balance",          "Stone trade balance",
            "Global human population",     "Global monster population",
        ),
        vertical_spacing=0.07,
        horizontal_spacing=0.09,
    )

    # --- Row 1 & 2: production + treasury ---
    prod_map = [
        (food_series,   1, 1),
        (stone_series,  1, 2),
        (gold_mined_s,  2, 1),
        (treasury_s,    2, 2),
    ]
    for series, row, col in prod_map:
        for idx, sname in enumerate(state_names):
            fig.add_trace(
                go.Scatter(
                    x=ticks, y=series[sname],
                    name=sname,
                    legendgroup=sname,
                    showlegend=(row == 1 and col == 1),
                    line=dict(color=colors[idx], width=2),
                    hovertemplate=f"<b>{sname}</b><br>Year %{{x}}<br>%{{y:.2f}}<extra></extra>",
                ),
                row=row, col=col,
            )

    # --- Row 3 left: market prices (2 lines, not per-state) ---
    fig.add_trace(
        go.Scatter(x=ticks, y=price_food_s, name="Food price",
                   line=dict(color="#1D9E75", width=2),
                   hovertemplate="Year %{x}<br>Food price: %{y:.3f} gold<extra></extra>",
                   showlegend=True, legendgroup="prices"),
        row=3, col=1,
    )
    fig.add_trace(
        go.Scatter(x=ticks, y=price_stone_s, name="Stone price",
                   line=dict(color="#BA7517", width=2),
                   hovertemplate="Year %{x}<br>Stone price: %{y:.3f} gold<extra></extra>",
                   showlegend=True, legendgroup="prices"),
        row=3, col=1,
    )

    # --- Row 3 right: unmet deficits (stacked bars, one per state per resource) ---
    for idx, sname in enumerate(state_names):
        fig.add_trace(
            go.Bar(x=ticks, y=unmet_food_s[sname],
                   name=sname, legendgroup=sname, showlegend=False,
                   marker_color=colors[idx], opacity=0.6,
                   hovertemplate=f"<b>{sname}</b> unmet food %{{y:.2f}}<extra></extra>"),
            row=3, col=2,
        )
        fig.add_trace(
            go.Bar(x=ticks, y=unmet_stone_s[sname],
                   name=sname, legendgroup=sname, showlegend=False,
                   marker_color=colors[idx], opacity=0.35,
                   hovertemplate=f"<b>{sname}</b> unmet stone %{{y:.2f}}<extra></extra>"),
            row=3, col=2,
        )

    # --- Row 4: trade balance bars ---
    for res, series, col in [("food", food_trade_s, 1), ("stone", stone_trade_s, 2)]:
        for idx, sname in enumerate(state_names):
            fig.add_trace(
                go.Bar(
                    x=ticks, y=series[sname],
                    name=sname, legendgroup=sname, showlegend=False,
                    marker_color=colors[idx], opacity=0.75,
                    hovertemplate=(
                        f"<b>{sname}</b><br>Year %{{x}}<br>"
                        f"Net {res} trade: %{{y:.2f}}<br>"
                        "(+ = received, − = exported)<extra></extra>"
                    ),
                ),
                row=4, col=col,
            )
        fig.add_hline(y=0, line_width=1, line_color="grey", row=4, col=col)

    # --- Row 5: global dynamics ---
    fig.add_trace(
        go.Scatter(x=ticks, y=global_pop, name="Humans",
                   line=dict(color="#378ADD", width=2.5),
                   fill="tozeroy", fillcolor="rgba(55,138,221,0.1)",
                   hovertemplate="Year %{x}<br>Humans: %{y:.1f}<extra></extra>",
                   showlegend=True, legendgroup="global"),
        row=5, col=1,
    )
    fig.add_trace(
        go.Scatter(x=ticks, y=global_mon, name="Monsters",
                   line=dict(color="#D85A30", width=2.5),
                   fill="tozeroy", fillcolor="rgba(216,90,48,0.1)",
                   hovertemplate="Year %{x}<br>Monsters: %{y:.1f}<extra></extra>",
                   showlegend=True, legendgroup="global"),
        row=5, col=2,
    )

    # ---- Axis labels -------------------------------------------------------
    labels = {
        "yaxis":   "Food",     "yaxis2":  "Stone",
        "yaxis3":  "Gold/tick","yaxis4":  "Gold treasury",
        "yaxis5":  "Gold/unit","yaxis6":  "Units unmet",
        "yaxis7":  "Food net", "yaxis8":  "Stone net",
        "yaxis9":  "Humans",   "yaxis10": "Monsters",
    }
    for axis, label in labels.items():
        if axis in fig.layout:
            fig.layout[axis].update(title_text=label)
    for i in range(1, 11):
        axis = "xaxis" if i == 1 else f"xaxis{i}"
        if axis in fig.layout:
            fig.layout[axis].update(title_text="Year")

    fig.update_layout(
        title=dict(text="Vilia Economy & Population Simulator  •  Gold-as-Currency",
                   font=dict(size=20), x=0.5, xanchor="center"),
        height=1700,
        template="plotly_white",
        hovermode="x unified",
        barmode="relative",
        legend=dict(
            title="States",
            orientation="v",
            x=1.02, y=1,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#ddd", borderwidth=1,
        ),
        font=dict(family="sans-serif", size=12),
        margin=dict(l=60, r=160, t=80, b=60),
    )
    return fig


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Vilia Economy Simulator v2")
    parser.add_argument("--json",    type=str,  default=r"C:\Users\dickh\Downloads\New folder\Econ\ViliaFull.json")
    parser.add_argument("--ticks",   type=int,   default=10)
    parser.add_argument("--density", type=float, default=0.05)
    parser.add_argument("--seed",    type=int,   default=42)
    parser.add_argument("--alpha",   type=float, default=0.10)
    parser.add_argument("--mu",      type=float, default=0.08)
    parser.add_argument("--beta",    type=float, default=0.02)
    parser.add_argument("--delta",   type=float, default=0.01)
    parser.add_argument("--gamma",   type=float, default=0.08)
    parser.add_argument("--output",  default=None)
    args = parser.parse_args()

    lv = dict(alpha=args.alpha, mu=args.mu, beta=args.beta,
              delta=args.delta, gamma=args.gamma)

    print("Loading world...")
    if args.json:
        world = load_from_file(args.json)
        print(f"  Loaded {args.json}: {len(world.states)} states, {len(world.cells)} cells")
    else:
        print("Put Path to Exported Map Json")

    print(f"Running {args.ticks} ticks (monster density={args.density})...")
    history = sim_loop(world, n_ticks=args.ticks, lv_params=lv,
                       monster_density=args.density)

    last = history[-1]
    print(f"\n  Final tick {last['tick']}:")
    print(f"    Total population : {last['total_pop']:.1f}")
    print(f"    Total monsters   : {last['total_monsters']:.1f}")
    print(f"    Food price       : {last['prices']['food']:.3f} gold/unit")
    print(f"    Stone price      : {last['prices']['stone']:.3f} gold/unit")
    print(f"\n    {'State':<12}  {'Pop':>7}  {'Food':>7}  {'Stone':>7}  {'Treasury':>10}  {'Unmet F':>8}  {'Unmet S':>8}")
    print(f"    {'-'*70}")
    for s in world.states:
        sn = s["name"]
        ep = last["production"].get(sn, {})
        un = last["unmet"].get(sn, {})
        pp = last["pop_by_state"].get(s["i"], 0)
        tr = last["treasury"].get(sn, 0)
        print(f"    {sn:<12}  {pp:>7.1f}  {ep.get('food',0):>7.2f}  "
              f"{ep.get('stone',0):>7.2f}  {tr:>10.2f}  "
              f"{un.get('food',0):>8.2f}  {un.get('stone',0):>8.2f}")

    print("\nBuilding dashboard...")
    fig = build_dashboard(world, history)
    if args.output:
        fig.write_html(args.output)
        print(f"  Saved to {args.output}")
    else:
        fig.show()


if __name__ == "__main__":
    main()