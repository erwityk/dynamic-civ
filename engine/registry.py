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
    "gold": (0, 5),
    "happiness": (0, 5),
    "max_hp": (1, 30),
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
    maintenance: int = 0  # gold cost per turn
    max_hp: int = 10
    on_attack: Optional[Callable] = None  # hook signature: (attacker_stats, defender_stats) -> int bonus
    requires_tech: Optional[str] = None  # tech name that must be researched to build/train


@dataclass(frozen=True)
class BuildingType:
    name: str
    cost: int
    food: int = 0
    production: int = 0
    science: int = 0
    gold: int = 0
    gold_multiplier: float = 1.0  # multiplies total city gold (e.g. Mint = 2.0)
    growth_food_reduction: float = 0.0  # fraction by which to reduce FOOD_PER_GROWTH (e.g. Aqueduct = 0.2)
    description: str = ""
    requires_tech: Optional[str] = None  # tech name that must be researched to construct
    happiness: int = 0  # empire-wide happiness bonus (e.g. Colosseum +3)


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

    def buildable_options(self, researched_techs: set[str] | None = None) -> list[str]:
        """Return names of all types whose tech prerequisite (if any) is satisfied."""
        def unlocked(item) -> bool:
            return item.requires_tech is None or (
                researched_techs is not None and item.requires_tech in researched_techs
            )
        return (
            [n for n, ut in self.unit_types.items() if unlocked(ut)]
            + [n for n, bt in self.building_types.items() if unlocked(bt)]
        )


def register_builtins(reg: Registry) -> None:
    # Units — no tech required
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
        maintenance=1,
    ))
    # Units — tech-locked
    reg.add_unit(UnitType(
        name="Spearman",
        attack=3, defense=3, move=1, cost=30,
        shape="triangle", color=(180, 140, 60),
        description="Anti-cavalry pikeman.",
        maintenance=1,
        requires_tech="Bronze Working",
    ))
    reg.add_unit(UnitType(
        name="Cavalry",
        attack=4, defense=2, move=3, cost=60,
        shape="circle", color=(200, 100, 40),
        description="Fast mounted raider.",
        maintenance=2,
        requires_tech="Horseback Riding",
    ))
    reg.add_unit(UnitType(
        name="Catapult",
        attack=4, defense=1, move=1, cost=50,
        shape="square", color=(140, 100, 80),
        description="Siege engine.",
        maintenance=1,
        requires_tech="Mathematics",
    ))
    # Buildings — tech-locked
    reg.add_building(BuildingType(
        name="Granary",
        cost=40, food=1,
        description="Boosts city food production.",
        requires_tech="Agriculture",
    ))
    reg.add_building(BuildingType(
        name="Market",
        cost=60, gold=2,
        description="Boosts city gold production.",
        requires_tech="Currency",
    ))
    reg.add_building(BuildingType(
        name="Mint",
        cost=80, gold_multiplier=2.0,
        description="Doubles city gold output.",
    ))
    reg.add_building(BuildingType(
        name="Aqueduct",
        cost=70, growth_food_reduction=0.2,
        description="Reduces food needed for city growth.",
        requires_tech="Mathematics",
    ))
    reg.add_building(BuildingType(
        name="Library",
        cost=60, science=2,
        description="Center of knowledge. (+2 science)",
        requires_tech="Writing",
    ))
    reg.add_building(BuildingType(
        name="Workshop",
        cost=60, production=1,
        description="Craftsmen improve city output. (+1 production)",
        requires_tech="Mining",
    ))
    # Buildings — happiness, no tech required
    reg.add_building(BuildingType(
        name="Temple",
        cost=60, happiness=2,
        description="Spiritual center of the city. (+2 happiness)",
    ))
    reg.add_building(BuildingType(
        name="Colosseum",
        cost=120, happiness=3,
        description="Gladiatorial games keep citizens content. (+3 happiness)",
    ))
    reg.mark_builtins()
