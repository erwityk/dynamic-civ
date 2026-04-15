from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from engine.map import generate_map
from engine.registry import Registry, register_builtins
from engine.state import Civilization, GameState, Unit
from engine.turn import reset_unit_moves
from render.app import App


def new_game(seed: int | None = None) -> tuple[GameState, Registry]:
    reg = Registry()
    register_builtins(reg)
    tiles = generate_map(20, 20, seed=seed)
    state = GameState(width=20, height=20, tiles=tiles)

    # Player civilization.
    state.civs.append(Civilization(name="player", color=(0, 180, 255)))
    cx, cy = 10, 10
    state.units.append(Unit(id=state.new_id(), type_name="Settler", x=cx, y=cy, owner="player"))
    state.units.append(Unit(id=state.new_id(), type_name="Warrior", x=cx + 1, y=cy, owner="player"))

    # AI civilization — bottom-right corner (guaranteed grass by generate_map).
    state.civs.append(Civilization(name="ai_1", color=(220, 60, 60)))
    ax, ay = 17, 17
    state.units.append(Unit(id=state.new_id(), type_name="Settler", x=ax, y=ay, owner="ai_1"))
    state.units.append(Unit(id=state.new_id(), type_name="Warrior", x=ax - 1, y=ay, owner="ai_1"))

    reset_unit_moves(state, reg)
    return state, reg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--stub-research", action="store_true",
                        help="Skip Claude subprocess; use a local stub mod (for dev iteration).")
    args = parser.parse_args()

    state, reg = new_game(seed=args.seed)

    # Per-game mod sandbox.
    game_id = uuid.uuid4().hex[:8]
    repo_root = Path(__file__).resolve().parent
    mod_dir = repo_root / "mods" / game_id
    mod_dir.mkdir(parents=True, exist_ok=True)

    # Research runner is wired up in Phase 2. For now, no trigger -> research
    # will sit in "generating" until runner is implemented.
    research_trigger = None
    research_poll = None
    try:
        from research.runner import ResearchRunner  # Phase 2
        runner = ResearchRunner(state=state, registry=reg, mod_dir=mod_dir,
                                use_stub=args.stub_research, repo_root=repo_root)
        research_trigger = runner.start
        research_poll = runner.poll
        print(f"[dynamic-civ] mod sandbox: {mod_dir}")
    except ImportError:
        print("[dynamic-civ] research runner not yet implemented; research will block at 'generating'.")

    app = App(state=state, reg=reg, research_trigger=research_trigger, research_poll=research_poll)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
