from __future__ import annotations

import pygame

from engine.registry import Registry
from engine.state import GameState, Terrain, Unit

TILE = 32
GRID_ORIGIN = (8, 40)  # top-left of map area inside window

TERRAIN_COLORS = {
    Terrain.GRASS: (96, 150, 70),
    Terrain.WATER: (50, 90, 170),
}


def tile_to_screen(x: int, y: int) -> tuple[int, int]:
    ox, oy = GRID_ORIGIN
    return (ox + x * TILE, oy + y * TILE)


def screen_to_tile(sx: int, sy: int, state: GameState) -> tuple[int, int] | None:
    ox, oy = GRID_ORIGIN
    tx = (sx - ox) // TILE
    ty = (sy - oy) // TILE
    if 0 <= tx < state.width and 0 <= ty < state.height:
        return (int(tx), int(ty))
    return None


def draw_map(surf: pygame.Surface, state: GameState) -> None:
    for x in range(state.width):
        for y in range(state.height):
            t = state.tiles[x][y]
            sx, sy = tile_to_screen(x, y)
            pygame.draw.rect(surf, TERRAIN_COLORS[t.terrain], (sx, sy, TILE, TILE))
            pygame.draw.rect(surf, (30, 50, 30), (sx, sy, TILE, TILE), width=1)


def draw_city(surf: pygame.Surface, city, font: pygame.font.Font) -> None:
    sx, sy = tile_to_screen(city.x, city.y)
    pygame.draw.rect(surf, (230, 210, 120), (sx + 3, sy + 3, TILE - 6, TILE - 6))
    pygame.draw.rect(surf, (80, 50, 10), (sx + 3, sy + 3, TILE - 6, TILE - 6), width=2)
    label = font.render(city.name, True, (255, 255, 255))
    bg = pygame.Rect(sx - 4, sy - 14, label.get_width() + 8, 14)
    pygame.draw.rect(surf, (0, 0, 0), bg)
    surf.blit(label, (sx, sy - 14))


def draw_unit(surf: pygame.Surface, unit: Unit, reg: Registry, selected: bool, font: pygame.font.Font) -> None:
    sx, sy = tile_to_screen(unit.x, unit.y)
    ut = reg.unit_types.get(unit.type_name)
    color = ut.color if ut else (200, 200, 200)
    shape = ut.shape if ut else "circle"
    cx, cy = sx + TILE // 2, sy + TILE // 2
    r = TILE // 2 - 6
    if shape == "circle":
        pygame.draw.circle(surf, color, (cx, cy), r)
        pygame.draw.circle(surf, (20, 20, 20), (cx, cy), r, width=1)
    elif shape == "triangle":
        pts = [(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (20, 20, 20), pts, width=1)
    elif shape == "diamond":
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (20, 20, 20), pts, width=1)
    else:  # square
        pygame.draw.rect(surf, color, (cx - r, cy - r, r * 2, r * 2))
        pygame.draw.rect(surf, (20, 20, 20), (cx - r, cy - r, r * 2, r * 2), width=1)
    letter = unit.type_name[:1].upper()
    txt = font.render(letter, True, (0, 0, 0))
    surf.blit(txt, txt.get_rect(center=(cx, cy)))
    if selected:
        pygame.draw.rect(surf, (255, 230, 0), (sx, sy, TILE, TILE), width=2)


def draw_top_bar(surf: pygame.Surface, state: GameState, font: pygame.font.Font) -> None:
    pygame.draw.rect(surf, (25, 25, 35), (0, 0, surf.get_width(), 32))
    text = f"Turn {state.turn}    Science: {state.science}    Cities: {len(state.cities)}    Units: {len(state.units)}"
    label = font.render(text, True, (240, 240, 240))
    surf.blit(label, (12, 8))
