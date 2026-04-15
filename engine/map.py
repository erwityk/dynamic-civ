from __future__ import annotations

import random

from .state import Terrain, Tile


def generate_map(width: int = 20, height: int = 20, water_ratio: float = 0.15, seed: int | None = None) -> list[list[Tile]]:
    rng = random.Random(seed)
    tiles: list[list[Tile]] = []
    for x in range(width):
        col: list[Tile] = []
        for y in range(height):
            terrain = Terrain.WATER if rng.random() < water_ratio else Terrain.GRASS
            col.append(Tile(x=x, y=y, terrain=terrain))
        tiles.append(col)

    # Guarantee the center 3x3 is grass so player starting units have room.
    cx, cy = width // 2, height // 2
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            tiles[cx + dx][cy + dy].terrain = Terrain.GRASS

    # Guarantee a 3x3 grass patch at the AI start corner (bottom-right area).
    acx, acy = width - 3, height - 3
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            tiles[acx + dx][acy + dy].terrain = Terrain.GRASS

    return tiles
