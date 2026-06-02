"""
main.py
-------
Vilia Economy & Population Simulator — CLI entry point.

Gold is a currency, not a traded commodity:
  - States mine gold each tick → accumulated in state treasury.
  - Food and stone are traded; payment is settled in gold at a
    dynamically-priced market rate (supply/demand per resource).
  - A state with an empty treasury cannot buy imports.
    Unmet food deficit → starvation penalty on population growth.
    Unmet stone deficit → construction penalty (slower growth ceiling).
  - Lotka-Volterra monster / human predator-prey dynamics.

Usage
-----
# Run on a procedurally generated world (no files needed)
python main.py

# Run on an Azgaar FMG JSON export
python main.py --json ViliaFull.json

# Custom parameters
python main.py --json ViliaFull.json --ticks 500 --density 0.05 --output dashboard.html

# Tweak Lotka-Volterra parameters
python main.py --alpha 0.12 --gamma 0.06
"""

from __future__ import annotations

import argparse
import sys

from constants import DEFAULT_LV, BASE_PRICE
from world.model import load_from_file, generate_procedural_world
from simulation import run
from viz.dashboard import build_dashboard


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vilia Economy & Population Simulator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # World source
    world_group = parser.add_mutually_exclusive_group()
    world_group.add_argument(
        "--json",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to an Azgaar Fantasy Map Generator JSON export.",
    )
    world_group.add_argument(
        "--procedural",
        action="store_true",
        help="Generate a random world (no JSON file required).",
    )

    # Simulation parameters
    parser.add_argument("--ticks",   type=int,   default=200,  help="Number of simulation ticks.")
    parser.add_argument("--density", type=float, default=0.05, help="Initial monster density (fraction of human pop).")
    parser.add_argument("--seed",    type=int,   default=42,   help="Random seed for procedural generation.")

    # Lotka-Volterra parameters
    lv = DEFAULT_LV
    parser.add_argument("--alpha", type=float, default=lv["alpha"], help="Human natural growth rate.")
    parser.add_argument("--mu",    type=float, default=lv["mu"],    help="Human natural death rate.")
    parser.add_argument("--beta",  type=float, default=lv["beta"],  help="Predation rate (human losses per encounter).")
    parser.add_argument("--delta", type=float, default=lv["delta"], help="Monster conversion efficiency.")
    parser.add_argument("--gamma", type=float, default=lv["gamma"], help="Monster natural death rate.")

    # Output
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Save dashboard to an HTML file instead of opening the browser.",
    )

    return parser.parse_args()


def _print_summary(world, history: list[dict]) -> None:
    last = history[-1]
    print(f"\n  Final tick {last['tick']}:")
    print(f"    Total population : {last['total_pop']:>10.1f}")
    print(f"    Total monsters   : {last['total_monsters']:>10.1f}")
    print(f"    Food price       : {last['prices']['food']:.3f} gold / unit")
    print(f"    Stone price      : {last['prices']['stone']:.3f} gold / unit")
    print(
        f"\n    {'State':<14}  {'Pop':>8}  {'Food':>8}  {'Stone':>8}"
        f"  {'Treasury':>12}  {'Unmet F':>9}  {'Unmet S':>9}"
    )
    print(f"    {'─' * 77}")
    for s in world.states:
        sn = s["name"]
        ep = last["production"].get(sn, {})
        un = last["unmet"].get(sn, {})
        pp = last["pop_by_state"].get(s["i"], 0)
        tr = last["treasury"].get(sn, 0)
        print(
            f"    {sn:<14}  {pp:>8.1f}  {ep.get('food', 0):>8.2f}"
            f"  {ep.get('stone', 0):>8.2f}  {tr:>12.2f}"
            f"  {un.get('food', 0):>9.2f}  {un.get('stone', 0):>9.2f}"
        )


def main() -> None:
    args = _parse_args()

    lv_params = dict(
        alpha=args.alpha, mu=args.mu, beta=args.beta,
        delta=args.delta, gamma=args.gamma,
    )

    # ------------------------------------------------------------------
    # Load / generate world
    # ------------------------------------------------------------------
    if args.json:
        print(f"Loading world from '{args.json}' …")
        world = load_from_file(args.json)
        print(f"  {len(world.states)} states, {len(world.cells)} cells")
    else:
        if not args.procedural and args.json is None:
            # Default to procedural when neither flag is supplied
            print("No --json supplied; generating a procedural world.")
            print("(Pass --json <path> to use an Azgaar FMG export.)\n")
        world = generate_procedural_world(seed=args.seed)
        print(f"  Generated {len(world.states)} states, {len(world.cells)} cells")

    print(f"\nRunning {args.ticks} ticks  (monster density = {args.density}) …")
    history = run(world, n_ticks=args.ticks, lv_params=lv_params, monster_density=args.density)

    _print_summary(world, history)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    print("\nBuilding dashboard …")
    fig = build_dashboard(world, history)

    if args.output:
        fig.write_html(args.output)
        print(f"  Saved → {args.output}")
    else:
        fig.show()


if __name__ == "__main__":
    main()
