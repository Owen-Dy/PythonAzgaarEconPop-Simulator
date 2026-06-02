"""
population/dynamics.py
----------------------
Population dynamics: food-driven logistic growth and Lotka-Volterra
predator-prey (monsters vs. humans).

Growth model
------------
Each cell grows or shrinks based on its local food surplus/deficit:

    food_ratio = (food_produced - food_needed) / food_needed

    if food_ratio ≥ 0:
        growth = GROWTH_RATE_BASE × food_ratio × pop × (1 - pop/K)
    else:
        growth = STARVATION_RATE × food_ratio × pop

Additionally, if a cell's *state* has an unmet stone deficit, each cell
in that state receives a STONE_PENALTY_RATE growth penalty proportional
to the severity of the deficit.  Rationale: no building materials →
disease, crowding, stalled urban expansion.

Lotka-Volterra model
--------------------
Monster predation follows the classic Lotka-Volterra equations:

    dH/dt = (alpha - mu) × H - beta × H × M
    dM/dt = delta × beta × H × M - gamma × M

where H = human cell population, M = monster population in that cell.
Parameters are tunable via the CLI or DEFAULT_LV in constants.py.
"""

from __future__ import annotations

from typing import Optional

from constants import (
    FOOD_PER_POP,
    GROWTH_RATE_BASE,
    STARVATION_RATE,
    STONE_PENALTY_RATE,
    CARRYING_CAPACITY_K,
    MIN_CELL_POP,
    BASE_DEMAND,
)
from world.model import ViliaEconomy


# ---------------------------------------------------------------------------
# Population update
# ---------------------------------------------------------------------------

def update_population(
    world: ViliaEconomy,
    food_map: Optional[dict[int, float]] = None,
    unmet:    Optional[dict[str, dict]]  = None,
) -> None:
    """
    Update cell populations based on food availability and stone deprivation.

    Parameters
    ----------
    world : ViliaEconomy
        Mutated in-place (cell ``pop`` fields updated).
    food_map : dict[int, float], optional
        Per-cell food production from ``food_production_per_cell()``.
        Recomputed if not supplied.
    unmet : dict[str, dict[str, float]], optional
        Unmet deficits from ``tick()``.  Used to compute the stone
        deprivation penalty per state.
    """
    from economy.tick import food_production_per_cell   # local import avoids cycle

    if food_map is None:
        food_map = food_production_per_cell(world)
    if unmet is None:
        unmet = {}

    # Per-state stone penalty scalar: 0 = no penalty, 1 = full penalty
    stone_penalty: dict[int, float] = {}
    for s in world.states:
        sname  = s["name"]
        pop    = s.get("rural", 0) + s.get("urban", 0)
        demand = pop * BASE_DEMAND["stone"]
        unmet_st = unmet.get(sname, {}).get("stone", 0.0)
        stone_penalty[s["i"]] = (unmet_st / demand) if demand > 0 else 0.0

    for c in world.cells:
        pop = c.get("pop", 0.0)
        if pop <= 0:
            continue

        food_needed   = pop * FOOD_PER_POP
        food_produced = food_map.get(c["i"], 0.0)

        # Food ratio clamped to [-1, 1] to prevent extreme swings
        raw = (food_produced - food_needed) / food_needed if food_needed > 0 else 0.0
        fr  = max(-1.0, min(1.0, raw))

        if fr >= 0.0:
            # Logistic brake: growth slows as population approaches K
            brake  = max(0.0, 1.0 - pop / CARRYING_CAPACITY_K)
            growth = GROWTH_RATE_BASE * fr * pop * brake
        else:
            growth = STARVATION_RATE * fr * pop   # fr is negative → net loss

        # Stone deprivation dampens growth
        sp = stone_penalty.get(c.get("state", 0), 0.0)
        if sp > 0:
            growth -= STONE_PENALTY_RATE * sp * pop

        c["pop"] = max(pop + growth, MIN_CELL_POP)


# ---------------------------------------------------------------------------
# Lotka-Volterra predator-prey
# ---------------------------------------------------------------------------

def seed_monsters(world: ViliaEconomy, density: float = 0.05) -> dict[int, float]:
    """
    Initialise monster populations at *density* × cell human population.

    Only habitable, populated cells receive monsters.

    Parameters
    ----------
    density : float
        Fraction of human population seeded as monsters (default 0.05 = 5 %).
    """
    return {
        c["i"]: c["pop"] * density
        for c in world.cells
        if c.get("pop", 0) > 0 and c.get("h", 0) > 20
    }


def lv_step(
    world: ViliaEconomy,
    monsters: dict[int, float],
    lv: dict[str, float],
) -> None:
    """
    Apply one Lotka-Volterra step to all cells.

    Mutates ``world.cells[*]["pop"]`` and *monsters* in-place.

    Parameters
    ----------
    world : ViliaEconomy
    monsters : dict[int, float]
        Current monster population per cell ID.  Updated in-place.
    lv : dict[str, float]
        Lotka-Volterra parameters: alpha, mu, beta, delta, gamma.
    """
    alpha = lv["alpha"]
    mu    = lv["mu"]
    beta  = lv["beta"]
    delta = lv["delta"]
    gamma = lv["gamma"]

    for c in world.cells:
        H = c.get("pop", 0.0)
        M = monsters.get(c["i"], 0.0)
        if H <= 0:
            continue

        dH = (alpha - mu) * H - beta * H * M
        dM = delta * beta * H * M - gamma * M

        c["pop"]         = max(H + dH, MIN_CELL_POP)
        monsters[c["i"]] = max(M + dM, 0.0)
