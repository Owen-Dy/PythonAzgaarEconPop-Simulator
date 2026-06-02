"""
economy/tick.py
---------------
One simulation step of the Vilia economy.

Pipeline
--------
1.  Raw production  — food (renewable), stone & gold (reserve-depleted).
2.  Price update    — world prices adapt toward global supply/demand ratio.
3.  Gold-mediated trade — surplus states sell to deficit states;
    payment settled in gold at current market price.

Trade loop fix
--------------
The original code iterated over *each exporter separately* and let importers
buy the full surplus multiple times.  The corrected version:
  a) Aggregates total global surplus per resource across all exporters.
  b) Computes each importer's bid (capped by treasury).
  c) Allocates the *pooled* surplus proportionally to affordable bids.
  d) Attributes gold flows back to individual exporters proportionally
     to their contribution to the pool.

This ensures conservation: total resource moved = min(total surplus, total demand).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Tuple

from constants import (
    GRAIN_BIOME,
    STONE_BIOME,
    GOLD_BIOME,
    BASE_DEMAND,
    BASE_PRICE,
    TRADE_RESOURCES,
    STONE_REPLENISH_RATE,
    GOLD_REPLENISH_RATE,
    PRICE_ADAPT_RATE,
    PRICE_MIN,
    PRICE_MAX,
    WAR_TRADE_MUL,
    WAR_STATUS,
)
from world.model import ViliaEconomy

# Type alias for clarity
_StateMap = Dict[str, float]


# ---------------------------------------------------------------------------
# Diplomacy helper
# ---------------------------------------------------------------------------

def _get_war_pairs(world: ViliaEconomy) -> set[frozenset]:
    """Return a set of frozensets of state-ID pairs currently at war."""
    at_war: set[frozenset] = set()
    for s in world.states:
        sid = s.get("i")
        for oid, status in enumerate(s.get("diplomacy", [])):
            if isinstance(status, str) and status.lower() == WAR_STATUS:
                at_war.add(frozenset((sid, oid)))
    return at_war


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tick(world: ViliaEconomy) -> Tuple[dict, dict, dict, dict]:
    """
    Advance the economy by one tick.

    Parameters
    ----------
    world : ViliaEconomy
        The world object.  Mutated in-place (cell reserves, treasuries, prices).

    Returns
    -------
    production : dict[str, dict[str, float]]
        Post-trade food & stone per state: ``{state_name: {"food": ..., "stone": ...}}``.
    gold_mined : dict[str, float]
        Gold extracted this tick per state (already added to treasury).
    trade_flows : dict[str, dict]
        Net resource and gold flows per state:
        ``{"food": float, "stone": float, "gold_spent": float, "gold_earned": float}``.
        Positive = received / earned.
    unmet : dict[str, dict[str, float]]
        Unmet deficit per state per resource after trade.
        Non-zero means a state wanted to import but had no gold or no seller.
    """
    name_to_id = {s["name"]: s["i"] for s in world.states}
    id_to_name = {s["i"]: s["name"] for s in world.states}
    war_pairs  = _get_war_pairs(world)

    # ------------------------------------------------------------------
    # 1. Raw production
    # ------------------------------------------------------------------
    production: dict[str, dict] = {s["name"]: {"food": 0.0, "stone": 0.0} for s in world.states}
    gold_mined: dict[str, float] = {s["name"]: 0.0 for s in world.states}

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
        river = bool(c.get("river", False))
        coast = bool(c.get("coast", False))

        # Food — fully renewable each tick, no reserve
        g = GRAIN_BIOME.get(biome, 0.0)
        if river: g *= 1.2
        if coast: g *= 1.1
        if pop > 0: g *= 1 + pop
        g -= h * 0.01
        production[sname]["food"] += max(g, 0.0)

        # Stone — replenish then extract from reserve
        c["stone_reserve"] = min(
            c.get("stone_reserve", 0.0) + c.get("stone_max", 0.0) * STONE_REPLENISH_RATE,
            c.get("stone_max", 0.0),
        )
        st = STONE_BIOME.get(biome, 0.0)
        if river: st *= 1.2
        if coast: st *= 0.8
        if pop > 0: st *= 1 + pop
        st *= 1 + h / 1_000
        actual_st = min(st, c.get("stone_reserve", 0.0))
        c["stone_reserve"] = max(c.get("stone_reserve", 0.0) - actual_st, 0.0)
        production[sname]["stone"] += actual_st

        # Gold — replenish then extract; goes straight to treasury
        c["gold_reserve"] = min(
            c.get("gold_reserve", 0.0) + c.get("gold_max", 0.0) * GOLD_REPLENISH_RATE,
            c.get("gold_max", 0.0),
        )
        gd = GOLD_BIOME.get(biome, 0.0)
        if river: gd *= 1.6
        if coast: gd *= 0.8
        if pop > 0: gd *= 1 + pop
        gd *= 1 + h / 1_000
        actual_gd = min(gd, c.get("gold_reserve", 0.0))
        c["gold_reserve"] = max(c.get("gold_reserve", 0.0) - actual_gd, 0.0)
        gold_mined[sname] += actual_gd

    # Deposit mined gold into treasuries immediately
    for s in world.states:
        world.treasury[s["i"]] = world.treasury.get(s["i"], 0.0) + gold_mined[s["name"]]

    # ------------------------------------------------------------------
    # 2. Price update (global supply / demand signal)
    # ------------------------------------------------------------------
    for res in TRADE_RESOURCES:
        global_prod   = sum(production[s["name"]][res] for s in world.states)
        global_demand = sum(
            (s.get("rural", 0) + s.get("urban", 0)) * BASE_DEMAND[res]
            for s in world.states
        )
        if global_demand > 0 and global_prod > 0:
            ratio        = global_prod / global_demand
            target       = BASE_PRICE[res] / ratio          # scarcity → higher price
            target       = max(PRICE_MIN[res], min(PRICE_MAX[res], target))
            world.prices[res] += PRICE_ADAPT_RATE * (target - world.prices[res])
        world.prices[res] = max(PRICE_MIN[res], min(PRICE_MAX[res], world.prices[res]))

    # ------------------------------------------------------------------
    # 3. Gold-mediated trade  (FIXED: pooled surplus allocation)
    #
    # Algorithm:
    #   For each traded resource:
    #     a) Split states into surplus exporters and deficit importers.
    #     b) Pool total surplus across all exporters.
    #     c) Each importer bids min(deficit, affordable_units).
    #        War embargo: importer bid capped to 0 against all exporters
    #        they are at war with (conservative — a state at war with ANY
    #        exporter loses that exporter's share of the pool).
    #     d) Distribute pooled surplus proportionally to bids.
    #     e) Attribute gold flows back to individual exporters pro-rata
    #        by their contribution to the pool.
    # ------------------------------------------------------------------
    trade_flows: dict[str, dict] = {
        s["name"]: {"food": 0.0, "stone": 0.0, "gold_spent": 0.0, "gold_earned": 0.0}
        for s in world.states
    }
    unmet: dict[str, dict] = {s["name"]: {"food": 0.0, "stone": 0.0} for s in world.states}

    for res in TRADE_RESOURCES:
        price = world.prices[res]

        surplus: dict[str, float] = {}   # exporter name → surplus units
        deficit: dict[str, float] = {}   # importer name → deficit units

        for s in world.states:
            sname  = s["name"]
            pop    = s.get("rural", 0) + s.get("urban", 0)
            demand = pop * BASE_DEMAND[res]
            gap    = production[sname][res] - demand
            if gap > 0:
                surplus[sname] = gap
            elif gap < 0:
                deficit[sname] = -gap

        if not surplus or not deficit:
            for sname, amt in deficit.items():
                unmet[sname][res] += amt
            continue

        total_pool = sum(surplus.values())  # units available for trade

        # Build importer bids: units they can afford and need,
        # accounting for war embargoes.
        bids: dict[str, float] = {}
        for imp_name, def_amt in deficit.items():
            imp_id = name_to_id[imp_name]
            # Check if importer is at war with EVERY exporter
            # (if so, no trade at all for this importer)
            tradeable_pool = 0.0
            for exp_name, exp_surplus in surplus.items():
                exp_id = name_to_id[exp_name]
                if frozenset((exp_id, imp_id)) not in war_pairs or WAR_TRADE_MUL > 0:
                    tradeable_pool += exp_surplus

            if tradeable_pool <= 0:
                unmet[imp_name][res] += def_amt
                continue

            treasury  = world.treasury.get(imp_id, 0.0)
            affordable = treasury / price if price > 0 else 0.0
            effective  = min(def_amt, affordable, tradeable_pool)
            if effective > 0:
                bids[imp_name] = effective

        total_bid = sum(bids.values())
        if total_bid == 0:
            for imp_name, def_amt in deficit.items():
                unmet[imp_name][res] += def_amt
            continue

        # Allocate pooled surplus proportionally to bids
        for imp_name, bid in bids.items():
            imp_id   = name_to_id[imp_name]
            fraction = bid / total_bid
            transfer = min(total_pool * fraction, bid)   # can't exceed bid

            gold_cost = transfer * price
            treasury  = world.treasury.get(imp_id, 0.0)
            if gold_cost > treasury:
                transfer  = treasury / price if price > 0 else 0.0
                gold_cost = treasury

            if transfer <= 0:
                continue

            # Update post-trade production for the importer
            production[imp_name][res] += transfer

            # Deduct gold from importer
            world.treasury[imp_id] = max(world.treasury.get(imp_id, 0.0) - gold_cost, 0.0)

            # Distribute gold earned to exporters pro-rata by their pool share
            for exp_name, exp_surplus in surplus.items():
                exp_id      = name_to_id[exp_name]
                exp_share   = exp_surplus / total_pool
                exp_gold    = gold_cost * exp_share
                exp_units   = transfer * exp_share

                world.treasury[exp_id] = world.treasury.get(exp_id, 0.0) + exp_gold
                production[exp_name][res] = max(production[exp_name][res] - exp_units, 0.0)

                trade_flows[exp_name][res]           -= exp_units
                trade_flows[exp_name]["gold_earned"] += exp_gold

            trade_flows[imp_name][res]          += transfer
            trade_flows[imp_name]["gold_spent"] += gold_cost

            # Record any unmet deficit (asked for bid but got less)
            shortfall = deficit[imp_name] - transfer
            if shortfall > 0:
                unmet[imp_name][res] += shortfall

        # States that had no bids (broke or fully embargoed)
        for imp_name, def_amt in deficit.items():
            if imp_name not in bids:
                unmet[imp_name][res] += def_amt

    return production, gold_mined, trade_flows, unmet


def food_production_per_cell(world: ViliaEconomy) -> dict[int, float]:
    """
    Compute per-cell food production.

    Used by the population update to determine local food availability
    before state-level trade is applied.
    """
    out: dict[int, float] = {}
    for c in world.cells:
        if c.get("h", 0) <= 20:
            continue
        biome = c.get("biome", 0)
        h     = c.get("height", c.get("h", 0))
        pop   = c.get("pop", 0)
        g = GRAIN_BIOME.get(biome, 0.0)
        if c.get("river"): g *= 1.2
        if c.get("coast"): g *= 1.1
        if pop > 0: g *= 1 + pop
        g -= h * 0.01
        out[c["i"]] = max(g, 0.0)
    return out
