import json
from collections import defaultdict
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
    5: 0.06, 6: 0.11, 7: 0.04,  8: 0.1,  9: 0.20,
   10: 0.35, 11: 0.03, 12: 0.15,
}

BASE_DEMAND = {
    "food": 0.5,
    "stone": 0.2,
    "gold": 0.1,
}

class ViliaEconomy:

    def __init__(self, fmg_json):
        pack         = fmg_json["pack"]
        self.routes  = pack["routes"]
        self.biomes  = fmg_json["biomesData"]
        self.states  = [s for s in pack["states"]    if isinstance(s, dict)]
        self.provinces = [p for p in pack["provinces"] if isinstance(p, dict)]
        self.cells   = [c for c in pack["cells"]     if isinstance(c, dict)]

        self.year = fmg_json.get("settings", {}).get("options", {}).get("year", 1)
      

def load_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ViliaEconomy(data)

RESOURCES = ["food","stone","gold"]

def calculate_demand_state(self):
    out = {}
    for s in self.states:
        state_demand = {}
        for resource in RESOURCES:
            pop = s.get("rural", 0) + s.get("urban", 0)
            state_demand[resource] = pop * BASE_DEMAND[resource]
        out[s["name"]] = state_demand
    return out

def calculate_cell_capacity(c, food_per_person=1):
    # for c in self.cells:
    if c.get("h", 0) > 20:  # Only cells with elevation above 20 can produce
        biome_id = c["biome"]
        grain_yield = GRAIN_BIOME.get(biome_id, 0)
        # Bonus for being near a river or coast
        if c.get("river", False):
            grain_yield *= 1.2
        if c.get("coast", False):
            grain_yield *= 1.1
        if c.get("pop") > 0:
            grain_yield *= 1 + (c["pop"] / 1)  # Bonus for population

        grain_yield = grain_yield - c.get("height", 0) * 0.01
        return grain_yield/food_per_person

def labor_efficiency(pop, capacity):
    base = pop / (pop + capacity)

    # overcrowding penalty
    pressure = pop / capacity
    penalty = 1 / (1 + max(0, pressure - 1))

    return base * penalty

def calculate_cell_reserve(data):
#create the max of stone for each cell based on its height and biome, with a bonus for being near a river or coast
    for c in data.cells:
        if c.get("h", 0) > 20:  # Only cells with elevation above 20 can produce
            biome_id = c["biome"]
            stone_yield = STONE_BIOME.get(biome_id, 0)
            gold_yield = GOLD_BIOME.get(biome_id, 0)
            # Bonus for being near a river or coast
            if c.get("river", False):
                stone_yield *= 1.2
                gold_yield *= 1.6
            if c.get("coast", False):
                stone_yield *= 0.8
                gold_yield *= 0.8
            if c.get("pop") > 0:
                stone_yield *= 1 + (c["pop"] / 1)  # Bonus for population
                gold_yield *= 1 + (c["pop"] / 1)  # Bonus for population

            

            stone_yield *= 1 + c.get("height", 0)/1000
            gold_yield *= 1 + c.get("height", 0)/1000
            c["stone_max"] = stone_yield
            c["gold_max"] = gold_yield
        else:
            c["stone_max"] = 0
            c["gold_max"] = 0
        c["stone_reserve"] = c["stone_max"]*10
        c["gold_reserve"] = c["gold_max"]*10

    #print the aggerated stone max for each state, and the total stone max
    state_stone_max = defaultdict(float)
    return(state_stone_max)

    print("Total stone max:", sum(c["stone_max"] for c in data.cells))
    print("stone Reserve:", sum(c["stone_reserve"] for c in data.cells))
    print("Total gold max:", sum(c["gold_max"] for c in data.cells))
    print("gold Reserve:", sum(c["gold_reserve"] for c in data.cells))

def tick(self):
    # food production is based on the biome, with a bonus for being near a river or coast, and a penalty for being at high elevation
    def calculate_food_production():
        cell_production = {}  # state_id -> total food
        for c in self.cells:
            if c.get("h", 0) > 20:  # Only cells with elevation above 20 can produce
                biome_id = c["biome"]
                grain_yield = GRAIN_BIOME.get(biome_id, 0)
                # Bonus for being near a river or coast
                if c.get("river", False):
                    grain_yield *= 1.2
                if c.get("coast", False):
                    grain_yield *= 1.1
                if c.get("pop", 0) > 0:
                    grain_yield *= 1 + (c["pop"] / 1)  # Bonus for population

                grain_yield = grain_yield - c.get("height", 0) * 0.01  # Penalty for height
                # FIX: accumulate per state_id instead of overwriting
                state_id = c["state"]
                cell_production[state_id] = cell_production.get(state_id, 0) + grain_yield

        # Roll up cell totals to state names
        out = {}
        for state in self.states:
            state_id = state["i"]
            out[state["name"]] = {"food": cell_production.get(state_id, 0)}
        return out
    
    def calculate_stone_production():
        cell_production = {}  # state_id -> total stone
        for c in self.cells:
            if c.get("h", 0) > 20:  # Only cells with elevation above 120 can produce
                biome_id = c["biome"]
                stone_yield = STONE_BIOME.get(biome_id, 0)
                # Bonus for being near a river or coast
                if c.get("river", False):
                    stone_yield *= 1.2
                if c.get("coast", False):
                    stone_yield *= 0.8
                if c.get("pop", 0) > 0:
                    stone_yield *= 1 + (c["pop"] / 1)  # Bonus for population

                stone_yield *= 1 + c.get("height", 0)/1000
                reserve = c.get("stone_reserve", 0)
                actual = min(stone_yield, reserve)

                # reduce reserve
                c["stone_reserve"] = reserve - actual

                # FIX: accumulate per state_id instead of overwriting
                state_id = c["state"]
                cell_production[state_id] = cell_production.get(state_id, 0) + actual

        # Roll up cell totals to state names (FIX: no stale state_id keys to delete)
        out = {}
        for state in self.states:
            state_id = state["i"]
            out[state["name"]] = {"stone": cell_production.get(state_id, 0)}
        return out
    
    def calculate_gold_production():
        cell_production = {}  # state_id -> total gold
        for c in self.cells:
            if c.get("h", 0) > 20:  # Only cells with elevation above 120 can produce
                biome_id = c["biome"]
                gold_yield = GOLD_BIOME.get(biome_id, 0)
                # Bonus for being near a river or coast
                if c.get("river", False):
                    gold_yield *= 1.2
                if c.get("coast", False):
                    gold_yield *= 0.8
                if c.get("pop", 0) > 0:
                    gold_yield *= 1 + (c["pop"] / 1)  # Bonus for population

                gold_yield *= 1 + c.get("height", 0)/1000
                reserve = c.get("gold_reserve", 0)
                actual = min(gold_yield, reserve)

                # reduce reserve
                c["gold_reserve"] = reserve - actual

                # FIX: accumulate per state_id instead of overwriting
                state_id = c["state"]
                cell_production[state_id] = cell_production.get(state_id, 0) + actual

        # Roll up cell totals to state names (FIX: no stale state_id keys to delete)
        out = {}
        for state in self.states:
            state_id = state["i"]
            out[state["name"]] = {"gold": cell_production.get(state_id, 0)}
        return out

        
    grain=calculate_food_production()
    stone=calculate_stone_production()
    gold=calculate_gold_production()
    combined = {}
    for state in self.states:
        name = state["name"]
        combined[name] = {
            "food": grain.get(name, {}).get("food", 0),
            "stone": stone.get(name, {}).get("stone", 0),
            "gold": gold.get(name, {}).get("gold", 0)
        }

    return combined


#calc the demand-production gap for each state, and print it out in a nice format
def calculate_gap(self):
    demand = calculate_demand_state(self)
    production = tick(self)

    out = {}
    for state in self.states:
        name = state["name"]
        out[name] = {
            "food_gap": production.get(name, {}).get("food", 0)-demand.get(name, {}).get("food", 0) ,
            "stone_gap": production.get(name, {}).get("stone", 0)-demand.get(name, {}).get("stone", 0),
            "gold_gap": production.get(name, {}).get("gold", 0)-demand.get(name, {}).get("gold", 0)
        }
    return out


#also calc global gap
def calculate_global_gap(self):
    demand = calculate_demand_state(self)
    production = tick(self)

    out = {
        "food_gap": sum(demand.get(s["name"], {}).get("food", 0) for s in self.states) - sum(production.get(s["name"], {}).get("food", 0) for s in self.states),
        "stone_gap": sum(demand.get(s["name"], {}).get("stone", 0) for s in self.states) - sum(production.get(s["name"], {}).get("stone", 0) for s in self.states),
        "gold_gap": sum(demand.get(s["name"], {}).get("gold", 0) for s in self.states) - sum(production.get(s["name"], {}).get("gold", 0) for s in self.states)
    }
    return out
