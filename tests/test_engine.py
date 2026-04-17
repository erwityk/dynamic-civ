from engine.map import generate_map
from engine.registry import Registry, register_builtins
from engine.state import City, GameState, Terrain, Tile, Unit
from engine.tech import available_techs
from engine.turn import (
    CITY_FOUNDING_TERRAINS,
    attack,
    can_move_to,
    end_turn,
    found_city,
    move_unit,
    population_cap,
    reset_unit_moves,
)


def _new_game(seed: int = 1) -> tuple[GameState, Registry]:
    reg = Registry()
    register_builtins(reg)
    tiles = generate_map(20, 20, seed=seed)
    state = GameState(width=20, height=20, tiles=tiles, gold=100)
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


def _make_state(terrain_grid: dict[tuple[int, int], Terrain], width: int = 20, height: int = 20) -> tuple[GameState, Registry]:
    """Build a minimal GameState with specific tile overrides."""
    reg = Registry()
    register_builtins(reg)
    tiles = generate_map(width, height, seed=1)
    for (x, y), t in terrain_grid.items():
        tiles[x][y].terrain = t
    state = GameState(width=width, height=height, tiles=tiles)
    return state, reg


def test_forest_costs_two_moves():
    state, reg = _make_state({(11, 10): Terrain.FOREST})
    unit = Unit(id=state.new_id(), type_name="Warrior", x=10, y=10, moves_left=1)
    state.units.append(unit)
    # 1 move point is not enough to enter forest (cost=2).
    assert can_move_to(state, unit, 11, 10) is False
    unit.moves_left = 2
    assert can_move_to(state, unit, 11, 10) is True
    assert move_unit(state, unit, 11, 10) is True
    assert unit.moves_left == 0


def test_mountain_is_impassable():
    state, reg = _make_state({(11, 10): Terrain.MOUNTAIN})
    unit = Unit(id=state.new_id(), type_name="Warrior", x=10, y=10, moves_left=2)
    state.units.append(unit)
    assert can_move_to(state, unit, 11, 10) is False


def test_found_city_on_plains_allowed():
    state, reg = _make_state({(10, 10): Terrain.PLAINS})
    settler = Unit(id=state.new_id(), type_name="Settler", x=10, y=10, moves_left=2)
    state.units.append(settler)
    city = found_city(state, reg, settler, "Springfield")
    assert city is not None


def test_found_city_on_forest_blocked():
    state, reg = _make_state({(10, 10): Terrain.FOREST})
    settler = Unit(id=state.new_id(), type_name="Settler", x=10, y=10, moves_left=2)
    state.units.append(settler)
    city = found_city(state, reg, settler, "Nope")
    assert city is None


def test_terrain_defense_bonus_in_attack():
    # Warrior (attack=2) vs Warrior (defense=2) on FOREST (defense_bonus=1).
    # 2 < 2+1 → defender should survive.
    state, reg = _make_state({(11, 10): Terrain.FOREST})
    attacker = Unit(id=state.new_id(), type_name="Warrior", x=10, y=10, moves_left=1, owner="player")
    defender = Unit(id=state.new_id(), type_name="Warrior", x=11, y=10, moves_left=0, owner="ai_1")
    state.units.extend([attacker, defender])
    attack(state, reg, attacker, 11, 10)
    assert defender in state.units


def test_city_yields_from_terrain():
    # City on HILLS: food=0, prod=2, sci=0.
    state, reg = _make_state({(10, 10): Terrain.HILLS})
    city = City(id=state.new_id(), name="Hilly", x=10, y=10, owner="player")
    city.build_target = "Warrior"
    state.cities.append(city)
    end_turn(state, reg)
    assert city.production_stock == 2
    assert state.science == 1  # base science floor, HILLS has no terrain sci


def test_map_has_all_terrain_types():
    tiles = generate_map(20, 20, seed=42)
    found = {tiles[x][y].terrain for x in range(20) for y in range(20)}
    # Map should have more than just grass and water.
    assert len(found) > 2
    # Starting patch (centre 3x3) must all be city-foundable.
    cx, cy = 10, 10
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            assert tiles[cx + dx][cy + dy].terrain in CITY_FOUNDING_TERRAINS


# --- §8 Happiness & Population Cap tests ---

def test_happiness_single_city():
    state, reg = _new_game()
    settler = state.units[0]
    found_city(state, reg, settler, "Rome")
    end_turn(state, reg)
    assert state.happiness == 0  # first city has no penalty


def test_happiness_with_multiple_cities():
    state, reg = _new_game()
    settler = state.units[0]
    found_city(state, reg, settler, "Rome")
    second = City(id=state.new_id(), name="Athens", x=5, y=5, owner="player")
    state.cities.append(second)
    end_turn(state, reg)
    assert state.happiness == -1  # 2 cities → -1


def test_colosseum_raises_happiness():
    state, reg = _new_game()
    settler = state.units[0]
    city = found_city(state, reg, settler, "Rome")
    second = City(id=state.new_id(), name="Athens", x=5, y=5, owner="player")
    state.cities.append(second)
    city.buildings.append("Colosseum")
    end_turn(state, reg)
    # -1 for second city + 3 for Colosseum = +2
    assert state.happiness == 2


def test_population_cap_without_improvements():
    state, reg = _new_game()
    settler = state.units[0]
    city = found_city(state, reg, settler, "Rome")
    city.food_stock = 1000  # force-feed surplus
    for _ in range(30):
        end_turn(state, reg)
    assert city.population <= 2  # cap = 2 + 0 worked tiles


def test_happiness_blocks_growth():
    state, reg = _new_game()
    settler = state.units[0]
    city = found_city(state, reg, settler, "Rome")
    second = City(id=state.new_id(), name="Athens", x=5, y=5, owner="player")
    state.cities.append(second)
    city.food_stock = 1000
    for _ in range(10):
        end_turn(state, reg)
    # happiness is -1 (two cities, no happiness buildings) → growth blocked
    assert city.population == 1


# --- §9 Technology Tree tests ---

def test_granary_not_buildable_without_agriculture():
    reg = Registry()
    register_builtins(reg)
    opts = reg.buildable_options(set())
    assert "Granary" not in opts
    assert "Warrior" in opts   # no tech required


def test_granary_buildable_with_agriculture():
    reg = Registry()
    register_builtins(reg)
    opts = reg.buildable_options({"Agriculture"})
    assert "Granary" in opts


def test_tech_research_advances_and_completes():
    state, reg = _new_game()
    settler = state.units[0]
    found_city(state, reg, settler, "Rome")
    state.research.current_tech = "Agriculture"
    # Agriculture costs 20; city produces ~1 sci/turn → run 25 turns to be safe
    for _ in range(25):
        end_turn(state, reg)
    assert "Agriculture" in state.research.researched_techs
    assert state.research.current_tech is None
    assert reg.buildable_options(state.research.researched_techs).__contains__("Granary")


def test_tech_just_completed_flag():
    state, reg = _new_game()
    settler = state.units[0]
    found_city(state, reg, settler, "Rome")
    state.research.current_tech = "Agriculture"
    state.research.tech_progress = 19  # one beaker away (cost=20)
    end_turn(state, reg)  # city produces ≥1 sci → crosses threshold
    assert state.research.tech_just_completed == "Agriculture"
    assert state.research.current_tech is None
    assert state.research.tech_progress == 0


def test_available_techs_at_start():
    names = {t.name for t in available_techs(set())}
    assert "Agriculture" in names
    assert "Mining" in names
    assert "Writing" in names
    assert "Bronze Working" not in names  # prereq: Mining


def test_available_techs_with_prereq():
    names = {t.name for t in available_techs({"Mining"})}
    assert "Bronze Working" in names
    assert "Mining" not in names  # already researched


def test_population_cap_function():
    state, reg = _new_game()
    settler = state.units[0]
    city = found_city(state, reg, settler, "Rome")
    assert population_cap(state, city) == 2  # no improvements yet
