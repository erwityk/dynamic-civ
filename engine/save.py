"""Save/load GameState to JSON. §14."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .registry import Registry, register_builtins
from .state import (
    City,
    Civilization,
    GameState,
    ResearchState,
    Terrain,
    Tile,
    Unit,
    VictoryResult,
)
from .turn import compute_visibility, reset_unit_moves

SAVE_DIR = Path.home() / ".dynamic-civ" / "saves"


# ── serialization ──────────────────────────────────────────────────────────────

def _ser_tile(t: Tile) -> dict:
    return {
        "x": t.x, "y": t.y,
        "terrain": t.terrain.value,
        "improvement": t.improvement,
        "visibility": t.visibility,
    }


def _ser_unit(u: Unit) -> dict:
    return {
        "id": u.id, "type_name": u.type_name,
        "x": u.x, "y": u.y, "hp": u.hp,
        "moves_left": u.moves_left, "owner": u.owner,
        "xp": u.xp, "promotions": list(u.promotions),
        "has_moved": u.has_moved,
        "attacks_this_turn": u.attacks_this_turn,
        "promotion_pending": u.promotion_pending,
        "build_improvement": u.build_improvement,
        "improvement_turns_left": u.improvement_turns_left,
    }


def _ser_city(c: City) -> dict:
    return {
        "id": c.id, "name": c.name, "x": c.x, "y": c.y,
        "population": c.population, "food_stock": c.food_stock,
        "production_stock": c.production_stock, "build_target": c.build_target,
        "buildings": list(c.buildings), "owner": c.owner,
        "is_capital": c.is_capital,
        "culture": getattr(c, "culture", 0),
    }


def _ser_research(r: ResearchState) -> dict:
    return {
        "prompt": r.prompt, "progress": r.progress, "cost": r.cost,
        "status": r.status, "error": r.error,
        "last_result_name": r.last_result_name, "log_path": r.log_path,
        "researched_techs": sorted(r.researched_techs),
        "current_tech": r.current_tech, "tech_progress": r.tech_progress,
        "tech_just_completed": r.tech_just_completed,
        "wonder_discount": getattr(r, "wonder_discount", 0.0),
    }


def _ser_victory(v: Optional[VictoryResult]) -> Optional[dict]:
    if v is None:
        return None
    return {"victory_type": v.victory_type, "winner": v.winner, "score": v.score, "turn": v.turn}


def state_to_dict(state: GameState) -> dict:
    return {
        "width": state.width, "height": state.height,
        "game_id": state.game_id,
        "tiles": [[_ser_tile(state.tiles[x][y]) for y in range(state.height)] for x in range(state.width)],
        "units": [_ser_unit(u) for u in state.units],
        "cities": [_ser_city(c) for c in state.cities],
        "civs": [{"name": civ.name, "color": list(civ.color)} for civ in state.civs],
        "turn": state.turn, "science": state.science, "gold": state.gold,
        "happiness": state.happiness,
        "research": _ser_research(state.research),
        "game_over": _ser_victory(state.game_over),
        "_next_id": state._next_id,
        "built_wonders": sorted(getattr(state, "built_wonders", set())),
        "difficulty": getattr(state, "difficulty", "warlord"),
    }


# ── deserialization ────────────────────────────────────────────────────────────

def _deser_tile(d: dict) -> Tile:
    return Tile(
        x=d["x"], y=d["y"],
        terrain=Terrain(d["terrain"]),
        improvement=d.get("improvement"),
        visibility=d.get("visibility", "explored"),
    )


def _deser_unit(d: dict) -> Unit:
    return Unit(
        id=d["id"], type_name=d["type_name"],
        x=d["x"], y=d["y"], hp=d["hp"],
        moves_left=d["moves_left"], owner=d["owner"],
        xp=d.get("xp", 0), promotions=d.get("promotions", []),
        has_moved=d.get("has_moved", False),
        attacks_this_turn=d.get("attacks_this_turn", 0),
        promotion_pending=d.get("promotion_pending", False),
        build_improvement=d.get("build_improvement"),
        improvement_turns_left=d.get("improvement_turns_left", 0),
    )


def _deser_city(d: dict) -> City:
    c = City(
        id=d["id"], name=d["name"], x=d["x"], y=d["y"],
        population=d.get("population", 1),
        food_stock=d.get("food_stock", 0),
        production_stock=d.get("production_stock", 0),
        build_target=d.get("build_target"),
        buildings=d.get("buildings", []),
        owner=d.get("owner", "player"),
        is_capital=d.get("is_capital", False),
    )
    if hasattr(c, "culture"):
        c.culture = d.get("culture", 0)
    return c


def _deser_research(d: dict) -> ResearchState:
    r = ResearchState(
        prompt=d.get("prompt"),
        progress=d.get("progress", 0),
        cost=d.get("cost", 5),
        status=d.get("status", "idle"),
        error=d.get("error"),
        last_result_name=d.get("last_result_name"),
        log_path=d.get("log_path"),
        researched_techs=set(d.get("researched_techs", [])),
        current_tech=d.get("current_tech"),
        tech_progress=d.get("tech_progress", 0),
        tech_just_completed=d.get("tech_just_completed"),
    )
    if hasattr(r, "wonder_discount"):
        r.wonder_discount = d.get("wonder_discount", 0.0)
    return r


def dict_to_state(d: dict, repo_root: Optional[Path] = None) -> tuple[GameState, Registry]:
    tiles_raw = d["tiles"]
    tiles: list[list[Tile]] = [
        [_deser_tile(tiles_raw[x][y]) for y in range(d["height"])]
        for x in range(d["width"])
    ]

    state = GameState(
        width=d["width"], height=d["height"],
        tiles=tiles,
        turn=d.get("turn", 1),
        science=d.get("science", 0),
        gold=d.get("gold", 0),
        happiness=d.get("happiness", 0),
        game_id=d.get("game_id", ""),
        _next_id=d.get("_next_id", 1),
    )
    state.units = [_deser_unit(u) for u in d.get("units", [])]
    state.cities = [_deser_city(c) for c in d.get("cities", [])]
    state.civs = [Civilization(name=c["name"], color=tuple(c["color"])) for c in d.get("civs", [])]
    state.research = _deser_research(d.get("research", {}))
    vo = d.get("game_over")
    state.game_over = VictoryResult(**vo) if vo else None
    if hasattr(state, "built_wonders"):
        state.built_wonders = set(d.get("built_wonders", []))
    if hasattr(state, "difficulty"):
        state.difficulty = d.get("difficulty", "warlord")

    # Reconstruct registry: builtins first, then reload mods.
    reg = Registry()
    register_builtins(reg)
    if state.game_id and repo_root:
        _reload_mods(state, reg, repo_root)

    compute_visibility(state, reg)
    return state, reg


def _reload_mods(state: GameState, reg: Registry, repo_root: Path) -> None:
    mod_dir = repo_root / "mods" / state.game_id
    if not mod_dir.exists():
        return
    from .loader import load_mod_file
    for mod_file in sorted(mod_dir.glob("*.py")):
        try:
            load_mod_file(mod_file, reg)
        except Exception:
            pass


# ── public API ────────────────────────────────────────────────────────────────

def save_game(state: GameState, slot: int) -> None:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVE_DIR / f"slot{slot}.json"
    path.write_text(json.dumps(state_to_dict(state), indent=2), encoding="utf-8")


def load_game(slot: int, repo_root: Optional[Path] = None) -> tuple[GameState, Registry]:
    path = SAVE_DIR / f"slot{slot}.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    return dict_to_state(d, repo_root=repo_root)


def save_exists(slot: int) -> bool:
    return (SAVE_DIR / f"slot{slot}.json").exists()
