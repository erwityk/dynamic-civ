# Feature Backlog

Tracks unimplemented and partially-implemented features. Current state: single-player sandbox with a 20×20 procedural terrain map, combat and enemy AI, city yields (food/production/science/gold), a production queue, a 7-tech structured tech tree, global happiness, population cap, economy (gold/maintenance/purchasing), and AI-generated mod loading via the `claude` CLI.

---

## 1. Combat

**Status:** Logic stub exists in `engine/turn.py:attack()` but is never called from the UI. `app.py` comment reads: *"Solo sandbox: all units are friendly, so no attack path. Just move."*

### 1a. UI Integration
- Right-click an adjacent enemy unit to initiate an attack (or a separate "Attack" button when a unit with moves remaining is selected and an enemy is adjacent).
- Visual feedback: flash the defending tile red on hit, grey out the attacker when it expends its move attacking.
- Toast showing outcome: `"Warrior attacks Enemy Warrior — wins!"` or `"Warrior attacks Enemy Warrior — takes 2 damage (HP 8)"`.

### 1b. Combat Resolution
The current formula (`attack + bonus >= defense → instakill`) is too binary. Replace with a probabilistic model:
- Roll `d6 + attack` vs `d6 + defense`; loser loses HP equal to the margin (minimum 1).
- Both sides always take some damage (attacker takes half the losing roll); units are removed at HP ≤ 0.
- Expose the `on_attack` hook result as a flat bonus to the attacker's roll so mod-defined units actually feel different.

### 1c. Ranged Combat
- Add `range: int` field to `UnitType` (default 1 = melee). Ranged units (Archer, Catapult) can attack tiles within range without adjacency.
- Ranged attacker does not take counter-damage when `range > 1`.
- Reduce ranged unit `defense` stat to compensate.

### 1d. Terrain Combat Modifiers
- Forest/Hills give the defender +1 defense (see §5).
- City tile gives the defending unit +2 defense.

---

## 2. Enemy AI / Civilizations

**Status:** Not started. There is no concept of a second player or AI.

### 2a. Data Model
- Add `owner: str` field to `Unit` and `City` (e.g., `"player"`, `"ai_1"`).
- `GameState` holds a list of `Civilization` objects (name, color, owned units/cities).
- `attack()` should only proceed if attacker and target belong to different civs.

### 2b. AI Turn
Run after the player clicks "End Turn". Simple priority-ordered logic:
1. **Expand** — move Settlers toward unclaimed grass tiles, found cities.
2. **Defend** — move Warriors toward own cities that have no adjacent defender.
3. **Threaten** — if a Warrior is adjacent to a player city with no defender, attack.
4. **Build** — cities without a build target choose a Warrior or Granary based on needs.

Keep AI deterministic (seeded RNG per turn) so games are reproducible.

### 2c. Diplomacy (stretch)
- Player can declare war or propose peace via a sidebar button when a civ is selected.
- War state tracked per civ-pair; peace can be offered after N turns of conflict.

---

## 3. Currency & Economy

**Status: Implemented (§3a–3c).** Gold added to `GameState`. Cities produce 1 base gold/turn plus building bonuses. Unit maintenance deducted at end of turn; negative gold randomly disbands a unit. Market (+2 gold/turn), Mint (×2 gold multiplier), Aqueduct (−20% food-for-growth) registered as builtins. Buy button in city panel allows instant production completion for `remaining × 3` gold.

### 3a. Gold
- Add `gold: int` to `GameState` and `gold_per_turn: int` yield to cities (base 1, boosted by buildings like Market).
- Each unit costs `maintenance: int` gold per turn (Warriors cost 1, advanced units cost more). Cities cost 1 gold per turn regardless.
- If `gold < 0` at end of turn, randomly disband one unit.

### 3b. Buildings: Economic
- **Market** — +2 gold/turn per city.
- **Mint** — doubles gold output of the city.
- **Aqueduct** — reduces food needed for population growth by 20%.

### 3c. Purchasing
- Allow spending gold to instantly complete a unit or building currently in the production queue (cost = remaining production × 3 gold).
- "Buy" button in the city panel next to the current build target.

---

## 4. Trade

**Status:** Not started.

### 4a. Internal Trade Routes
- Once a city has a **Market**, it can send one trade route to another owned city.
- Each active route grants +1 gold and +1 production to both endpoints per turn.
- Routes are automatically established and displayed as a line on the map.

### 4b. Luxury Resources (see §6b)
- Luxury resources on the map can be harvested by a Worker improvement.
- Each unique luxury reduces the food cost of city growth by 1 (citizens are happier).

### 4c. AI Trade (stretch)
- AI civs can offer gold-per-turn deals in exchange for open borders or luxury access.

---

## 5. Terrain Types

**Status: Implemented (§5a–5b).** Six terrain types added (Plains, Forest, Hills, Mountain, Desert, Tundra) plus existing Grass/Water. Map generation uses diamond-square heightmap (`engine/map.py`). Terrain metadata (move cost, defense bonus, yields) is embedded on the `Terrain` enum in `engine/state.py`. Forest/Hills cost 2 moves; Mountain/Water are impassable. Cities may only be founded on Grass or Plains. Terrain defense bonus wired into `attack()`. City yields derived from tile terrain. Not yet implemented: 5c rivers, Worker tile improvements (§7).

---

## 6. Resources

**Status:** Not started.

### 6a. Strategic Resources
Strategic resources gate advanced units. Examples: Iron (Swordsman), Horses (Cavalry), Coal (Musketman).

- Resources are placed on the map at gen time (seeded), hidden until a unit enters the tile.
- A city can only train resource-requiring units if its territory contains that resource AND a Worker has built an improvement on it.
- Add `requires_resource: str | None` to `UnitType`.

### 6b. Luxury Resources
Gems, Silk, Spices, etc. Harvested by Worker improvement; each unique luxury in your empire gives +1 happiness (see §8b).

---

## 7. City Improvements (Worker Actions)

**Status:** Not started. No Worker unit type; no tile improvements.

- Add a `Worker` unit type (`can_found_city=False`, no attack, moves 2).
- Workers can spend turns improving the tile they occupy:
  - **Farm** on Grass/Plains: +1 food.
  - **Mine** on Hills: +1 production.
  - **Lumber Camp** on Forest: +1 production, removes forest (loses defense bonus).
  - **Road** on any passable tile: movement through the tile costs 0.5 instead of the base cost.
  - **Harvest Resource** on a resource tile: activates its strategic/luxury bonus.
- Improvements stored as `tile.improvement: str | None` on `Tile`.
- Workers track `turns_remaining: int`; improvement completes when it hits 0.

---

## 8. Happiness & Population Cap

**Status: Implemented (§8a–§8b).** Global `happiness` added to `GameState`, recomputed each `end_turn`. Each city beyond the first costs 1 happiness; Temple (+2) and Colosseum (+3) registered as builtins. If `happiness < 0`, city growth is blocked and units get −1 effective attack. Population hard-capped at `2 + worked tiles`; expands to full effect once §7 Workers are built (currently always 2). Top bar shows happiness in red when negative; city panel shows `Pop X/Y`.

Not yet implemented: happiness from luxury resources (§6b), happiness cost for units at war (§2).

### 8a. Happiness
- Global `happiness: int` on `GameState`. Starts at 0.
- Each city beyond the first costs 1 happiness. Each unit at war costs 1 happiness.
- Luxury resources (§6b) grant +1 happiness each.
- Happiness buildings: Colosseum (+3), Temple (+2).
- If `happiness < 0`: cities stop growing and units get -1 attack.

### 8b. Population Cap
- City population hard-capped at `2 + number of worked tiles` (tiles within city radius that have improvements).

---

## 9. Technology Tree

**Status: Implemented (§9a–§9b).** Seven-tech DAG defined in `engine/tech.py` (Agriculture, Mining, Writing, Bronze Working, Mathematics, Currency, Horseback Riding). `ResearchState` extended with `researched_techs`, `current_tech`, `tech_progress`, `tech_just_completed`. Tech advances by `sci_gained` each turn; completion unlocks buildings and units via `requires_tech` filter in `registry.buildable_options()`. New builtins: Library, Workshop, Spearman, Cavalry, Catapult. Existing builtins Granary, Market, and Aqueduct now gated behind their respective techs. Sidebar panel split into Technology (tech picker / progress / completion banner with Invent/Dismiss) and Invention (free-form Claude pipeline) sections.

### 9a. Structured Techs
Separate from the free-form research. A predefined DAG of technologies unlocks buildings and units:

```
Agriculture → Granary (already buildable without it — fix this)
Mining → Workshop (+1 prod), Mine improvement
Writing → Library (+2 sci), enables science victory progress
Bronze Working → Spearman, unlocks Iron resource
Horseback Riding → Cavalry (requires Horses resource)
Mathematics → Catapult (ranged, siege), unlocks Aqueduct
Currency → Market (+2 gold)
...
```

- `ResearchState` extended with `researched_techs: set[str]` and `current_tech: str | None`.
- Choosing a tech starts an accumulation cycle (cost in science beakers). On completion the tech is added to `researched_techs` and its unlocks become available in the build queue.
- Display current tech and progress bar in the sidebar (replace or augment the existing research panel).

### 9b. Free-Form Research (current system)
Keep as a separate "Invention" mechanic. After a structured tech is completed the player can optionally spend extra accumulated science to trigger the Claude mod-generation pipeline — producing a novel unit or building thematically inspired by the tech just discovered.

---

## 10. Victory Conditions

**Status:** Not started. Game runs indefinitely.

| Victory Type | Condition |
|---|---|
| **Domination** | Capture every enemy civilization's original capital city. |
| **Science** | Research a late-game tech (e.g., "Space Flight") and complete the Space Colony wonder. |
| **Cultural** | Accumulate N total culture points (generated by cultural buildings). |
| **Time** | Highest score at turn 300 (turns: cities × pop + units + science + gold). |

- On victory: freeze input, display a full-screen banner with victory type and final score, offer New Game.
- On defeat (all cities captured, no Settler to re-found): display a defeat screen.

---

## 11. Unit Progression

**Status:** Not started. Units have HP but no XP or promotions.

- Add `xp: int` to `Unit`. Each kill grants `+2 XP`; surviving combat (taking damage) grants `+1 XP`.
- At `10 XP`: choose one promotion from a small list relevant to the unit type:
  - **Medic I** — this unit heals adjacent friendly units 1 HP per turn.
  - **Drill I** — +1 attack.
  - **Fortify I** — +1 defense when not moved this turn.
  - **Blitz** — can attack twice per turn (costs all moves).
- Promoted units display a star glyph overlay on the map.

### 11a. Healing
- Units not moved or attacked during a turn heal 2 HP at end of turn.
- Units in a city heal 4 HP at end of turn.
- HP cap is `UnitType`-specific (stored on `UnitType`, default 10).

---

## 12. City Borders & Culture

**Status:** Not started. Cities have no territory.

- Add `culture: int` to `City`. Generated by cultural buildings (Temple, Library).
- City border radius expands at culture thresholds: starts radius 1 (3×3 area), grows to radius 2, then 3.
- Only tiles within a city's border contribute their yields to that city and can host Worker improvements.
- Render city territory as a faint colored overlay on claimed tiles.
- Enemy units entering claimed territory without an open-borders agreement trigger a warning toast.

---

## 13. Fog of War

**Status:** Not started. The entire map is always visible.

- Each tile has a `visibility: "hidden" | "explored" | "visible"` field.
- A tile is `"visible"` if any friendly unit or city is within sight range (default 2 tiles for most units, 3 for Scouts).
- `"explored"` tiles show their last-known state (terrain, improvements) but not current units or cities.
- `"hidden"` tiles render as solid black.
- Units on explored-but-not-visible tiles are hidden from the player (but AI still acts on them).

---

## 14. Save & Load

**Status:** Not started.

- Serialize `GameState` and `Registry` (excluding mod callbacks) to JSON via `dataclasses.asdict`.
- Prompt for a save slot (1–3) from the sidebar or a menu.
- On load: regenerate the map from stored tile data, re-run all loaded mod files to reconstruct `on_attack` callbacks, restore all other state.
- Auto-save at the start of each turn to a fixed slot.

---

## 15. Wonders

**Status:** Not started.

One-per-game buildings that can be constructed by any civ; once built, all other civs lose the ability to build it.

| Wonder | Effect |
|---|---|
| Pyramids | All your cities get a free Granary immediately. |
| Great Library | All future techs cost 10% less science. |
| Colosseum | +3 happiness empire-wide. |
| Hanging Gardens | All cities get +2 food permanently. |
| Space Colony | Triggers science victory when built (requires Space Flight tech). |

- Wonders tracked in `GameState.built_wonders: set[str]`.
- Build queue shows Wonders in a separate section; greyed out if already built.

---

## 16. Naval Units & Exploration

**Status:** Not started. Water tiles are completely impassable.

- Add a `can_traverse_water: bool` flag to `UnitType`.
- **Galley** / **Caravel** unit types that can move on water tiles.
- Land units can embark (move onto water) if a Harbour building exists in an adjacent city — costs all movement that turn.
- Embarked land units have `defense=1` and cannot attack.

---

## 17. Audio & Visual Polish

**Status:** Not started. No sound. No animations.

- Sound effects on: unit movement, combat, city founded, end turn, research complete.
- Short animation on unit death (fade-out over 3 frames).
- Map camera scroll when the map grows larger than the viewport (currently fixed 20×20 fits the window; larger maps will need panning with arrow keys or edge-scroll).
- Minimap in bottom-left corner showing terrain and city dots.
- Unit HP bar drawn as a small green/red strip below the unit shape.
- City population number displayed on the city tile.

---

## 18. Difficulty Settings

**Status:** Not started.

- **Chieftain** — AI builds slower, starts with fewer units.
- **Warlord** — Default balanced.
- **Emperor** — AI starts with an extra Warrior and Settler; gets +50% production.
- Difficulty applied via a multiplier on AI city yields at `end_turn`.

---

## Priority Order (suggested)

| Priority | Feature | Status |
|---|---|---|
| 1 | Combat UI (§1a) | **Done** |
| 2 | Enemy AI basics (§2a–2b) | **Done** |
| 3 | Terrain types (§5a–5b) | **Done** |
| 4 | Technology tree (§9a) | **Done** |
| 5 | Currency & economy (§3) | **Done** |
| 6 | Happiness & population cap (§8) | **Done** |
| 7 | Victory conditions (§10) — gives the game an end | — |
| 8 | Fog of war (§13) — changes exploration incentive | — |
| 9 | Unit progression (§11) — rewards keeping units alive | — |
| 10 | Workers & improvements (§7) — tile optimization layer | — |
| 11 | Save/Load (§14) — quality of life | — |
