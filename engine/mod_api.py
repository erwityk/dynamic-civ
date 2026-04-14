"""Public mod interface.

Mod files placed in mods/<game_id>/ expose a single top-level function:

    def register(api):
        api.register_unit(name="Magic Ogre", attack=5, defense=4, move=1,
                          cost=60, shape="triangle", color=(120, 60, 160),
                          description="A hulking sorcerous brute.")

The `api` object is an instance of ModAPI. Mods MUST NOT import engine internals
other than through this module. The loader enforces an import allowlist.
"""
from __future__ import annotations

from typing import Callable, Optional

from .registry import (
    SHAPES,
    STAT_BOUNDS,
    BuildingType,
    Registry,
    UnitType,
    _clamp,
)


class ModAPI:
    """Thin facade over the registry. The only surface mods see."""

    def __init__(self, registry: Registry, source_mod: str):
        self._registry = registry
        self._source = source_mod
        self.registered: list[str] = []

    def register_unit(
        self,
        name: str,
        *,
        attack: int,
        defense: int,
        move: int,
        cost: int,
        shape: str = "circle",
        color: tuple[int, int, int] = (100, 100, 200),
        description: str = "",
        on_attack: Optional[Callable] = None,
    ) -> None:
        name = str(name).strip()
        if not name:
            raise ValueError("unit name required")
        if name in self._registry.builtin_names:
            raise ValueError(f"cannot overwrite built-in '{name}'")
        if shape not in SHAPES:
            shape = "circle"
        color = _normalize_color(color)
        ut = UnitType(
            name=name,
            attack=_clamp("attack", attack),
            defense=_clamp("defense", defense),
            move=_clamp("move", move),
            cost=_clamp("cost", cost),
            shape=shape,
            color=color,
            description=str(description)[:400],
            can_found_city=False,
            on_attack=on_attack,
        )
        self._registry.add_unit(ut)
        self.registered.append(name)

    def register_building(
        self,
        name: str,
        *,
        cost: int,
        food: int = 0,
        production: int = 0,
        science: int = 0,
        description: str = "",
    ) -> None:
        name = str(name).strip()
        if not name:
            raise ValueError("building name required")
        if name in self._registry.builtin_names:
            raise ValueError(f"cannot overwrite built-in '{name}'")
        bt = BuildingType(
            name=name,
            cost=_clamp("cost", cost),
            food=_clamp("food", food),
            production=_clamp("production", production),
            science=_clamp("science", science),
            description=str(description)[:400],
        )
        self._registry.add_building(bt)
        self.registered.append(name)


def _normalize_color(c) -> tuple[int, int, int]:
    try:
        r, g, b = c
    except Exception:
        return (100, 100, 200)
    return (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))


__all__ = ["ModAPI", "STAT_BOUNDS", "SHAPES"]
