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

The project is a turn-based civilization game where players can "research" new units/buildings by typing a free-text idea. The game calls the `claude` CLI as a subprocess which writes a Python mod file that gets dynamically loaded into the registry.

### Layer separation

- **`engine/`** — Pure game logic, no pygame. Safe to test headlessly.
  - `state.py` — All mutable game data: `GameState`, `Unit`, `City`, `Tile`, `ResearchState`. `GameState` is the single source of truth.
  - `registry.py` — Immutable type definitions (`UnitType`, `BuildingType`). `STAT_BOUNDS` enforces clamping for all registrations. `register_builtins()` seeds Settler, Warrior, Granary and calls `mark_builtins()` to protect them.
  - `turn.py` — All state-mutating game actions: `move_unit`, `found_city`, `attack`, `end_turn`. `end_turn` runs city yields, advances research progress, and increments the turn counter.
  - `map.py` — Procedural map generation. Center 3×3 is always grass to guarantee starting room.
  - `mod_api.py` — `ModAPI`: the only surface mods are allowed to touch. Validates names, clamps stats, delegates to `Registry`.

- **`render/`** — pygame UI. Depends on engine but engine never imports render.
  - `app.py` — `App`: main game loop at 30 FPS. Wires up event handling, sidebar (unit/city/research panels), and calls `research_trigger`/`research_poll` callbacks injected from `main.py`.
  - `draw.py` — Stateless drawing helpers. `TILE=32`, `GRID_ORIGIN=(8,40)`. Map is 20×20 tiles; sidebar starts at `x = GRID_ORIGIN[0] + 20*TILE + 16`.
  - `ui.py` — `Button`, `TextInput`, `Toasts`.

- **`research/`** — AI-powered mod pipeline.
  - `runner.py` — `ResearchRunner`: background thread. Calls `claude -p --permission-mode acceptEdits --allowedTools Write,Edit,Read` with the prompt piped via stdin (not argv — Windows `claude.CMD` mangles multi-line args). CWD is `mod_dir` so Claude can only write inside the sandbox.
  - `prompt.py` — `build_prompt()`: constructs the full Claude prompt embedding stat bounds, shape constraints, and API signatures.
  - `loader.py` — `load_mod_file()`: AST-validates imports against an allowlist (`math`, `random`, `dataclasses`, `engine.mod_api`), then `exec`s the mod and calls its `register(api)` function.

- **`mods/`** — Per-game sandbox directories at `mods/<game_id>/`. Each `.py` file dropped here by Claude is a mod. `_research.log` in each subdirectory contains run history.

### Research state machine

`ResearchState.status` transitions: `idle` → `accumulating` (player submits idea) → `generating` (science threshold met, triggers Claude subprocess) → `done` | `error`. `ResearchRunner.poll()` is called every frame from the render loop to consume finished jobs.

### Mod contract

Every mod file must define exactly `def register(api): ...` and call `api.register_unit(...)` or `api.register_building(...)` exactly once. No disallowed imports. Mods cannot overwrite builtin names.
