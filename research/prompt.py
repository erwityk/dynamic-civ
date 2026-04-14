from __future__ import annotations

from engine.registry import SHAPES, STAT_BOUNDS

EXAMPLE = '''
# mods/<game_id>/magic_ogre.py
def register(api):
    api.register_unit(
        name="Magic Ogre",
        attack=5, defense=4, move=1, cost=60,
        shape="triangle", color=(120, 60, 160),
        description="A hulking sorcerous brute that shrugs off small arms."
    )
'''


def build_prompt(player_idea: str, mod_filename: str) -> str:
    bounds = ", ".join(f"{k} in [{lo},{hi}]" for k, (lo, hi) in STAT_BOUNDS.items())
    shapes = ", ".join(sorted(SHAPES))
    return f"""You are generating a single Python mod file for a turn-based civilization game.

The player researched: **{player_idea}**

Create ONE new unit OR building (your choice, whichever fits the idea better) by writing a
Python file. Write the file to: `{mod_filename}` using the Write tool.

## Strict rules

1. The file must define exactly one top-level function: `def register(api): ...`
2. Inside `register`, call `api.register_unit(...)` OR `api.register_building(...)` exactly once.
3. Do NOT `import` anything except: `math`, `random`, `dataclasses`.
4. Do NOT read, write, or modify any file outside the per-game mods directory.
5. Do NOT define any other top-level code that has side effects.
6. Stat bounds (will be clamped if out of range): {bounds}.
7. `shape` must be one of: {shapes}.
8. `color` must be a tuple of 3 ints in [0, 255].
9. Keep `description` under 300 characters.
10. The `name` must be evocative of the player's idea and must not already exist.

## API signatures

```python
api.register_unit(
    name: str, *,
    attack: int, defense: int, move: int, cost: int,
    shape: str = "circle",
    color: tuple[int, int, int] = (100, 100, 200),
    description: str = "",
    on_attack: Callable | None = None,  # optional: (atk_stats, def_stats) -> int bonus
)

api.register_building(
    name: str, *,
    cost: int, food: int = 0, production: int = 0, science: int = 0,
    description: str = "",
)
```

## Example

```python
{EXAMPLE.strip()}
```

Now write the mod file for "{player_idea}". After writing, output nothing else.
"""
