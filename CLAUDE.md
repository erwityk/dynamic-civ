# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the game
python -m uv run python main.py

# Run with local stub research (no Claude subprocess, fast iteration)
python -m uv run python main.py --stub-research

# Run all tests
python -m uv run pytest

# Run a single test
python -m uv run pytest tests/test_engine.py::test_settler_founds_city_and_city_produces_warrior

# Add a dependency
python -m uv add <package>
```

## Architecture

Turn-based civilization game where players can "research" new units/buildings by typing a free-text idea. The game calls the `claude` CLI as a subprocess which writes a Python mod file that gets dynamically loaded into the registry.

### Layer separation

- **`engine/`** — Pure game logic, no pygame. Safe to test headlessly.
  - `state.py` — All mutable game data. `GameState` is the single source of truth: `tiles[x][y]`, `units`, `cities`, `civs`, `turn`, `science`, `gold`, `happiness`, `research`, `game_over`. Key types: `Unit` (has `xp`, `promotions`, `has_moved`, `attacks_this_turn`, `promotion_pending`), `City` (has `is_capital`), `Tile` (has `improvement`), `VictoryResult`, `ResearchState`.
  - `registry.py` — Immutable type definitions (`UnitType`, `BuildingType`). `STAT_BOUNDS` enforces clamping for all registrations (including mods). `register_builtins()` seeds all built-in units/buildings and calls `mark_builtins()` to protect them from mod overwriting. `UnitType` has `max_hp`, `can_found_city`, `maintenance`, `on_attack`, `requires_tech`.
  - `turn.py` — All state-mutating game actions: `move_unit`, `found_city`, `attack`, `end_turn`, `purchase_build`, `check_victory`. `end_turn` runs city yields → research advancement → maintenance → healing → move reset → victory check. `attack()` handles promotion bonuses (Drill I, Fortify I, Blitz), XP gain, and city capture on kill.
  - `tech.py` — `TECHS` dict of 7 `Tech` dataclasses (name, cost, prereqs, unlocks). `available_techs(researched)` returns the currently researchable set. Techs gate `UnitType`/`BuildingType` via `requires_tech`.
  - `ai.py` — `run_ai_turn()`: seeded-RNG AI executing four priority phases: `_ai_build` (assign build targets), `_ai_expand` (Settlers found cities), `_ai_defend` (Warriors cover own cities), `_ai_threaten` (attack adjacent player units). `AI_OWNER = "ai_1"`.
  - `map.py` — Diamond-square heightmap procedural generation. Center 3×3 is always grass; bottom-right 3×3 is always grass (AI start). Mountains/water are impassable.
  - `mod_api.py` — `ModAPI`: the only surface mods are allowed to touch. Validates names, clamps stats, delegates to `Registry`.

- **`render/`** — pygame UI. Depends on engine; engine never imports render.
  - `app.py` — `App`: 30 FPS game loop. Sidebar panels: unit (stats, XP, promotions, Found City), city (pop/food/prod, build queue, buy button), research (tech picker + invention). `_pending_promotion_unit` drives the promotion-choice UI. `game_over` on `GameState` triggers the victory/defeat overlay. `reset_callback` wires New Game.
  - `draw.py` — Stateless drawing helpers. `TILE=32`, `GRID_ORIGIN=(8,40)`. Map is 20×20 tiles; sidebar starts at `SIDEBAR_X = GRID_ORIGIN[0] + 20*TILE + 16`. `draw_unit()` renders HP bar and star glyph for promoted units.
  - `ui.py` — `Button`, `TextInput`, `Toasts`.

- **`research/`** — AI-powered mod pipeline.
  - `runner.py` — `ResearchRunner`: background thread. Calls `claude -p --permission-mode acceptEdits --allowedTools Write,Edit,Read` with the prompt piped via stdin (not argv — Windows `claude.CMD` mangles multi-line args). CWD is `mod_dir` so Claude can only write inside the sandbox.
  - `prompt.py` — `build_prompt()`: constructs the full Claude prompt embedding stat bounds, shape constraints, and API signatures.
  - `loader.py` — `load_mod_file()`: AST-validates imports against an allowlist (`math`, `random`, `dataclasses`, `engine.mod_api`), then `exec`s the mod and calls its `register(api)` function.

- **`mods/`** — Per-game sandbox directories at `mods/<game_id>/`. Each `.py` file dropped here by Claude is a mod. `_research.log` in each subdirectory contains run history.

### Dual-mode research

`ResearchState` tracks two parallel systems:

1. **Structured tech tree** — `current_tech` / `tech_progress` / `researched_techs`. Advances by `sci_gained` each turn. Completion sets `tech_just_completed` (cleared by the UI's Invent/Dismiss buttons) and unlocks gated units/buildings.

2. **Free-form invention** — `status` state machine: `idle` → `accumulating` → `generating` → `done` | `error`. Player types a prompt; science accumulates until threshold; `ResearchRunner` spawns Claude subprocess; result is a mod file loaded into the registry.

### Mod contract

Every mod file must define exactly `def register(api): ...` and call `api.register_unit(...)` or `api.register_building(...)` exactly once. No disallowed imports. Mods cannot overwrite builtin names.
