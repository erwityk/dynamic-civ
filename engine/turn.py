from __future__ import annotations

from .registry import Registry
from .state import City, GameState, Terrain, Unit

FOOD_PER_GROWTH = 5


def reset_unit_moves(state: GameState, reg: Registry) -> None:
    for u in state.units:
        ut = reg.unit_types.get(u.type_name)
        u.moves_left = ut.move if ut else 0


def can_move_to(state: GameState, unit: Unit, nx: int, ny: int) -> bool:
    if unit.moves_left <= 0:
        return False
    if abs(nx - unit.x) + abs(ny - unit.y) != 1:
        return False
    tile = state.tile(nx, ny)
    if tile is None or tile.terrain == Terrain.WATER:
        return False
    # Friendly stacking blocked (single-player: any unit blocks).
    if state.unit_at(nx, ny) is not None:
        return False
    return True


def move_unit(state: GameState, unit: Unit, nx: int, ny: int) -> bool:
    if not can_move_to(state, unit, nx, ny):
        return False
    unit.x, unit.y = nx, ny
    unit.moves_left -= 1
    return True


def found_city(state: GameState, reg: Registry, unit: Unit, name: str) -> City | None:
    ut = reg.unit_types.get(unit.type_name)
    if ut is None or not ut.can_found_city:
        return None
    tile = state.tile(unit.x, unit.y)
    if tile is None or tile.terrain != Terrain.GRASS:
        return None
    if state.city_at(unit.x, unit.y) is not None:
        return None
    city = City(id=state.new_id(), name=name, x=unit.x, y=unit.y)
    state.cities.append(city)
    state.units.remove(unit)
    return city


def attack(state: GameState, reg: Registry, attacker: Unit, tx: int, ty: int) -> bool:
    if abs(tx - attacker.x) + abs(ty - attacker.y) != 1:
        return False
    if attacker.moves_left <= 0:
        return False
    target = state.unit_at(tx, ty)
    if target is None:
        return False
    # Placeholder: attacker wins if attack >= target defense, else both damaged.
    at = reg.unit_types.get(attacker.type_name)
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
    if at.attack + bonus >= dt.defense:
        state.units.remove(target)
    else:
        attacker.hp -= 2
        if attacker.hp <= 0:
            state.units.remove(attacker)
    attacker.moves_left -= 1
    return True


def _city_yields(city: City, reg: Registry) -> tuple[int, int, int]:
    base_food, base_prod, base_sci = 2, 1, 1
    for b in city.buildings:
        bt = reg.building_types.get(b)
        if bt:
            base_food += bt.food
            base_prod += bt.production
            base_sci += bt.science
    return base_food, base_prod, base_sci


def _apply_city_tick(state: GameState, reg: Registry, city: City) -> None:
    food, prod, sci = _city_yields(city, reg)
    city.food_stock += max(0, food - city.population)
    if city.food_stock >= FOOD_PER_GROWTH:
        city.food_stock -= FOOD_PER_GROWTH
        city.population += 1
    state.science += sci

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
                ))
        elif building_type:
            if target not in city.buildings:
                city.buildings.append(target)
        # Leave build_target set so the city keeps producing the same thing
        # until the player changes it.


def _find_spawn_tile(state: GameState, city: City) -> tuple[int, int] | None:
    if state.unit_at(city.x, city.y) is None:
        return (city.x, city.y)
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        nx, ny = city.x + dx, city.y + dy
        tile = state.tile(nx, ny)
        if tile is None or tile.terrain == Terrain.WATER:
            continue
        if state.unit_at(nx, ny) is None:
            return (nx, ny)
    return None


def end_turn(state: GameState, reg: Registry) -> None:
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

    state.turn += 1
    reset_unit_moves(state, reg)
