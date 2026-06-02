"""
constants.py
------------
All tunable simulation parameters in one place.

Edit this file to change biome yields, market behaviour, population
dynamics, or Lotka-Volterra predator-prey constants without touching
any model code.
"""

# ---------------------------------------------------------------------------
# Biome yield tables
# Keys are Azgaar FMG biome IDs.
# ---------------------------------------------------------------------------

#: Grain (food) yield per biome per unit population per tick.
GRAIN_BIOME: dict[int, float] = {
    0: 0.00,   # Ocean / water
    1: 0.05,   # Hot desert
    2: 0.05,   # Cold desert
    3: 0.80,   # Savanna
    4: 1.00,   # Grassland
    5: 1.15,   # Tropical seasonal forest
    6: 1.15,   # Temperate deciduous forest
    7: 1.44,   # Tropical rainforest
    8: 1.34,   # Temperate rainforest
    9: 0.40,   # Taiga
   10: 0.20,   # Tundra
   11: 0.06,   # Glacier
   12: 1.12,   # Wetland
}

#: Stone yield per biome per tick. Higher in mountains and cold biomes.
STONE_BIOME: dict[int, float] = {
    0: 0.00, 1: 0.13, 2: 1.15,  3: 0.50,  4: 0.40,
    5: 0.12, 6: 0.23, 7: 0.08,  8: 0.21,  9: 0.40,
   10: 0.70, 11: 0.06, 12: 0.30,
}

#: Gold yield per biome per tick. Rare — treated as currency, not commodity.
GOLD_BIOME: dict[int, float] = {
    0: 0.00, 1: 0.06, 2: 0.65,  3: 0.25,  4: 0.20,
    5: 0.06, 6: 0.11, 7: 0.04,  8: 0.10,  9: 0.20,
   10: 0.35, 11: 0.03, 12: 0.15,
}

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

#: Resources that are traded between states (settled in gold).
TRADE_RESOURCES: list[str] = ["food", "stone"]

#: Per-capita demand per tick for each traded resource.
BASE_DEMAND: dict[str, float] = {
    "food":  0.5,
    "stone": 0.2,
}

# ---------------------------------------------------------------------------
# Market pricing (gold per unit of traded resource)
# ---------------------------------------------------------------------------

#: Starting price for each resource.
BASE_PRICE: dict[str, float] = {"food": 1.0, "stone": 2.0}

#: Speed at which prices adapt toward supply/demand signal each tick.
#: 0.0 = fixed prices, 1.0 = instant adjustment.
PRICE_ADAPT_RATE: float = 0.15

#: Hard price floor per resource (prevents deflation to zero).
PRICE_MIN: dict[str, float] = {"food": 0.1, "stone": 0.2}

#: Hard price ceiling per resource (prevents runaway inflation).
PRICE_MAX: dict[str, float] = {"food": 20.0, "stone": 40.0}

# ---------------------------------------------------------------------------
# Resource reserve replenishment
# ---------------------------------------------------------------------------

#: Fraction of stone_max restored to each cell per tick (slow geological process).
STONE_REPLENISH_RATE: float = 0.002

#: Fraction of gold_max restored to each cell per tick (very slow).
GOLD_REPLENISH_RATE: float = 0.0005

#: Number of ticks of base-rate stone production used to seed initial reserves.
STONE_SEED_YEARS: int = 2_000

#: Number of ticks of base-rate gold production used to seed initial reserves.
GOLD_SEED_YEARS: int = 500

#: Ticks of gold income used to seed each state's starting treasury.
TREASURY_SEED_YEARS: int = 20

# ---------------------------------------------------------------------------
# War / diplomacy
# ---------------------------------------------------------------------------

#: Trade multiplier between states at war. 0.0 = full embargo.
WAR_TRADE_MUL: float = 0.0

#: Diplomacy string that indicates two states are at war.
WAR_STATUS: str = "war"

# ---------------------------------------------------------------------------
# Population dynamics
# ---------------------------------------------------------------------------

#: Food units consumed per population unit per tick.
FOOD_PER_POP: float = 1.0

#: Base annual growth rate when food is ample and population is well below K.
GROWTH_RATE_BASE: float = 0.02

#: Starvation mortality rate multiplier when food is scarce.
STARVATION_RATE: float = 0.05

#: Extra negative growth rate per tick when a state's stone deficit is unmet.
#: Rationale: no building materials → disease, crowding, no expansion.
STONE_PENALTY_RATE: float = 0.01

#: Logistic carrying-capacity ceiling (population units per cell).
CARRYING_CAPACITY_K: float = 500.0

#: Minimum cell population (prevents extinction at floating-point zero).
MIN_CELL_POP: float = 0.001

# ---------------------------------------------------------------------------
# Lotka-Volterra predator-prey (monsters vs. humans)
# ---------------------------------------------------------------------------

#: Default Lotka-Volterra parameters.
#: alpha  — human natural growth rate (birth - death without monsters)
#: mu     — human natural death rate (subtracted from alpha)
#: beta   — predation rate (human losses per human-monster encounter)
#: delta  — monster conversion efficiency (monsters gained per kill)
#: gamma  — monster natural death rate
DEFAULT_LV: dict[str, float] = {
    "alpha": 0.10,
    "mu":    0.08,
    "beta":  0.02,
    "delta": 0.01,
    "gamma": 0.08,
}

# ---------------------------------------------------------------------------
# Procedural world generation (used when no JSON map is supplied)
# ---------------------------------------------------------------------------

#: Number of states in a randomly generated world.
PROC_NUM_STATES: int = 6

#: Number of cells per state in a randomly generated world.
PROC_CELLS_PER_STATE: int = 15

#: Population per cell in a randomly generated world.
PROC_CELL_POP: float = 10.0

# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

#: Colour palette for states (cycles if more states than colours).
STATE_COLORS: list[str] = [
    "#378ADD", "#D85A30", "#1D9E75", "#BA7517",
    "#993556", "#534AB7", "#3B6D11", "#888780",
    "#5DCAA5", "#F09595", "#EF9F27", "#AFA9EC",
]
