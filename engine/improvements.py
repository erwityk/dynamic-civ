from __future__ import annotations

from .state import Terrain

# Turns a Worker must spend on a tile to complete each improvement.
IMPROVEMENT_TURNS: dict[str, int] = {
    "Farm": 3,
    "Mine": 4,
    "Lumber Camp": 3,
    "Road": 2,
}

# Valid terrain types for each improvement. None means any passable terrain.
IMPROVEMENT_TERRAINS: dict[str, set[Terrain] | None] = {
    "Farm": {Terrain.GRASS, Terrain.PLAINS},
    "Mine": {Terrain.HILLS},
    "Lumber Camp": {Terrain.FOREST},
    "Road": None,
}

# (food_bonus, prod_bonus) added to the working city's yields when present on a tile.
IMPROVEMENT_YIELDS: dict[str, tuple[int, int]] = {
    "Farm": (1, 0),
    "Mine": (0, 2),
    "Lumber Camp": (0, 1),
    "Road": (0, 0),
}


def valid_improvements(terrain: Terrain) -> list[str]:
    """Return improvement names that can be built on the given terrain."""
    return [
        name for name, terrains in IMPROVEMENT_TERRAINS.items()
        if terrains is None or terrain in terrains
    ]
