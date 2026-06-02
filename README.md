# Vilia Economy & Population Simulator

An agent-based economy simulator built on top of [Azgaar Fantasy Map Generator](https://azgaar.github.io/Fantasy-Map-Generator/) map data. Given a procedurally generated fantasy world, the simulator models resource production, gold-mediated inter-state trade, food-driven population dynamics, and Lotka-Volterra predator-prey interactions — all visualised in an interactive Plotly dashboard.

---

## What It Simulates

**Economy**

Each tick, every cell on the map produces resources based on its biome, elevation, and population:

- **Food** — fully renewable each tick; highest in rainforests and temperate grasslands.
- **Stone** — mined from geological reserves that slowly replenish; higher yields in mountains.
- **Gold** — rare, mined from reserves; treated as *currency*, not a traded commodity.

States with food or stone surpluses sell to deficit states at market rates. Prices respond dynamically to global supply and demand — scarcity raises prices, gluts lower them. A state that runs out of gold cannot import, leading to starvation and slower urban growth.

**Population**

Cell populations grow logistically when food is abundant and shrink under starvation. An unmet stone deficit (no building materials) applies an additional growth penalty — cities can't expand without quarried stone. Population figures feed directly back into production, creating natural boom-bust cycles.

**Predator-Prey Dynamics**

Monster populations are modelled with classic [Lotka-Volterra equations](https://en.wikipedia.org/wiki/Lotka%E2%80%93Volterra_equations), competing with humans for the same cells. Parameters are tunable via the CLI.

---

## Architecture

```
vilia_sim/
├── main.py              # CLI entry point
├── simulation.py        # Main simulation loop
├── constants.py         # All tunable parameters (biome yields, prices, LV coefficients)
├── requirements.txt
├── world/
│   └── model.py         # ViliaEconomy world object, JSON loader, procedural generator
├── economy/
│   └── tick.py          # Economy tick: production, price update, gold-mediated trade
├── population/
│   └── dynamics.py      # Population update (logistic + stone penalty) + Lotka-Volterra
└── viz/
    └── dashboard.py     # Interactive Plotly dashboard (5×2 subplot layout)
```

**Key design decisions**

- **Gold as currency, not commodity** — gold goes directly into state treasuries; food and stone are the traded goods, paid for in gold. This creates realistic trade dynamics: wealthy states can outbid poor ones even with comparable deficits.
- **Pooled surplus trade** — all exporters contribute to a single surplus pool per resource tick; importers bid proportionally. This fixes a resource-conservation bug in the naive "iterate each exporter" approach.
- **Reserve-backed mining** — stone and gold are finite (with slow replenishment). Reserves deplete over time, forcing states to adapt or trade.
- **Phase-aware population growth** — logistic brake (pop / K) prevents infinite growth; stone deprivation introduces a construction bottleneck as a second limiting factor.

---

## Setup

```bash
git clone https://github.com/Owen-Dy/vilia-economy-simulator
cd vilia-economy-simulator
pip install -r requirements.txt
```
## Usage

**No setup needed — runs on a procedural world out of the box:**

```bash
python main.py
```

**Use your own Azgaar FMG map:**

1. Open [Azgaar Fantasy Map Generator](https://azgaar.github.io/Fantasy-Map-Generator/)
2. Generate or load a map → *Export* → *Export to JSON*
3. Run:

```bash
python main.py --json YourMap.json
```

**Common options:**

```bash
# 500-tick simulation saved to HTML
python main.py --json ViliaFull.json --ticks 500 --output dashboard.html

# Higher monster density, aggressive Lotka-Volterra parameters
python main.py --density 0.15 --alpha 0.12 --gamma 0.05

# Reproducible procedural world
python main.py --procedural --seed 123 --ticks 300
```

**All options:**

| Flag | Default | Description |
|---|---|---|
| `--json PATH` | — | Path to Azgaar FMG JSON export |
| `--procedural` | — | Generate a random world (mutually exclusive with `--json`) |
| `--ticks N` | 200 | Simulation steps |
| `--density F` | 0.05 | Initial monster-to-human ratio |
| `--seed N` | 42 | Random seed for procedural generation |
| `--output FILE` | — | Save dashboard to HTML instead of opening browser |
| `--alpha F` | 0.10 | Human natural growth rate (LV) |
| `--mu F` | 0.08 | Human natural death rate (LV) |
| `--beta F` | 0.02 | Predation rate (LV) |
| `--delta F` | 0.01 | Monster conversion efficiency (LV) |
| `--gamma F` | 0.08 | Monster natural death rate (LV) |

---

## Dashboard

The interactive dashboard shows 10 subplots:

| Row | Left | Right |
|---|---|---|
| 1 | Food production per state | Stone production per state |
| 2 | Gold mined per tick | State treasury balance |
| 3 | Market prices (food & stone) | Unmet deficits |
| 4 | Food trade balance | Stone trade balance |
| 5 | Global human population | Global monster population |

Hover over any line or bar for detailed per-state, per-tick values.

---

## Tuning the Model

All constants are centralised in `constants.py`. Key parameters:

```python
# Biome yield tables (GRAIN_BIOME, STONE_BIOME, GOLD_BIOME)
# — adjust per-biome yields to change the economic geography

PRICE_ADAPT_RATE = 0.15   # how fast markets respond to supply shocks
STONE_REPLENISH_RATE = 0.002  # geological replenishment speed
GROWTH_RATE_BASE = 0.02   # base annual population growth
CARRYING_CAPACITY_K = 500.0  # logistic pop ceiling per cell

DEFAULT_LV = {"alpha": 0.10, "mu": 0.08, "beta": 0.02, "delta": 0.01, "gamma": 0.08}
```

---

## References

- Azgaar Fantasy Map Generator — [azgaar.github.io/Fantasy-Map-Generator](https://azgaar.github.io/Fantasy-Map-Generator/)
- Lotka-Volterra equations — [Wikipedia](https://en.wikipedia.org/wiki/Lotka%E2%80%93Volterra_equations)
- Logistic population growth — [Wikipedia](https://en.wikipedia.org/wiki/Logistic_function#In_ecology)
- Epstein & Axtell (1996) *Growing Artificial Societies* — foundational agent-based economics reference
