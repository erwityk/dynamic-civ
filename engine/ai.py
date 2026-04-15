from __future__ import annotations

import random

from .registry import Registry
from .state import GameState
from .turn import CITY_FOUNDING_TERRAINS, attack, found_city, move_unit

AI_OWNER = "ai_1"
_AI_CITY_COUNTER = 0


def run_ai_turn(state: GameState, reg: Registry) -> None:
    """Execute one full AI turn for all AI-owned units and cities."""
    rng = random.Random(state.turn)  # seeded per-turn for reproducibility
    _ai_build(state, reg, rng)
    _ai_expand(state, reg, rng)
    _ai_defend(state, reg, rng)
    _ai_threaten(state, reg, rng)


# ---------- priority helpers ----------

def _ai_build(state: GameState, reg: Registry, rng: random.Random) -> None:
    """Assign build targets to AI cities with no current target."""
    for city in [c for c in state.cities if c.owner == AI_OWNER]:
        if city.build_target is not None:
            continue
        if _city_has_adjacent_defender(state, city, AI_OWNER):
            city.build_target = "Granary"
        else:
            city.build_target = "Warrior"


def _ai_expand(state: GameState, reg: Registry, rng: random.Random) -> None:
    """Move AI Settlers toward unclaimed grass; found cities when in position."""
    global _AI_CITY_COUNTER
    settlers = [u for u in state.units if u.type_name == "Settler" and u.owner == AI_OWNER]
    for settler in settlers:
        if settler not in state.units:
            continue  # removed during this loop (e.g., founded a city)
        # Try to found a city on the current tile.
        if state.city_at(settler.x, settler.y) is None:
            tile = state.tile(settler.x, settler.y)
            if tile is not None and tile.terrain in CITY_FOUNDING_TERRAINS:
                _AI_CITY_COUNTER += 1
                city = found_city(state, reg, settler, f"AI City {_AI_CITY_COUNTER}")
                if city is not None:
                    continue  # settler consumed; city founded
        # Move toward nearest valid city tile.
        target = _nearest_valid_city_tile(state, settler.x, settler.y)
        if target is not None:
            _step_toward(state, settler, target[0], target[1])


def _ai_defend(state: GameState, reg: Registry, rng: random.Random) -> None:
    """Move Warriors toward undefended AI cities."""
    warriors = [u for u in state.units if u.type_name == "Warrior" and u.owner == AI_OWNER]
    ai_cities = [c for c in state.cities if c.owner == AI_OWNER]
    for warrior in warriors:
        if warrior not in state.units:
            continue
        if warrior.moves_left <= 0:
            continue
        # Find closest undefended AI city.
        undefended = [c for c in ai_cities if not _city_has_adjacent_defender(state, c, AI_OWNER)]
        if not undefended:
            break
        closest = min(undefended, key=lambda c: abs(c.x - warrior.x) + abs(c.y - warrior.y))
        _step_toward(state, warrior, closest.x, closest.y)


def _ai_threaten(state: GameState, reg: Registry, rng: random.Random) -> None:
    """Warriors adjacent to a player unit attack it."""
    warriors = [u for u in state.units if u.type_name == "Warrior" and u.owner == AI_OWNER]
    for warrior in warriors:
        if warrior not in state.units:
            continue
        if warrior.moves_left <= 0:
            continue
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = warrior.x + dx, warrior.y + dy
            neighbor = state.unit_at(nx, ny)
            if neighbor is not None and neighbor.owner != AI_OWNER:
                attack(state, reg, warrior, nx, ny)
                break  # one attack per warrior per turn


# ---------- utility ----------

def _step_toward(state: GameState, unit, tx: int, ty: int) -> bool:
    """Move unit one step closer to (tx, ty). Returns True if moved."""
    directions = []
    if tx > unit.x:
        directions.append((1, 0))
    elif tx < unit.x:
        directions.append((-1, 0))
    if ty > unit.y:
        directions.append((0, 1))
    elif ty < unit.y:
        directions.append((0, -1))
    # Try preferred directions first, then the other axis as fallback.
    all_dirs = directions + [(dx, dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)] if (dx, dy) not in directions]
    for dx, dy in all_dirs:
        if move_unit(state, unit, unit.x + dx, unit.y + dy):
            return True
    return False


def _nearest_valid_city_tile(state: GameState, x: int, y: int) -> tuple[int, int] | None:
    """Return the nearest unclaimed GRASS or PLAINS tile, or None if none exists."""
    best: tuple[int, int] | None = None
    best_dist = float("inf")
    for cx in range(state.width):
        for cy in range(state.height):
            tile = state.tiles[cx][cy]
            if tile.terrain not in CITY_FOUNDING_TERRAINS:
                continue
            if state.city_at(cx, cy) is not None:
                continue
            dist = abs(cx - x) + abs(cy - y)
            if dist < best_dist:
                best_dist = dist
                best = (cx, cy)
    return best


def _city_has_adjacent_defender(state: GameState, city, owner: str) -> bool:
    """True if any friendly unit is on or adjacent to the city tile."""
    for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
        u = state.unit_at(city.x + dx, city.y + dy)
        if u is not None and u.owner == owner:
            return True
    return False
