from __future__ import annotations

import random
from typing import Optional

from .improvements import IMPROVEMENT_TERRAINS, IMPROVEMENT_TURNS, IMPROVEMENT_YIELDS, valid_improvements
from .registry import Registry
from .state import City, GameState, Terrain, Unit, VictoryResult
from .tech import TECHS

FOOD_PER_GROWTH = 5
CITY_FOUNDING_TERRAINS = {Terrain.GRASS, Terrain.PLAINS}

_DIFFICULTY_MULTIPLIERS = {"chieftain": 0.7, "warlord": 1.0, "emperor": 1.5}


def _compute_happiness(state: GameState, reg: Registry) -> None:
    """Recompute global happiness before city ticks: buildings add, extra cities subtract."""
    h = -max(0, len(state.cities) - 1)
    for city in state.cities:
        for b in city.buildings:
            bt = reg.building_types.get(b)
            if bt and bt.happiness:
                h += bt.happiness
    state.happiness = h


def population_cap(state: GameState, city: City) -> int:
    """Hard cap = 2 + worked tiles within city border radius."""
    r = city_border_radius(city)
    worked = sum(
        1
        for dx in range(-r, r + 1)
        for dy in range(-r, r + 1)
        if (dx, dy) != (0, 0)
        for tile in [state.tile(city.x + dx, city.y + dy)]
        if tile is not None and tile.improvement is not None
    )
    return 2 + worked


def compute_visibility(state: GameState, reg: Registry) -> None:
    """Update fog-of-war: reset visible→explored, then mark tiles within player sight."""
    for col in state.tiles:
        for tile in col:
            if tile.visibility == "visible":
                tile.visibility = "explored"
    for u in state.units:
        if u.owner != "player":
            continue
        ut = reg.unit_types.get(u.type_name)
        sight = ut.sight if ut else 2
        for dx in range(-sight, sight + 1):
            for dy in range(-sight, sight + 1):
                if abs(dx) + abs(dy) <= sight:
                    tile = state.tile(u.x + dx, u.y + dy)
                    if tile is not None:
                        tile.visibility = "visible"
    for city in state.cities:
        if city.owner != "player":
            continue
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx) + abs(dy) <= 2:
                    tile = state.tile(city.x + dx, city.y + dy)
                    if tile is not None:
                        tile.visibility = "visible"


def reset_unit_moves(state: GameState, reg: Registry) -> None:
    for u in state.units:
        ut = reg.unit_types.get(u.type_name)
        u.moves_left = ut.move if ut else 0
        u.has_moved = False
        u.attacks_this_turn = 0


def can_move_to(state: GameState, unit: Unit, nx: int, ny: int, reg: Optional[Registry] = None) -> bool:
    if abs(nx - unit.x) + abs(ny - unit.y) != 1:
        return False
    tile = state.tile(nx, ny)
    if tile is None:
        return False
    ut = reg.unit_types.get(unit.type_name) if reg else None
    is_naval = ut is not None and ut.can_traverse_water
    is_embarked = unit.embarked
    if tile.terrain == Terrain.WATER:
        if not is_naval and not is_embarked:
            return False
        move_cost = 1
    elif is_naval:
        return False  # naval units cannot enter land tiles
    else:
        if not tile.terrain.passable:
            return False
        move_cost = 1 if tile.improvement == "Road" else tile.terrain.move_cost
    if unit.moves_left < move_cost:
        return False
    # Same-owner stacking blocked; enemy-occupied tiles require attack() instead.
    blocker = state.unit_at(nx, ny)
    if blocker is not None and blocker.owner == unit.owner:
        return False
    return True


def move_unit(state: GameState, unit: Unit, nx: int, ny: int, reg: Optional[Registry] = None) -> bool:
    if not can_move_to(state, unit, nx, ny, reg):
        return False
    tile = state.tile(nx, ny)  # type: ignore[union-attr]
    if tile.terrain == Terrain.WATER:
        cost = 1
        unit.embarked = True  # land unit enters water
    else:
        cost = 1 if tile.improvement == "Road" else tile.terrain.move_cost
        unit.embarked = False  # land unit returns to land
    unit.x, unit.y = nx, ny
    unit.moves_left -= cost
    unit.has_moved = True
    return True


def found_city(state: GameState, reg: Registry, unit: Unit, name: str) -> City | None:
    ut = reg.unit_types.get(unit.type_name)
    if ut is None or not ut.can_found_city:
        return None
    tile = state.tile(unit.x, unit.y)
    if tile is None or tile.terrain not in CITY_FOUNDING_TERRAINS:
        return None
    if state.city_at(unit.x, unit.y) is not None:
        return None
    city = City(id=state.new_id(), name=name, x=unit.x, y=unit.y, owner=unit.owner)
    if not any(c.owner == unit.owner for c in state.cities):
        city.is_capital = True
    state.cities.append(city)
    state.units.remove(unit)
    return city


def attack(state: GameState, reg: Registry, attacker: Unit, tx: int, ty: int) -> bool:
    at = reg.unit_types.get(attacker.type_name)
    at_range = at.range if at else 1
    dist = abs(tx - attacker.x) + abs(ty - attacker.y)
    if dist == 0 or dist > at_range:
        return False
    max_attacks = 2 if "Blitz" in attacker.promotions else 1
    if attacker.attacks_this_turn >= max_attacks:
        return False
    if attacker.moves_left <= 0 and attacker.attacks_this_turn == 0:
        return False
    target = state.unit_at(tx, ty)
    if target is None:
        return False
    if attacker.owner == target.owner:
        return False  # no friendly fire
    if attacker.embarked:
        return False  # embarked units cannot attack
    dt = reg.unit_types.get(target.type_name)
    if at is None or dt is None:
        return False
    bonus = 0
    if at.on_attack:
        try:
            bonus = int(at.on_attack(
                {"attack": at.attack, "defense": at.defense},
                {"attack": dt.attack, "defense": dt.defense},
            ))
        except Exception:
            bonus = 0
    if state.happiness < 0:
        bonus -= 1  # unhappy empire: -1 effective attack
    if "Drill I" in attacker.promotions:
        bonus += 1
    def_tile = state.tile(tx, ty)
    if target.embarked:
        terrain_def = 1 - dt.defense  # effective defense capped at 1 for embarked units
    else:
        terrain_def = def_tile.terrain.defense_bonus if def_tile else 0
        if state.city_at(tx, ty) is not None:
            terrain_def += 2  # city tile defense bonus
        if "Fortify I" in target.promotions and not target.has_moved:
            terrain_def += 1
    attacker.has_moved = True
    attacker.attacks_this_turn += 1
    attacker.moves_left = max(0, attacker.moves_left - 1)
    atk_roll = random.randint(1, 6) + at.attack + bonus
    def_roll = random.randint(1, 6) + dt.defense + terrain_def
    damage = max(1, abs(atk_roll - def_roll))
    if atk_roll >= def_roll:
        target.hp -= damage
        if target.hp <= 0:
            state.units.remove(target)
            attacker.xp += 2
            if attacker.xp >= 10 and not attacker.promotion_pending:
                attacker.promotion_pending = True
            # Capture city if the defender was its sole protector
            city = state.city_at(tx, ty)
            if city is not None and city.owner != attacker.owner:
                city.owner = attacker.owner
        else:
            attacker.xp += 1
            if attacker.xp >= 10 and not attacker.promotion_pending:
                attacker.promotion_pending = True
    else:
        if at.range == 1:  # ranged units take no counter-damage
            attacker.hp -= damage
            if attacker.hp <= 0:
                state.units.remove(attacker)
                return True
        attacker.xp += 1
        if attacker.xp >= 10 and not attacker.promotion_pending:
            attacker.promotion_pending = True
    return True


def city_border_radius(city: City) -> int:
    """Return city territory radius based on accumulated culture (§12)."""
    c = city.culture
    if c >= 25:
        return 3
    if c >= 10:
        return 2
    return 1


def _city_yields(city: City, state: GameState, reg: Registry, multiplier: float = 1.0) -> tuple[int, int, int, int]:
    tile = state.tile(city.x, city.y)
    if tile is not None:
        base_food, base_prod, base_sci = tile.terrain.food, tile.terrain.prod, tile.terrain.sci
    else:
        base_food, base_prod, base_sci = 1, 1, 0
    base_sci += 1  # every city contributes 1 base science; buildings add more
    base_gold = 1  # every city produces 1 base gold
    gold_multiplier = 1.0
    if "Hanging Gardens" in state.built_wonders and city.owner == "player":
        base_food += 2
    for b in city.buildings:
        bt = reg.building_types.get(b)
        if bt:
            base_food += bt.food
            base_prod += bt.production
            base_sci += bt.science
            base_gold += bt.gold
            gold_multiplier *= bt.gold_multiplier
    # Sum improvement bonuses from worked tiles within city border radius.
    r = city_border_radius(city)
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx == 0 and dy == 0:
                continue
            wtile = state.tile(city.x + dx, city.y + dy)
            if wtile is not None and wtile.improvement in IMPROVEMENT_YIELDS:
                fi, pi = IMPROVEMENT_YIELDS[wtile.improvement]
                base_food += fi
                base_prod += pi
    if multiplier != 1.0:
        base_food = int(base_food * multiplier)
        base_prod = int(base_prod * multiplier)
        base_sci = int(base_sci * multiplier)
        base_gold = int(base_gold * gold_multiplier * multiplier)
        return base_food, base_prod, base_sci, base_gold
    return base_food, base_prod, base_sci, int(base_gold * gold_multiplier)


def _apply_wonder_effect(state: GameState, reg: Registry, wonder_name: str) -> None:
    bt = reg.building_types.get(wonder_name)
    if bt is None or bt.wonder_effect is None:
        return
    effect = bt.wonder_effect
    if effect == "pyramids":
        for city in state.cities:
            if city.owner == "player" and "Granary" not in city.buildings:
                city.buildings.append("Granary")
    elif effect == "great_library":
        state.research.wonder_discount = 0.1
    elif effect == "space_colony":
        state.game_over = VictoryResult("science", "player", _compute_score(state), state.turn)
    # "hanging_gardens" bonus applied in _city_yields; "colosseum" bonus is on BuildingType.happiness


def _apply_city_tick(state: GameState, reg: Registry, city: City) -> None:
    mult = _DIFFICULTY_MULTIPLIERS.get(state.difficulty, 1.0) if city.owner != "player" else 1.0
    food, prod, sci, gold = _city_yields(city, state, reg, multiplier=mult)
    city.food_stock += max(0, food - city.population)
    growth_threshold = FOOD_PER_GROWTH
    for b in city.buildings:
        bt = reg.building_types.get(b)
        if bt and bt.growth_food_reduction:
            growth_threshold = max(1, int(growth_threshold * (1 - bt.growth_food_reduction)))
    cap = population_cap(state, city)
    if state.happiness >= 0 and city.food_stock >= growth_threshold:
        if city.population < cap:
            city.food_stock -= growth_threshold
            city.population += 1
        else:
            city.food_stock = growth_threshold - 1  # hold just under threshold at cap
    state.science += sci
    state.gold += gold

    # Culture accumulation (§12)
    for b in city.buildings:
        bt = reg.building_types.get(b)
        if bt:
            city.culture += bt.culture_per_turn

    if not city.build_target:
        return
    target = city.build_target
    unit_type = reg.unit_types.get(target)
    building_type = reg.building_types.get(target)
    cost = (unit_type.cost if unit_type else building_type.cost) if (unit_type or building_type) else None
    if cost is None:
        city.build_target = None
        return
    city.production_stock += max(0, prod)
    if city.production_stock >= cost:
        city.production_stock = 0
        if unit_type:
            # Spawn on city tile if empty, else adjacent grass.
            spawn = _find_spawn_tile(state, city)
            if spawn is not None:
                state.units.append(Unit(
                    id=state.new_id(), type_name=target,
                    x=spawn[0], y=spawn[1], moves_left=0,
                    owner=city.owner,
                ))
        elif building_type:
            if building_type.is_wonder:
                if target in state.built_wonders:
                    city.build_target = None
                    return
                city.buildings.append(target)
                state.built_wonders.add(target)
                _apply_wonder_effect(state, reg, target)
            elif target not in city.buildings:
                city.buildings.append(target)
        # Leave build_target set so the city keeps producing the same thing
        # until the player changes it.


def _find_spawn_tile(state: GameState, city: City) -> tuple[int, int] | None:
    if state.unit_at(city.x, city.y) is None:
        return (city.x, city.y)
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        nx, ny = city.x + dx, city.y + dy
        tile = state.tile(nx, ny)
        if tile is None or not tile.terrain.passable:
            continue
        if state.unit_at(nx, ny) is None:
            return (nx, ny)
    return None


def embark_unit(state: GameState, reg: Registry, unit: Unit) -> bool:
    """Embark a land unit onto an adjacent water tile. Requires a friendly Harbour city adjacent."""
    ut = reg.unit_types.get(unit.type_name)
    if ut is None or ut.can_traverse_water:
        return False  # already naval
    # Check adjacent friendly city has Harbour
    has_harbour = any(
        state.city_at(unit.x + dx, unit.y + dy) is not None
        and state.city_at(unit.x + dx, unit.y + dy).owner == unit.owner  # type: ignore
        and "Harbour" in state.city_at(unit.x + dx, unit.y + dy).buildings  # type: ignore
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
    )
    if not has_harbour:
        return False
    # Find adjacent water tile
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        tile = state.tile(unit.x + dx, unit.y + dy)
        if tile is not None and tile.terrain == Terrain.WATER and state.unit_at(unit.x + dx, unit.y + dy) is None:
            unit.x += dx
            unit.y += dy
            unit.embarked = True
            unit.moves_left = 0
            unit.has_moved = True
            return True
    return False


def worker_improve(state: GameState, reg: Registry, unit: Unit, improvement_name: str) -> bool:
    """Start a Worker building an improvement on its current tile."""
    ut = reg.unit_types.get(unit.type_name)
    if ut is None or not ut.can_improve:
        return False
    if unit.moves_left <= 0:
        return False
    tile = state.tile(unit.x, unit.y)
    if tile is None or not tile.terrain.passable:
        return False
    allowed = IMPROVEMENT_TERRAINS.get(improvement_name)
    if allowed is not None and tile.terrain not in allowed:
        return False
    if tile.improvement == improvement_name:
        return False  # already built
    unit.build_improvement = improvement_name
    unit.improvement_turns_left = IMPROVEMENT_TURNS[improvement_name]
    unit.moves_left = 0
    unit.has_moved = True
    return True


def _advance_worker_improvements(state: GameState) -> None:
    """Tick worker progress and apply completed improvements to tiles."""
    for u in list(state.units):
        if u.build_improvement is None:
            continue
        u.improvement_turns_left -= 1
        if u.improvement_turns_left <= 0:
            tile = state.tile(u.x, u.y)
            if tile is not None:
                tile.improvement = u.build_improvement
                if u.build_improvement == "Lumber Camp":
                    tile.terrain = Terrain.PLAINS  # clear forest, removes defense bonus
            u.build_improvement = None
            u.improvement_turns_left = 0


def _compute_score(state: GameState) -> int:
    player_cities = [c for c in state.cities if c.owner == "player"]
    player_units = [u for u in state.units if u.owner == "player"]
    return sum(c.population for c in player_cities) * 3 + len(player_units) + state.science + state.gold


def check_victory(state: GameState, reg: Registry) -> Optional[VictoryResult]:
    if state.game_over is not None:
        return state.game_over
    player_cities = [c for c in state.cities if c.owner == "player"]
    player_units = [u for u in state.units if u.owner == "player"]
    # Defeat: no cities and no unit that can found a city
    can_refound = any(
        reg.unit_types.get(u.type_name) and reg.unit_types[u.type_name].can_found_city
        for u in player_units
    )
    if not player_cities and not can_refound:
        result = VictoryResult("defeat", "ai", _compute_score(state), state.turn)
        state.game_over = result
        return result
    # Science victory: Space Colony wonder built
    if "Space Colony" in state.built_wonders and state.game_over is None:
        result = VictoryResult("science", "player", _compute_score(state), state.turn)
        state.game_over = result
        return result
    # Domination: no enemy capitals remain
    enemy_capitals = [c for c in state.cities if c.is_capital and c.owner != "player"]
    if not enemy_capitals and any(c.is_capital for c in state.cities):
        result = VictoryResult("domination", "player", _compute_score(state), state.turn)
        state.game_over = result
        return result
    # Time victory at turn 300
    if state.turn >= 300:
        result = VictoryResult("time", "player", _compute_score(state), state.turn)
        state.game_over = result
        return result
    return None


def _apply_healing(state: GameState, reg: Registry) -> None:
    for u in state.units:
        if u.has_moved:
            continue
        ut = reg.unit_types.get(u.type_name)
        max_hp = ut.max_hp if ut else 10
        city = state.city_at(u.x, u.y)
        heal = 4 if (city is not None and city.owner == u.owner) else 2
        u.hp = min(max_hp, u.hp + heal)


def end_turn(state: GameState, reg: Registry) -> None:
    compute_visibility(state, reg)
    _compute_happiness(state, reg)
    # Tally science gained this turn so research advances by the same amount cities produced.
    sci_before = state.science
    for city in state.cities:
        _apply_city_tick(state, reg, city)
    sci_gained = state.science - sci_before

    r = state.research
    if r.status == "accumulating" and r.prompt:
        r.progress += sci_gained
        if r.progress >= r.cost:
            r.status = "generating"
            r.progress = r.cost

    # Structured tech research: advances each turn by sci_gained.
    if r.current_tech is not None:
        tech = TECHS.get(r.current_tech)
        if tech is not None:
            r.tech_progress += sci_gained
            effective_cost = tech.cost * (1.0 - r.wonder_discount)
            if r.tech_progress >= effective_cost:
                r.researched_techs.add(r.current_tech)
                r.tech_just_completed = r.current_tech
                r.current_tech = None
                r.tech_progress = 0

    # Deduct maintenance: 1 gold per city + each unit's maintenance cost.
    maintenance = len(state.cities)
    for u in state.units:
        ut = reg.unit_types.get(u.type_name)
        if ut:
            maintenance += ut.maintenance
    state.gold -= maintenance
    if state.gold < 0 and state.units:
        disbanded = random.choice(state.units)
        state.units.remove(disbanded)

    state.turn += 1
    _advance_worker_improvements(state)
    _apply_healing(state, reg)
    reset_unit_moves(state, reg)
    check_victory(state, reg)


def purchase_build(state: GameState, reg: Registry, city: City) -> bool:
    """Instantly complete city's current build target by spending gold (cost = remaining × 3)."""
    if not city.build_target:
        return False
    unit_type = reg.unit_types.get(city.build_target)
    building_type = reg.building_types.get(city.build_target)
    if unit_type is None and building_type is None:
        return False
    cost = unit_type.cost if unit_type else building_type.cost  # type: ignore[union-attr]
    remaining = max(0, cost - city.production_stock)
    price = remaining * 3
    if state.gold < price:
        return False
    state.gold -= price
    city.production_stock = 0
    if unit_type:
        spawn = _find_spawn_tile(state, city)
        if spawn is not None:
            state.units.append(Unit(
                id=state.new_id(), type_name=city.build_target,
                x=spawn[0], y=spawn[1], moves_left=0,
                owner=city.owner,
            ))
    elif building_type:
        if city.build_target not in city.buildings:
            city.buildings.append(city.build_target)
    return True
