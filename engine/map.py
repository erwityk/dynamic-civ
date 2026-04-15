from __future__ import annotations

import random

from .state import Terrain, Tile


def _diamond_square(size: int, rng: random.Random, roughness: float = 0.5) -> list[list[float]]:
    """Return a size×size float grid in [0,1] via midpoint displacement.

    `size` must be 2^n + 1.  Values outside [0,1] are clamped.
    """
    grid = [[0.0] * size for _ in range(size)]
    # Seed the four corners.
    grid[0][0] = rng.random()
    grid[0][size - 1] = rng.random()
    grid[size - 1][0] = rng.random()
    grid[size - 1][size - 1] = rng.random()

    step = size - 1
    scale = roughness
    while step > 1:
        half = step // 2
        # Diamond step: fill centre of each square.
        for x in range(0, size - 1, step):
            for y in range(0, size - 1, step):
                avg = (grid[x][y] + grid[x + step][y] +
                       grid[x][y + step] + grid[x + step][y + step]) / 4.0
                grid[x + half][y + half] = avg + rng.uniform(-scale, scale)
        # Square step: fill midpoints of each edge.
        for x in range(0, size, half):
            for y in range((x + half) % step, size, step):
                total, count = 0.0, 0
                for dx, dy in [(-half, 0), (half, 0), (0, -half), (0, half)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < size and 0 <= ny < size:
                        total += grid[nx][ny]
                        count += 1
                grid[x][y] = total / count + rng.uniform(-scale, scale)
        step = half
        scale *= roughness

    # Clamp to [0, 1].
    for x in range(size):
        for y in range(size):
            grid[x][y] = max(0.0, min(1.0, grid[x][y]))
    return grid


def _height_to_terrain(h: float, x: int, y: int, width: int, height: int) -> Terrain:
    near_edge = x < 3 or x >= width - 3 or y < 3 or y >= height - 3
    if h < 0.25:
        return Terrain.WATER
    if h < 0.40:
        return Terrain.TUNDRA if near_edge else Terrain.PLAINS
    if h < 0.55:
        return Terrain.GRASS
    if h < 0.68:
        return Terrain.FOREST
    if h < 0.80:
        return Terrain.HILLS
    if h < 0.90:
        return Terrain.DESERT
    return Terrain.MOUNTAIN


def generate_map(
    width: int = 20,
    height: int = 20,
    water_ratio: float = 0.15,  # kept for API compatibility; ignored
    seed: int | None = None,
) -> list[list[Tile]]:
    rng = random.Random(seed)

    # Build a diamond-square grid large enough to cover width×height.
    n = 1
    while (1 << n) + 1 < max(width, height):
        n += 1
    ds_size = (1 << n) + 1
    hmap = _diamond_square(ds_size, rng)

    tiles: list[list[Tile]] = []
    for x in range(width):
        col: list[Tile] = []
        for y in range(height):
            terrain = _height_to_terrain(hmap[x][y], x, y, width, height)
            col.append(Tile(x=x, y=y, terrain=terrain))
        tiles.append(col)

    # Guarantee the centre 3×3 is PLAINS so player starting units have room to found.
    cx, cy = width // 2, height // 2
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            tiles[cx + dx][cy + dy].terrain = Terrain.PLAINS

    # Guarantee a 3×3 PLAINS patch at the AI start corner (bottom-right area).
    acx, acy = width - 3, height - 3
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            tiles[acx + dx][acy + dy].terrain = Terrain.PLAINS

    return tiles
