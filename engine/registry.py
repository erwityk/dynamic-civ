from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# Stat bounds enforced on all registrations (including mods).
STAT_BOUNDS = {
    "attack": (0, 10),
    "defense": (0, 10),
    "move": (0, 4),
    "cost": (5, 200),
    "food": (-2, 5),
    "production": (-2, 5),
    "science": (-2, 5),
}

# Valid shape tokens for the renderer.
SHAPES = {"circle", "triangle", "square", "diamond"}


def _clamp(name: str, value: int) -> int:
    lo, hi = STAT_BOUNDS[name]
    return max(lo, min(hi, int(value)))


@dataclass(frozen=True)
class UnitType:
    name: str
    attack: int
    defense: int
    move: int
    cost: int
    shape: str
    color: tuple[int, int, int]
    description: str
    can_found_city: bool = False
    on_attack: Optional[Callable] = None  # hook signature: (attacker_stats, defender_stats) -> int bonus


@dataclass(frozen=True)
class BuildingType:
    name: str
    cost: int
    food: int = 0
    production: int = 0
    science: int = 0
    description: str = ""


@dataclass
class Registry:
    unit_types: dict[str, UnitType] = field(default_factory=dict)
    building_types: dict[str, BuildingType] = field(default_factory=dict)
    builtin_names: set[str] = field(default_factory=set)

    def add_unit(self, ut: UnitType) -> None:
        if ut.name in self.unit_types or ut.name in self.building_types:
            raise ValueError(f"name '{ut.name}' already registered")
        self.unit_types[ut.name] = ut

    def add_building(self, bt: BuildingType) -> None:
        if bt.name in self.unit_types or bt.name in self.building_types:
            raise ValueError(f"name '{bt.name}' already registered")
        self.building_types[bt.name] = bt

    def mark_builtins(self) -> None:
        """Freeze the current registrations as built-ins; mods cannot overwrite these names."""
        self.builtin_names = set(self.unit_types) | set(self.building_types)

    def buildable_options(self) -> list[str]:
        return list(self.unit_types) + list(self.building_types)


def register_builtins(reg: Registry) -> None:
    reg.add_unit(UnitType(
        name="Settler",
        attack=0, defense=1, move=2, cost=30,
        shape="diamond", color=(230, 230, 230),
        description="Founds a new city on grass.",
        can_found_city=True,
    ))
    reg.add_unit(UnitType(
        name="Warrior",
        attack=2, defense=2, move=1, cost=20,
        shape="triangle", color=(200, 60, 60),
        description="Basic melee unit.",
    ))
    reg.add_building(BuildingType(
        name="Granary",
        cost=40, food=1, production=0, science=0,
        description="Boosts city food production.",
    ))
    reg.mark_builtins()
