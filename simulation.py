"""
simulation.py
-------------
Main simulation loop: wires together the economy tick, population update,
and Lotka-Volterra predator-prey step, and records a history snapshot
each tick for later visualisation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from constants import DEFAULT_LV
from world.model import ViliaEconomy
from economy.tick import tick, food_production_per_cell
from population.dynamics import update_population, seed_monsters, lv_step


def run(
    world: ViliaEconomy,
    n_ticks: int = 200,
    lv_params: Optional[dict] = None,
    monster_density: float = 0.05,
) -> List[dict]:
    """
    Run the simulation for *n_ticks* steps and return a history list.

    Each entry in the returned list corresponds to one tick and contains:

    ============= ============================================================
    Key           Description
    ============= ============================================================
    tick          Tick index (0-based).
    production    Post-trade food & stone per state.
    gold_mined    Gold extracted this tick per state.
    treasury      Gold held by each state treasury at end of tick.
    trade         Net trade flows per state (food, stone, gold_spent/earned).
    unmet         Unmet food/stone deficits per state.
    prices        Current market prices (gold/unit) for food and stone.
    pop_by_state  Total population per state (sum of cell pops).
    total_pop     Global human population.
    total_monsters Global monster population.
    ============= ============================================================

    Parameters
    ----------
    world : ViliaEconomy
        The world to simulate.  Mutated in-place.
    n_ticks : int
        Number of simulation steps.
    lv_params : dict, optional
        Lotka-Volterra parameters.  Defaults to ``DEFAULT_LV``.
    monster_density : float
        Initial monsters as a fraction of cell human population.

    Returns
    -------
    list[dict]
        History snapshots, one per tick.
    """
    if lv_params is None:
        lv_params = DEFAULT_LV.copy()

    monsters = seed_monsters(world, monster_density)
    history: List[dict] = []

    for t in range(n_ticks):
        food_map = food_production_per_cell(world)
        production, gold_mined, trade_flows, unmet = tick(world)
        update_population(world, food_map, unmet)
        lv_step(world, monsters, lv_params)

        # Aggregate population per state from cell-level data
        pop_by_state: dict[int, float] = defaultdict(float)
        for c in world.cells:
            pop_by_state[c.get("state", 0)] += c.get("pop", 0.0)

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
            "total_pop":      sum(c.get("pop", 0.0) for c in world.cells),
            "total_monsters": sum(monsters.values()),
        })

    return history
