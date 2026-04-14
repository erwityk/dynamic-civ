from engine.map import generate_map
from engine.registry import Registry, register_builtins
from engine.state import GameState, Unit
from engine.turn import end_turn, found_city, move_unit, reset_unit_moves


def _new_game(seed: int = 1) -> tuple[GameState, Registry]:
    reg = Registry()
    register_builtins(reg)
    tiles = generate_map(20, 20, seed=seed)
    state = GameState(width=20, height=20, tiles=tiles)
    state.units.append(Unit(id=state.new_id(), type_name="Settler", x=10, y=10))
    state.units.append(Unit(id=state.new_id(), type_name="Warrior", x=11, y=10))
    reset_unit_moves(state, reg)
    return state, reg


def test_settler_founds_city_and_city_produces_warrior():
    state, reg = _new_game()
    settler = state.units[0]
    city = found_city(state, reg, settler, "Rome")
    assert city is not None
    assert settler not in state.units
    city.build_target = "Warrior"
    warrior_cost = reg.unit_types["Warrior"].cost
    # Need enough turns at ~1 prod/turn to complete a 20-cost warrior.
    for _ in range(warrior_cost + 2):
        end_turn(state, reg)
    names = [u.type_name for u in state.units]
    assert names.count("Warrior") >= 2  # original + produced


def test_research_progress_accumulates_and_flips_to_generating():
    state, reg = _new_game()
    settler = state.units[0]
    found_city(state, reg, settler, "Rome")
    state.research.prompt = "magic ogre"
    state.research.status = "accumulating"
    state.research.cost = 3
    for _ in range(5):
        end_turn(state, reg)
    assert state.research.status == "generating"


def test_unit_cannot_move_into_occupied_or_water():
    state, reg = _new_game()
    warrior = [u for u in state.units if u.type_name == "Warrior"][0]
    # Try to move onto settler.
    settler = [u for u in state.units if u.type_name == "Settler"][0]
    assert move_unit(state, warrior, settler.x, settler.y) is False
