from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Terrain(str, Enum):
    # Each member encodes: (str_val, move_cost, defense_bonus, food, prod, sci)
    # move_cost == 0 means impassable.
    GRASS    = ("grass",    1, 0, 2, 0, 0)
    PLAINS   = ("plains",   1, 0, 1, 1, 0)
    FOREST   = ("forest",   2, 1, 1, 1, 0)
    HILLS    = ("hills",    2, 1, 0, 2, 0)
    MOUNTAIN = ("mountain", 0, 0, 0, 0, 0)
    DESERT   = ("desert",   1, 0, 0, 0, 0)
    TUNDRA   = ("tundra",   1, 0, 1, 0, 0)
    WATER    = ("water",    0, 0, 0, 0, 0)

    def __new__(cls, str_val: str, move_cost: int, defense_bonus: int, food: int, prod: int, sci: int):
        obj = str.__new__(cls, str_val)
        obj._value_ = str_val
        obj.move_cost = move_cost
        obj.defense_bonus = defense_bonus
        obj.food = food
        obj.prod = prod
        obj.sci = sci
        return obj

    @property
    def passable(self) -> bool:
        return self.move_cost > 0


@dataclass
class Civilization:
    name: str
    color: tuple[int, int, int]  # RGB used for unit border tint


@dataclass
class Unit:
    id: int
    type_name: str
    x: int
    y: int
    hp: int = 10
    moves_left: int = 0
    owner: str = "player"  # matches Civilization.name or "player"


@dataclass
class City:
    id: int
    name: str
    x: int
    y: int
    population: int = 1
    food_stock: int = 0
    production_stock: int = 0
    build_target: Optional[str] = None  # unit or building type name
    buildings: list[str] = field(default_factory=list)
    owner: str = "player"


@dataclass
class Tile:
    x: int
    y: int
    terrain: Terrain


@dataclass
class ResearchState:
    prompt: Optional[str] = None
    progress: int = 0
    cost: int = 5
    status: str = "idle"  # idle | accumulating | generating | done | error
    error: Optional[str] = None
    last_result_name: Optional[str] = None  # name of the unit/building just created
    log_path: Optional[str] = None  # path to the most recent runner log


@dataclass
class GameState:
    width: int
    height: int
    tiles: list[list[Tile]]  # tiles[x][y]
    units: list[Unit] = field(default_factory=list)
    cities: list[City] = field(default_factory=list)
    civs: list[Civilization] = field(default_factory=list)
    turn: int = 1
    science: int = 0
    gold: int = 0
    research: ResearchState = field(default_factory=ResearchState)
    _next_id: int = 1

    def new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def tile(self, x: int, y: int) -> Optional[Tile]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[x][y]
        return None

    def unit_at(self, x: int, y: int) -> Optional[Unit]:
        for u in self.units:
            if u.x == x and u.y == y:
                return u
        return None

    def city_at(self, x: int, y: int) -> Optional[City]:
        for c in self.cities:
            if c.x == x and c.y == y:
                return c
        return None
