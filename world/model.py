"""
world/model.py
--------------
Core world object (ViliaEconomy) and its initialisation helpers.

The world object is a thin data container — it holds the parsed map data
from an Azgaar Fantasy Map Generator JSON export and a small amount of
mutable simulation state (treasuries, dynamic prices).  All simulation
logic lives in the economy and population modules.

Azgaar FMG export format (relevant keys)
-----------------------------------------
fmg_json
├── pack
│   ├── states     [list of state dicts]  — i, name, rural, urban, diplomacy
│   ├── provinces  [list of province dicts]
│   ├── cells      [list of cell dicts]   — i, h, biome, pop, state, river, coast, c
│   └── routes     [list of route dicts]  — group ("roads"|"trails"), points
├── biomesData     {biome metadata}
└── settings.options.year
"""

from __future__ import annotations

import json
import random
from typing import Dict, List

from constants import (
    BASE_PRICE,
    GRAIN_BIOME,
    STONE_BIOME,
    GOLD_BIOME,
    STONE_REPLENISH_RATE,
    GOLD_REPLENISH_RATE,
    STONE_SEED_YEARS,
    GOLD_SEED_YEARS,
    TREASURY_SEED_YEARS,
    PROC_NUM_STATES,
    PROC_CELLS_PER_STATE,
    PROC_CELL_POP,
)


# ---------------------------------------------------------------------------
# World object
# ---------------------------------------------------------------------------

class ViliaEconomy:
    """
    Container for a Vilia simulation world.

    Attributes
    ----------
    states : list[dict]
        State records from the FMG JSON (filtered to dict entries only).
    provinces : list[dict]
        Province records.
    cells : list[dict]
        Cell records — the fundamental spatial unit.  Mutated each tick
        (pop, stone_reserve, gold_reserve).
    routes : list[dict]
        Road/trail route records used for travel-cost graphs.
    biomes : dict
        Biome metadata from the FMG export.
    year : int
        Starting calendar year (cosmetic; not used in simulation logic).
    prices : dict[str, float]
        Current market prices (gold per unit) for each traded resource.
        Mutated by the economy tick.
    treasury : dict[int, float]
        Gold held by each state, keyed by state ID (``state["i"]``).
        Mutated by the economy tick.
    """

    def __init__(self, fmg_json: dict) -> None:
        pack = fmg_json["pack"]
        self.states:    List[dict] = [s for s in pack["states"]         if isinstance(s, dict)]
        self.provinces: List[dict] = [p for p in pack.get("provinces", []) if isinstance(p, dict)]
        self.cells:     List[dict] = [c for c in pack["cells"]          if isinstance(c, dict)]
        self.routes:    List[dict] = pack.get("routes", [])
        self.biomes:    dict       = fmg_json.get("biomesData", {})
        self.year:      int        = (
            fmg_json.get("settings", {}).get("options", {}).get("year", 1)
        )

        # Mutable simulation state
        self.prices:   Dict[str, float] = dict(BASE_PRICE)
        self.treasury: Dict[int, float] = {}


# ---------------------------------------------------------------------------
# Loading from file
# ---------------------------------------------------------------------------

def load_from_file(path: str) -> ViliaEconomy:
    """
    Parse an Azgaar FMG JSON export and return an initialised world.

    Reserves and treasuries are seeded automatically.
    """
    with open(path, "r", encoding="utf-8") as fh:
        world = ViliaEconomy(json.load(fh))
    _init_reserves(world)
    _init_treasuries(world)
    return world


# ---------------------------------------------------------------------------
# Procedural world generator (no JSON required)
# ---------------------------------------------------------------------------

def generate_procedural_world(
    num_states: int = PROC_NUM_STATES,
    cells_per_state: int = PROC_CELLS_PER_STATE,
    cell_pop: float = PROC_CELL_POP,
    seed: int = 42,
) -> ViliaEconomy:
    """
    Build a small random world so the simulator can run without a map file.

    Each state gets *cells_per_state* cells with randomly assigned biomes,
    heights, river/coast flags, and a fixed starting population.

    Parameters
    ----------
    num_states : int
        Number of states to generate.
    cells_per_state : int
        Cells assigned to each state.
    cell_pop : float
        Starting population per cell.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    ViliaEconomy
        Fully initialised world ready for simulation.
    """
    rng = random.Random(seed)

    state_names = [
        "Aldenmoor", "Brackenveil", "Cinderholm", "Duskreach",
        "Eryndell", "Frostmere", "Gravenwatch", "Harrowfen",
    ][:num_states]

    states = [
        {"i": i, "name": name, "rural": cell_pop * cells_per_state * 0.6,
         "urban": cell_pop * cells_per_state * 0.4, "diplomacy": []}
        for i, name in enumerate(state_names)
    ]

    habitable_biomes = [3, 4, 5, 6, 7, 8, 9, 10, 12]
    cells = []
    cell_id = 0
    for sid in range(num_states):
        for _ in range(cells_per_state):
            biome  = rng.choice(habitable_biomes)
            height = rng.uniform(25, 400)
            cells.append({
                "i":      cell_id,
                "state":  sid,
                "biome":  biome,
                "h":      height,
                "height": height,
                "pop":    cell_pop,
                "river":  rng.random() < 0.3,
                "coast":  rng.random() < 0.2,
                "c":      [],          # no adjacency needed for procedural world
            })
            cell_id += 1

    fmg_stub = {
        "pack": {
            "states":    states,
            "provinces": [],
            "cells":     cells,
            "routes":    [],
        },
        "biomesData": {},
        "settings":   {"options": {"year": 1}},
    }

    world = ViliaEconomy(fmg_stub)
    _init_reserves(world)
    _init_treasuries(world)
    return world


# ---------------------------------------------------------------------------
# Reserve & treasury initialisation (private)
# ---------------------------------------------------------------------------

def _init_reserves(world: ViliaEconomy) -> None:
    """
    Seed ``stone_reserve`` / ``gold_reserve`` for every habitable cell.

    Underwater / below-sea-level cells (h ≤ 20) get zero reserves.
    The ``_max`` fields store the geological ceiling so replenishment
    has a hard upper bound.
    """
    for c in world.cells:
        if c.get("h", 0) <= 20:
            c["stone_reserve"] = c["stone_max"] = 0.0
            c["gold_reserve"]  = c["gold_max"]  = 0.0
            continue

        biome = c.get("biome", 0)
        h     = c.get("height", c.get("h", 0))
        river = bool(c.get("river", False))
        coast = bool(c.get("coast", False))

        # Stone reserve — higher in mountains, reduced on coasts
        st = STONE_BIOME.get(biome, 0.0)
        if river: st *= 1.2
        if coast: st *= 0.8
        st *= 1 + h / 1_000

        # Gold reserve — peaks at riverine mountain cells
        gd = GOLD_BIOME.get(biome, 0.0)
        if river: gd *= 1.6
        if coast: gd *= 0.8
        gd *= 1 + h / 1_000

        c["stone_max"]     = st * STONE_SEED_YEARS
        c["gold_max"]      = gd * GOLD_SEED_YEARS
        c["stone_reserve"] = c["stone_max"]
        c["gold_reserve"]  = c["gold_max"]


def _init_treasuries(world: ViliaEconomy) -> None:
    """
    Give each state a starting treasury equal to *TREASURY_SEED_YEARS*
    ticks of base gold income (no pop multiplier).

    This prevents early-game trade being blocked by empty treasuries
    before the economy has had a chance to warm up.
    """
    for s in world.states:
        sid   = s["i"]
        total = 0.0
        for c in world.cells:
            if c.get("state") != sid or c.get("h", 0) <= 20:
                continue
            biome = c.get("biome", 0)
            h     = c.get("height", c.get("h", 0))
            gd    = GOLD_BIOME.get(biome, 0.0)
            if c.get("river"): gd *= 1.6
            if c.get("coast"): gd *= 0.8
            gd *= 1 + h / 1_000
            total += gd
        world.treasury[sid] = total * TREASURY_SEED_YEARS
