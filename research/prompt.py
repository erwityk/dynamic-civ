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
    return f"""You are a code generator for a turn-based civilization game. This is a
non-interactive task: **do NOT ask clarifying questions, do NOT explain your
reasoning, do NOT read any other files**. Just invoke the Write tool exactly
once with the file contents described below, then stop.

The player researched: **{player_idea}**

Task: pick ONE new unit OR building (whichever fits the idea) and Write a
Python file at the path `{mod_filename}` (relative to the current working
directory) containing valid Python source code.

## Required file contents

- Exactly one top-level function: `def register(api): ...`
- Inside `register`, call `api.register_unit(...)` OR `api.register_building(...)` exactly once.
- No other top-level statements with side effects.
- If you import anything, it must be from: `math`, `random`, `dataclasses`. Imports are optional; prefer zero imports.
- Stat bounds (values outside will be clamped): {bounds}.
- `shape` must be one of: {shapes}.
- `color` must be a tuple of 3 ints in [0, 255].
- Keep `description` under 300 characters.
- The `name` must be evocative of the player's idea and must differ from built-ins (Settler, Warrior, Granary).

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

Now generate the file for "{player_idea}" and Write it to `{mod_filename}`. No questions. No commentary.
"""
