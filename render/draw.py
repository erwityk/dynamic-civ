from __future__ import annotations

import pygame

from engine.registry import Registry
from engine.state import GameState, Terrain, Unit
from engine.turn import city_border_radius

IMPROVEMENT_ICONS: dict[str, tuple[str, tuple[int, int, int]]] = {
    "Farm":        ("F", (160, 220, 80)),
    "Mine":        ("M", (200, 170, 80)),
    "Lumber Camp": ("L", (100, 180, 80)),
    "Road":        ("=", (210, 200, 150)),
}

TILE = 32
GRID_ORIGIN = (8, 40)  # top-left of map area inside window

TERRAIN_COLORS = {
    Terrain.GRASS:    (96,  150, 70),
    Terrain.PLAINS:   (180, 190, 100),
    Terrain.FOREST:   (34,  100, 34),
    Terrain.HILLS:    (140, 110, 70),
    Terrain.MOUNTAIN: (180, 180, 190),
    Terrain.DESERT:   (210, 190, 120),
    Terrain.TUNDRA:   (190, 200, 210),
    Terrain.WATER:    (50,  90,  170),
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
            if t.visibility == "hidden":
                pygame.draw.rect(surf, (0, 0, 0), (sx, sy, TILE, TILE))
            elif t.visibility == "explored":
                base = TERRAIN_COLORS[t.terrain]
                dim = tuple(int(c * 0.45) for c in base)
                pygame.draw.rect(surf, dim, (sx, sy, TILE, TILE))
                pygame.draw.rect(surf, (15, 25, 15), (sx, sy, TILE, TILE), width=1)
            else:
                pygame.draw.rect(surf, TERRAIN_COLORS[t.terrain], (sx, sy, TILE, TILE))
                pygame.draw.rect(surf, (30, 50, 30), (sx, sy, TILE, TILE), width=1)


def draw_improvements(surf: pygame.Surface, state: GameState, font: pygame.font.Font) -> None:
    for x in range(state.width):
        for y in range(state.height):
            tile = state.tiles[x][y]
            if tile.visibility == "hidden":
                continue
            imp = tile.improvement
            if imp not in IMPROVEMENT_ICONS:
                continue
            letter, color = IMPROVEMENT_ICONS[imp]
            sx, sy = tile_to_screen(x, y)
            lbl = font.render(letter, True, color)
            surf.blit(lbl, (sx + 2, sy + TILE - lbl.get_height() - 2))


def draw_city_borders(surf: pygame.Surface, state: GameState) -> None:
    """Draw semi-transparent city territory overlays (§12)."""
    border_surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    for city in state.cities:
        r = city_border_radius(city)
        color = (0, 180, 255, 45) if city.owner == "player" else (220, 60, 60, 45)
        border_surf.fill(color)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                tile = state.tile(city.x + dx, city.y + dy)
                if tile is None or tile.visibility == "hidden":
                    continue
                sx, sy = tile_to_screen(city.x + dx, city.y + dy)
                surf.blit(border_surf, (sx, sy))


def draw_city(surf: pygame.Surface, city, font: pygame.font.Font) -> None:
    sx, sy = tile_to_screen(city.x, city.y)
    fill = (230, 210, 120) if city.owner == "player" else (200, 80, 80)
    border = (80, 50, 10) if city.owner == "player" else (120, 20, 20)
    pygame.draw.rect(surf, fill, (sx + 3, sy + 3, TILE - 6, TILE - 6))
    pygame.draw.rect(surf, border, (sx + 3, sy + 3, TILE - 6, TILE - 6), width=2)
    label = font.render(city.name, True, (255, 255, 255))
    bg = pygame.Rect(sx - 4, sy - 14, label.get_width() + 8, 14)
    pygame.draw.rect(surf, (0, 0, 0), bg)
    surf.blit(label, (sx, sy - 14))
    # Population number in bottom-right of tile
    pop_lbl = font.render(str(city.population), True, (240, 240, 240))
    surf.blit(pop_lbl, (sx + TILE - pop_lbl.get_width() - 3, sy + TILE - pop_lbl.get_height() - 2))


def draw_unit(surf: pygame.Surface, unit: Unit, reg: Registry, selected: bool, font: pygame.font.Font) -> None:
    sx, sy = tile_to_screen(unit.x, unit.y)
    ut = reg.unit_types.get(unit.type_name)
    color = ut.color if ut else (200, 200, 200)
    # Dim exhausted units so the player can see at a glance who has moves left.
    if unit.moves_left == 0:
        color = tuple(max(0, c // 2) for c in color)
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
    elif unit.owner != "player":
        pygame.draw.rect(surf, (220, 50, 50), (sx, sy, TILE, TILE), width=2)
    # HP bar
    max_hp = ut.max_hp if ut else 10
    bar_w = TILE - 8
    bar_x, bar_y = sx + 4, sy + TILE - 5
    pygame.draw.rect(surf, (160, 40, 40), (bar_x, bar_y, bar_w, 4))
    filled = int(bar_w * max(0, unit.hp) / max_hp)
    pygame.draw.rect(surf, (60, 200, 60), (bar_x, bar_y, filled, 4))
    # Star glyph for promoted units
    if unit.promotions:
        star = font.render("*", True, (255, 220, 60))
        surf.blit(star, (sx + TILE - star.get_width() - 2, sy + 1))
    # Wave glyph for embarked units
    if unit.embarked:
        wave = font.render("~", True, (80, 160, 255))
        surf.blit(wave, (sx + 2, sy + 1))


def draw_minimap(surf: pygame.Surface, state: GameState) -> None:
    """Draw a small 100×100 minimap overlay in the bottom-right of the map area."""
    px = 5  # pixels per tile
    mm_w = state.width * px
    mm_h = state.height * px
    ox, oy = GRID_ORIGIN
    map_right = ox + state.width * TILE
    map_bottom = oy + state.height * TILE
    mm_x = map_right - mm_w - 4
    mm_y = map_bottom - mm_h - 4
    # Background
    pygame.draw.rect(surf, (10, 10, 10), (mm_x - 1, mm_y - 1, mm_w + 2, mm_h + 2))
    for x in range(state.width):
        for y in range(state.height):
            tile = state.tiles[x][y]
            if tile.visibility == "hidden":
                color = (0, 0, 0)
            else:
                color = TERRAIN_COLORS[tile.terrain]
            pygame.draw.rect(surf, color, (mm_x + x * px, mm_y + y * px, px, px))
    # City dots
    for city in state.cities:
        tile = state.tile(city.x, city.y)
        if tile and tile.visibility != "hidden":
            dot_color = (255, 220, 60) if city.owner == "player" else (220, 60, 60)
            pygame.draw.rect(surf, dot_color, (mm_x + city.x * px, mm_y + city.y * px, px, px))
    # Unit dots (player only for simplicity)
    for unit in state.units:
        if unit.owner == "player":
            pygame.draw.rect(surf, (255, 255, 255), (mm_x + unit.x * px + 1, mm_y + unit.y * px + 1, px - 2, px - 2))
    pygame.draw.rect(surf, (180, 180, 180), (mm_x - 1, mm_y - 1, mm_w + 2, mm_h + 2), width=1)


def draw_top_bar(surf: pygame.Surface, state: GameState, font: pygame.font.Font) -> None:
    pygame.draw.rect(surf, (25, 25, 35), (0, 0, surf.get_width(), 32))
    h = state.happiness
    h_str = f"{h:+d}" if h != 0 else "0"
    h_color = (240, 100, 100) if h < 0 else (240, 240, 240)
    left = f"Turn {state.turn}    Science: {state.science}    Gold: {state.gold}    "
    mid = f"Happiness: {h_str}    "
    right = f"Cities: {len(state.cities)}    Units: {len(state.units)}"
    x = 12
    lbl = font.render(left, True, (240, 240, 240))
    surf.blit(lbl, (x, 8))
    x += lbl.get_width()
    lbl = font.render(mid, True, h_color)
    surf.blit(lbl, (x, 8))
    x += lbl.get_width()
    surf.blit(font.render(right, True, (240, 240, 240)), (x, 8))
