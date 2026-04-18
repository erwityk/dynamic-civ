from __future__ import annotations

from typing import Callable, Optional

import pygame

from pathlib import Path

from engine.registry import Registry
from engine.state import City, GameState, Terrain, Unit, VictoryResult
from engine.ai import run_ai_turn
from engine.improvements import IMPROVEMENT_TURNS, valid_improvements
from engine.save import load_game, save_exists, save_game
from engine.turn import attack, check_victory, embark_unit, end_turn, found_city, move_unit, population_cap, purchase_build, reset_unit_moves, worker_improve
from engine.tech import TECHS, available_techs
from render.draw import GRID_ORIGIN, TILE, draw_city, draw_city_borders, draw_improvements, draw_map, draw_minimap, draw_top_bar, draw_unit, screen_to_tile, tile_to_screen
from render.ui import Button, TextInput, Toasts

WINDOW_W = 1000
WINDOW_H = 720
SIDEBAR_X = GRID_ORIGIN[0] + 20 * TILE + 16  # right edge of map + gap
SIDEBAR_W = WINDOW_W - SIDEBAR_X - 8
RESEARCH_PANEL_H = 280

ResearchTrigger = Callable[[str], None]  # invoked with the player's research prompt


class App:
    def __init__(self, state: GameState, reg: Registry, research_trigger: Optional[ResearchTrigger] = None,
                 research_poll: Optional[Callable[[], None]] = None,
                 reset_callback: Optional[Callable[[], tuple[GameState, Registry]]] = None,
                 repo_root: Optional[Path] = None):
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass
        pygame.display.set_caption("Dynamic Civ")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_sm = pygame.font.SysFont("consolas", 12)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)
        self._sounds: dict[str, object] = self._load_sounds(repo_root)

        self.state = state
        self.reg = reg
        self.research_trigger = research_trigger
        self.research_poll = research_poll
        self.reset_callback = reset_callback
        self.repo_root = repo_root

        self.selected_unit: Optional[Unit] = None
        self.selected_city: Optional[City] = None
        self.toasts = Toasts()
        self._city_counter = 0
        self._pending_promotion_unit: Optional[Unit] = None
        self.promotion_buttons: list[Button] = []
        self.improve_buttons: list[Button] = []
        self._show_difficulty_select = True
        self._difficulty_buttons: list[Button] = []
        self._init_difficulty_buttons()

        self.end_turn_btn = Button(
            rect=pygame.Rect(SIDEBAR_X, 40, SIDEBAR_W, 36),
            label="End Turn",
            on_click=self._on_end_turn,
        )
        self.found_btn = Button(
            rect=pygame.Rect(SIDEBAR_X, 0, SIDEBAR_W, 28),
            label="Found City",
            on_click=self._on_found_city,
        )
        self.research_input = TextInput(
            rect=pygame.Rect(SIDEBAR_X, 0, SIDEBAR_W, 28),
            placeholder="e.g. magic ogre, steam scout...",
        )
        self.research_btn = Button(
            rect=pygame.Rect(SIDEBAR_X, 0, SIDEBAR_W, 28),
            label="Start Research",
            on_click=self._on_start_research,
        )
        self.new_game_btn = Button(
            rect=pygame.Rect(WINDOW_W // 2 - 100, WINDOW_H // 2 + 60, 200, 40),
            label="New Game",
            on_click=self._on_new_game,
        )
        # Build-queue option buttons, rebuilt each frame based on registry.
        self.build_buttons: list[Button] = []
        # Buy button for instant production completion; rebuilt each frame.
        self.buy_btn: Optional[Button] = None
        # Tech-selection buttons, rebuilt each frame.
        self.tech_buttons: list[Button] = []
        # Invention/dismiss buttons shown after a tech completes.
        self.invent_btn = Button(
            rect=pygame.Rect(SIDEBAR_X, 0, SIDEBAR_W, 26),
            label="Invent!",
            on_click=self._on_invent,
        )
        self.dismiss_btn = Button(
            rect=pygame.Rect(SIDEBAR_X, 0, SIDEBAR_W, 26),
            label="Dismiss",
            on_click=self._on_dismiss_tech,
        )
        btn_w = (SIDEBAR_W - 4) // 3
        self.save_buttons = [
            Button(rect=pygame.Rect(SIDEBAR_X + i * (btn_w + 2), 0, btn_w, 24),
                   label=f"Save {i + 1}", on_click=self._on_save(i + 1))
            for i in range(3)
        ]
        self.load_buttons = [
            Button(rect=pygame.Rect(SIDEBAR_X + i * (btn_w + 2), 0, btn_w, 24),
                   label=f"Load {i + 1}", on_click=self._on_load(i + 1))
            for i in range(3)
        ]

    def _load_sounds(self, repo_root: Optional[Path]) -> dict[str, object]:
        sounds = {}
        if repo_root is None:
            return sounds
        sound_dir = repo_root / "assets" / "sounds"
        names = ["move", "combat", "found_city", "end_turn", "research"]
        for name in names:
            for ext in ("ogg", "wav"):
                path = sound_dir / f"{name}.{ext}"
                if path.exists():
                    try:
                        sounds[name] = pygame.mixer.Sound(str(path))
                    except Exception:
                        pass
                    break
        return sounds

    def _play_sound(self, name: str) -> None:
        s = self._sounds.get(name)
        if s is not None:
            try:
                s.play()  # type: ignore[union-attr]
            except Exception:
                pass

    def _init_difficulty_buttons(self) -> None:
        labels = [("Chieftain", "chieftain"), ("Warlord", "warlord"), ("Emperor", "emperor")]
        btn_w = (SIDEBAR_W - 4) // 3
        cy = WINDOW_H // 2 + 10
        self._difficulty_buttons = [
            Button(rect=pygame.Rect(WINDOW_W // 2 - SIDEBAR_W // 2 + i * (btn_w + 2), cy, btn_w, 36),
                   label=label, on_click=self._on_select_difficulty(diff))
            for i, (label, diff) in enumerate(labels)
        ]

    def _on_select_difficulty(self, difficulty: str) -> Callable[[], None]:
        def fn() -> None:
            self._show_difficulty_select = False
            ref = getattr(self, "_difficulty_ref", None)
            if ref is not None:
                ref["value"] = difficulty
            if self.reset_callback:
                self.state, self.reg = self.reset_callback()
                self.selected_unit = None
                self.selected_city = None
                self._pending_promotion_unit = None
                self.toasts = Toasts()
                self.toasts.add(f"Difficulty: {difficulty.capitalize()}")
        return fn

    def _draw_difficulty_select(self) -> None:
        overlay = pygame.Surface((WINDOW_W, WINDOW_H))
        overlay.set_alpha(230)
        overlay.fill((10, 10, 20))
        self.screen.blit(overlay, (0, 0))
        cx = WINDOW_W // 2
        font_title = pygame.font.SysFont("consolas", 36, bold=True)
        t = font_title.render("Choose Difficulty", True, (240, 240, 240))
        self.screen.blit(t, t.get_rect(center=(cx, WINDOW_H // 2 - 60)))
        descs = {
            "Chieftain": "AI builds slowly. Good for learning.",
            "Warlord": "Balanced. Default experience.",
            "Emperor": "AI gets +50% yields and an extra Warrior.",
        }
        for btn in self._difficulty_buttons:
            btn.draw(self.screen, self.font_big)
            dy = descs.get(btn.label, "")
            lbl = self.font_sm.render(dy, True, (180, 180, 200))
            self.screen.blit(lbl, lbl.get_rect(center=(btn.rect.centerx, btn.rect.bottom + 14)))

    # ---------- button callbacks ----------

    def _on_end_turn(self) -> None:
        self._play_sound("end_turn")
        try:
            save_game(self.state, slot=0)  # auto-save slot 0
        except Exception:
            pass
        end_turn(self.state, self.reg)
        run_ai_turn(self.state, self.reg)
        check_victory(self.state, self.reg)  # catches defeat after AI kills last city/settler
        self.selected_unit = None
        self.toasts.add(f"Turn {self.state.turn}")

    def _on_save(self, slot: int) -> Callable[[], None]:
        def fn() -> None:
            try:
                save_game(self.state, slot)
                self.toasts.add(f"Game saved to slot {slot}")
            except Exception as e:
                self.toasts.add(f"Save failed: {e}", color=(180, 60, 60))
        return fn

    def _on_load(self, slot: int) -> Callable[[], None]:
        def fn() -> None:
            if not save_exists(slot):
                self.toasts.add(f"No save in slot {slot}", color=(140, 40, 40))
                return
            try:
                self.state, self.reg = load_game(slot, repo_root=self.repo_root)
                self.selected_unit = None
                self.selected_city = None
                self._pending_promotion_unit = None
                self.toasts = Toasts()
                self.toasts.add(f"Game loaded from slot {slot}")
            except Exception as e:
                self.toasts.add(f"Load failed: {e}", color=(180, 60, 60))
        return fn

    def _on_found_city(self) -> None:
        if not self.selected_unit:
            return
        self._city_counter += 1
        name = f"City {self._city_counter}"
        city = found_city(self.state, self.reg, self.selected_unit, name)
        if city:
            self._play_sound("found_city")
            self.toasts.add(f"Founded {name}")
            self.selected_unit = None
            self.selected_city = city
        else:
            self.toasts.add("Cannot found here", color=(140, 40, 40))

    def _on_start_research(self) -> None:
        prompt = self.research_input.value.strip()
        if not prompt:
            self.toasts.add("Enter a research idea first", color=(140, 40, 40))
            return
        if self.state.research.status in ("accumulating", "generating"):
            self.toasts.add("Research already in progress", color=(140, 40, 40))
            return
        self.state.research.prompt = prompt
        self.state.research.progress = 0
        self.state.research.cost = 5
        self.state.research.status = "accumulating"
        self.state.research.error = None
        self.state.research.last_result_name = None
        self.toasts.add(f"Researching: {prompt}")

    def _on_select_tech(self, tech_name: str) -> Callable[[], None]:
        def fn() -> None:
            r = self.state.research
            if r.current_tech is not None:
                self.toasts.add("Already researching a tech", color=(140, 40, 40))
                return
            r.current_tech = tech_name
            r.tech_progress = 0
            self.toasts.add(f"Now researching {tech_name}")
        return fn

    def _on_invent(self) -> None:
        r = self.state.research
        if r.tech_just_completed is None:
            return
        if r.status in ("accumulating", "generating"):
            self.toasts.add("Invention already in progress", color=(140, 40, 40))
            return
        seed = r.tech_just_completed
        r.tech_just_completed = None
        r.prompt = seed
        r.progress = 0
        r.cost = 5
        r.status = "accumulating"
        r.error = None
        r.last_result_name = None
        self.research_input.value = seed
        self.toasts.add(f"Inventing inspired by {seed}!")

    def _on_dismiss_tech(self) -> None:
        self.state.research.tech_just_completed = None
        self.toasts.add("Discovery noted.")

    def _on_new_game(self) -> None:
        self._show_difficulty_select = True
        self.selected_unit = None
        self.selected_city = None
        self._pending_promotion_unit = None
        self.toasts = Toasts()
        self._city_counter = 0

    def _on_choose_promotion(self, unit: Unit, promo: str) -> Callable[[], None]:
        def fn() -> None:
            unit.promotions.append(promo)
            unit.promotion_pending = False
            unit.xp = 0
            self._pending_promotion_unit = None
            self.promotion_buttons = []
            self.toasts.add(f"{unit.type_name} gained {promo}!")
        return fn

    def _set_build(self, city: City, target: str) -> Callable[[], None]:
        def fn() -> None:
            city.build_target = target
            self.toasts.add(f"{city.name} now building {target}")
        return fn

    def _on_buy(self, city: City) -> Callable[[], None]:
        def fn() -> None:
            target = city.build_target
            if purchase_build(self.state, self.reg, city):
                self.toasts.add(f"Purchased {target} for {city.name}")
            else:
                self.toasts.add("Not enough gold", color=(140, 40, 40))
        return fn

    # ---------- event handling ----------

    def _handle_map_click(self, mx: int, my: int, button: int) -> None:
        t = screen_to_tile(mx, my, self.state)
        if t is None:
            return
        tx, ty = t
        # Left click: select or move.
        if button == 1:
            city_here = self.state.city_at(tx, ty)
            unit_here = self.state.unit_at(tx, ty)
            if self.selected_unit:
                # Only move onto empty tiles; enemy tiles require right-click attack.
                if unit_here is None and move_unit(self.state, self.selected_unit, tx, ty, self.reg):
                    self._play_sound("move")
                    return
            # Otherwise: selection.
            if unit_here is not None:
                self.selected_unit = unit_here
                self.selected_city = None
            elif city_here is not None:
                self.selected_city = city_here
                self.selected_unit = None
            else:
                self.selected_unit = None
                self.selected_city = None
        # Right click: attack.
        elif button == 3:
            if self.selected_unit is None:
                return
            target = self.state.unit_at(tx, ty)
            if target is None or target.owner == self.selected_unit.owner:
                return
            self._do_attack(self.selected_unit, target, tx, ty)

    def _do_attack(self, attacker: Unit, target: Unit, tx: int, ty: int) -> None:
        """Attempt attack and display a toast with the outcome."""
        atk_name = attacker.type_name
        def_name = target.type_name
        attacker_hp_before = attacker.hp

        success = attack(self.state, self.reg, attacker, tx, ty)
        if not success:
            return  # out of moves, out of range, or other precondition failed
        self._play_sound("combat")

        attacker_dead = attacker not in self.state.units
        target_dead = self.state.unit_at(tx, ty) is None

        if attacker_dead:
            self.toasts.add(f"{atk_name} attacks {def_name} — attacker lost!", color=(180, 60, 60))
            self.selected_unit = None
        elif target_dead:
            self.toasts.add(f"{atk_name} attacks {def_name} — wins!", color=(60, 180, 60))
        else:
            dmg = attacker_hp_before - attacker.hp
            self.toasts.add(f"{atk_name} attacks {def_name} — takes {dmg} damage (HP {attacker.hp})", color=(200, 160, 60))
        if not attacker_dead and attacker.promotion_pending:
            self._pending_promotion_unit = attacker
            self.toasts.add(f"{atk_name} earned a promotion!", color=(255, 220, 60))

    def _poll_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            # Difficulty selection overlay takes full focus.
            if self._show_difficulty_select:
                for b in self._difficulty_buttons:
                    if b.handle(event):
                        break
                continue
            # When game is over, only the New Game button is active.
            if self.state.game_over is not None:
                self.new_game_btn.handle(event)
                continue
            if self.end_turn_btn.handle(event):
                continue
            # Sidebar buttons only active when their panel is showing.
            if self._settler_selected() and self.found_btn.handle(event):
                continue
            if self.research_input.handle(event):
                continue
            if self.research_btn.handle(event):
                continue
            if self.invent_btn.enabled and self.invent_btn.handle(event):
                continue
            if self.dismiss_btn.enabled and self.dismiss_btn.handle(event):
                continue
            for b in self.tech_buttons:
                if b.handle(event):
                    break
            if self.buy_btn and self.buy_btn.handle(event):
                continue
            for b in self.build_buttons:
                if b.handle(event):
                    break
            for b in self.promotion_buttons:
                if b.handle(event):
                    break
            for b in self.improve_buttons:
                if b.handle(event):
                    break
            for b in self.save_buttons + self.load_buttons:
                if b.handle(event):
                    break
            if event.type == pygame.MOUSEBUTTONDOWN and event.pos[0] < SIDEBAR_X - 8:
                self._handle_map_click(event.pos[0], event.pos[1], event.button)
            if event.type == pygame.KEYDOWN and not self.research_input.active:
                if event.key == pygame.K_SPACE:
                    self._on_end_turn()
                elif event.key == pygame.K_f and self._settler_selected():
                    self._on_found_city()
        return True

    def _settler_selected(self) -> bool:
        if not self.selected_unit:
            return False
        ut = self.reg.unit_types.get(self.selected_unit.type_name)
        return bool(ut and ut.can_found_city)

    def _worker_selected(self) -> bool:
        if not self.selected_unit:
            return False
        ut = self.reg.unit_types.get(self.selected_unit.type_name)
        return bool(ut and ut.can_improve)

    def _on_embark(self, unit: Unit) -> Callable[[], None]:
        def fn() -> None:
            if embark_unit(self.state, self.reg, unit):
                self.toasts.add(f"{unit.type_name} embarked onto water")
            else:
                self.toasts.add("Cannot embark here — need Harbour nearby", color=(140, 40, 40))
        return fn

    def _on_improve(self, unit: Unit, name: str) -> Callable[[], None]:
        def fn() -> None:
            if worker_improve(self.state, self.reg, unit, name):
                self.toasts.add(f"Worker starts {name} ({unit.improvement_turns_left} turns)")
            else:
                self.toasts.add(f"Cannot build {name} here", color=(140, 40, 40))
        return fn

    # ---------- drawing ----------

    def _draw_sidebar(self) -> None:
        # Sidebar background.
        pygame.draw.rect(self.screen, (30, 30, 40), (SIDEBAR_X - 8, 32, WINDOW_W - (SIDEBAR_X - 8), WINDOW_H - 32))
        y = 40
        self.end_turn_btn.rect.topleft = (SIDEBAR_X, y)
        self.end_turn_btn.draw(self.screen, self.font)
        y += 44

        # Unit panel
        if self.selected_unit and not self.selected_city:
            y = self._draw_unit_panel(y)

        # City panel
        if self.selected_city:
            y = self._draw_city_panel(y)

        # Research panel (always visible at bottom-ish)
        self._draw_research_panel()
        self._draw_save_load_panel()

    def _draw_label(self, x: int, y: int, text: str, color=(230, 230, 230), font=None) -> int:
        f = font or self.font
        for line in text.split("\n"):
            surf = f.render(line, True, color)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 2
        return y

    def _draw_unit_panel(self, y: int) -> int:
        u = self.selected_unit
        if u is None:
            return y
        ut = self.reg.unit_types.get(u.type_name)
        y = self._draw_label(SIDEBAR_X, y, f"Unit: {u.type_name}", font=self.font_big)
        if ut:
            stats = f"Atk {ut.attack}  Def {ut.defense}  Move {ut.move}"
            if ut.range > 1:
                stats += f"  Range {ut.range}"
            y = self._draw_label(SIDEBAR_X, y, stats)
            y = self._draw_label(SIDEBAR_X, y, f"HP {u.hp}  Moves left {u.moves_left}")
            xp_str = f"XP {u.xp}/10"
            if u.promotions:
                xp_str += "  [" + ", ".join(u.promotions) + "]"
            y = self._draw_label(SIDEBAR_X, y, xp_str, color=(200, 200, 140), font=self.font_sm)
            y = self._draw_label(SIDEBAR_X, y, _wrap(ut.description, 42), color=(180, 180, 200), font=self.font_sm)
        # Promotion choice UI
        if self._pending_promotion_unit is u:
            y = self._draw_label(SIDEBAR_X, y, "Choose promotion:", color=(255, 220, 60))
            available = [p for p in ("Drill I", "Fortify I", "Blitz") if p not in u.promotions]
            self.promotion_buttons = []
            for promo in available:
                btn = Button(
                    rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 26),
                    label=promo,
                    on_click=self._on_choose_promotion(u, promo),
                )
                btn.draw(self.screen, self.font)
                self.promotion_buttons.append(btn)
                y += 28
        if self._settler_selected():
            self.found_btn.rect.topleft = (SIDEBAR_X, y + 4)
            self.found_btn.draw(self.screen, self.font)
            y += 36
        # Embark button for non-naval land units
        if ut and not ut.can_traverse_water and not u.embarked and u.owner == "player":
            embark_btn = Button(
                rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 28),
                label="Embark",
                on_click=self._on_embark(u),
            )
            embark_btn.draw(self.screen, self.font)
            y += 32
        elif u.embarked:
            y = self._draw_label(SIDEBAR_X, y, "[Embarked]", color=(80, 160, 255), font=self.font_sm)
        # Worker improvement UI
        if self._worker_selected():
            self.improve_buttons = []
            if u.build_improvement is not None:
                y = self._draw_label(SIDEBAR_X, y, f"Building: {u.build_improvement}",
                                     color=(180, 220, 140))
                self._draw_progress(SIDEBAR_X, y, IMPROVEMENT_TURNS.get(u.build_improvement, 1) - u.improvement_turns_left,
                                    IMPROVEMENT_TURNS.get(u.build_improvement, 1))
                y += 14
                y = self._draw_label(SIDEBAR_X, y,
                                     f"{u.improvement_turns_left} turn(s) left",
                                     color=(160, 200, 130), font=self.font_sm)
            else:
                tile = self.state.tile(u.x, u.y)
                eligible = valid_improvements(tile.terrain) if tile else []
                if eligible:
                    y = self._draw_label(SIDEBAR_X, y, "Build improvement:", color=(200, 200, 220))
                    for imp_name in eligible:
                        btn = Button(
                            rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 24),
                            label=imp_name,
                            on_click=self._on_improve(u, imp_name),
                        )
                        btn.enabled = u.moves_left > 0
                        btn.draw(self.screen, self.font_sm)
                        self.improve_buttons.append(btn)
                        y += 26
                else:
                    y = self._draw_label(SIDEBAR_X, y, "No improvements available",
                                         color=(140, 140, 160), font=self.font_sm)
        return y + 6

    def _draw_city_panel(self, y: int) -> int:
        c = self.selected_city
        if c is None:
            return y
        y = self._draw_label(SIDEBAR_X, y, f"{c.name}", font=self.font_big)
        cap = population_cap(self.state, c)
        y = self._draw_label(SIDEBAR_X, y, f"Pop {c.population}/{cap}  Food {c.food_stock}  Prod {c.production_stock}")
        y = self._draw_label(SIDEBAR_X, y, f"Culture {c.culture}", color=(200, 160, 220), font=self.font_sm)
        y = self._draw_label(SIDEBAR_X, y, f"Buildings: {', '.join(c.buildings) or 'none'}", color=(180, 180, 200), font=self.font_sm)
        y = self._draw_label(SIDEBAR_X, y, f"Building: {c.build_target or 'nothing'}")
        self.buy_btn = None
        if c.build_target:
            ttype = self.reg.unit_types.get(c.build_target) or self.reg.building_types.get(c.build_target)
            if ttype is not None:
                remaining = max(0, ttype.cost - c.production_stock)
                price = remaining * 3
                self.buy_btn = Button(
                    rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 24),
                    label=f"Buy ({price} gold)",
                    on_click=self._on_buy(c),
                )
                self.buy_btn.enabled = self.state.gold >= price
                self.buy_btn.draw(self.screen, self.font_sm)
                y += 28
        y += 4
        y = self._draw_label(SIDEBAR_X, y, "Set production:", color=(200, 200, 220))
        self.build_buttons = []
        options = self.reg.buildable_options(
            self.state.research.researched_techs, self.state.built_wonders)
        for name in options:
            bt = self.reg.building_types.get(name)
            is_wonder = bt is not None and bt.is_wonder
            label = name + (" *" if c.build_target == name else "")
            if is_wonder:
                label = f"[W] {label}"
            btn = Button(
                rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 24),
                label=label,
                on_click=self._set_build(c, name),
            )
            btn.draw(self.screen, self.font_sm)
            self.build_buttons.append(btn)
            y += 26
        return y + 6

    def _draw_research_panel(self) -> None:
        panel_top = WINDOW_H - RESEARCH_PANEL_H
        pygame.draw.rect(self.screen, (40, 40, 55),
                         (SIDEBAR_X - 8, panel_top, WINDOW_W - (SIDEBAR_X - 8), RESEARCH_PANEL_H))
        y = panel_top + 8
        r = self.state.research
        self.research_btn.enabled = False
        self.tech_buttons = []
        self.invent_btn.enabled = False
        self.dismiss_btn.enabled = False

        # --- Section A: Technology ---
        y = self._draw_label(SIDEBAR_X, y, "Technology", font=self.font_big)

        if r.tech_just_completed:
            y = self._draw_label(SIDEBAR_X, y, f"Discovered: {r.tech_just_completed}!",
                                 color=(180, 255, 180))
            self.invent_btn.rect.topleft = (SIDEBAR_X, y)
            self.invent_btn.enabled = True
            self.invent_btn.draw(self.screen, self.font_sm)
            y += 30
            self.dismiss_btn.rect.topleft = (SIDEBAR_X, y)
            self.dismiss_btn.enabled = True
            self.dismiss_btn.draw(self.screen, self.font_sm)
            y += 30
        elif r.current_tech:
            tech = TECHS.get(r.current_tech)
            cost = tech.cost if tech else 1
            y = self._draw_label(SIDEBAR_X, y, f"Researching: {r.current_tech}",
                                 color=(220, 220, 180))
            self._draw_progress(SIDEBAR_X, y, r.tech_progress, cost)
            y += 14
            y = self._draw_label(SIDEBAR_X, y, f"{r.tech_progress}/{cost} beakers",
                                 font=self.font_sm)
        else:
            avail = available_techs(r.researched_techs)
            if avail:
                y = self._draw_label(SIDEBAR_X, y, "Choose research:", color=(200, 200, 220))
                for tech in avail[:5]:  # cap display to avoid overflow
                    btn = Button(
                        rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 22),
                        label=f"{tech.name} ({tech.cost})",
                        on_click=self._on_select_tech(tech.name),
                    )
                    btn.draw(self.screen, self.font_sm)
                    self.tech_buttons.append(btn)
                    y += 24
            else:
                y = self._draw_label(SIDEBAR_X, y, "All techs researched!",
                                     color=(180, 240, 180))

        if r.researched_techs:
            label = "Done: " + ", ".join(sorted(r.researched_techs))
            y = self._draw_label(SIDEBAR_X, y, _wrap(label, 42), color=(140, 140, 160),
                                 font=self.font_sm)

        # Divider between sections
        pygame.draw.line(self.screen, (60, 60, 80),
                         (SIDEBAR_X - 8, y + 3), (WINDOW_W, y + 3))
        y += 9

        # --- Section B: Invention (free-form research) ---
        y = self._draw_label(SIDEBAR_X, y, "Invention", font=self.font_big)

        if r.status == "idle":
            self.research_input.rect.topleft = (SIDEBAR_X, y)
            self.research_input.draw(self.screen, self.font)
            y += 32
            self.research_btn.rect.topleft = (SIDEBAR_X, y)
            self.research_btn.label = "Start Research"
            self.research_btn.on_click = self._on_start_research
            self.research_btn.enabled = bool(self.research_input.value.strip())
            self.research_btn.draw(self.screen, self.font)
        elif r.status == "accumulating":
            y = self._draw_label(SIDEBAR_X, y, f"Researching: {r.prompt}", color=(220, 220, 180))
            self._draw_progress(SIDEBAR_X, y, r.progress, r.cost)
            y += 14
            y = self._draw_label(SIDEBAR_X, y, f"{r.progress}/{r.cost} science", font=self.font_sm)
        elif r.status == "generating":
            y = self._draw_label(SIDEBAR_X, y, f"Inventing: {r.prompt}", color=(220, 200, 120))
            tick = (pygame.time.get_ticks() // 300) % 4
            y = self._draw_label(SIDEBAR_X, y, "Claude is working" + "." * tick,
                                 color=(200, 200, 220))
        elif r.status == "done":
            y = self._draw_label(SIDEBAR_X, y, f"Discovered: {r.last_result_name}",
                                 color=(180, 240, 180))
            y = self._draw_label(SIDEBAR_X, y, "(now buildable in cities)",
                                 color=(160, 200, 160), font=self.font_sm)
            self.research_btn.rect.topleft = (SIDEBAR_X, y + 6)
            self.research_btn.label = "Research Again"
            self.research_btn.on_click = self._on_research_again
            self.research_btn.enabled = True
            self.research_btn.draw(self.screen, self.font)
        elif r.status == "error":
            y = self._draw_label(SIDEBAR_X, y, "Research failed:", color=(240, 140, 140))
            y = self._draw_label(SIDEBAR_X, y, _wrap(r.error or "(unknown)", 38, max_lines=3),
                                 color=(240, 180, 180), font=self.font_sm)
            if r.log_path:
                y = self._draw_label(SIDEBAR_X, y, f"log: {r.log_path}",
                                     color=(160, 180, 200), font=self.font_sm)
            self.research_btn.rect.topleft = (SIDEBAR_X, y + 6)
            self.research_btn.label = "Try Again"
            self.research_btn.on_click = self._on_research_again
            self.research_btn.enabled = True
            self.research_btn.draw(self.screen, self.font)

    def _on_research_again(self) -> None:
        self.state.research.status = "idle"
        self.state.research.prompt = None
        self.state.research.progress = 0
        self.state.research.error = None
        self.research_btn.label = "Start Research"
        self.research_btn.on_click = self._on_start_research
        self.research_input.value = ""

    def _draw_save_load_panel(self) -> None:
        y = WINDOW_H - 58
        self._draw_label(SIDEBAR_X, y, "Save / Load", color=(160, 160, 200), font=self.font_sm)
        y += 14
        btn_w = (SIDEBAR_W - 4) // 3
        for i, btn in enumerate(self.save_buttons):
            btn.rect.topleft = (SIDEBAR_X + i * (btn_w + 2), y)
            btn.draw(self.screen, self.font_sm)
        y += 26
        for i, btn in enumerate(self.load_buttons):
            btn.rect.topleft = (SIDEBAR_X + i * (btn_w + 2), y)
            btn.enabled = save_exists(i + 1)
            btn.draw(self.screen, self.font_sm)

    def _draw_game_over_screen(self) -> None:
        result = self.state.game_over
        if result is None:
            return
        overlay = pygame.Surface((WINDOW_W, WINDOW_H))
        overlay.set_alpha(210)
        overlay.fill((10, 10, 20))
        self.screen.blit(overlay, (0, 0))
        cx = WINDOW_W // 2
        cy = WINDOW_H // 2 - 80
        if result.victory_type == "defeat":
            title = "DEFEAT"
            title_color = (220, 60, 60)
            sub = "Your civilization has fallen."
        elif result.victory_type == "domination":
            title = "VICTORY"
            title_color = (255, 220, 60)
            sub = "Domination! All enemy capitals captured."
        elif result.victory_type == "science":
            title = "VICTORY"
            title_color = (100, 220, 255)
            sub = "Science Victory! Space Colony launched."
        else:
            title = "VICTORY"
            title_color = (120, 220, 255)
            sub = "Time's up! Final score wins."
        font_title = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_title.render(title, True, title_color)
        self.screen.blit(t, t.get_rect(center=(cx, cy)))
        cy += 60
        s = self.font_big.render(sub, True, (230, 230, 230))
        self.screen.blit(s, s.get_rect(center=(cx, cy)))
        cy += 30
        score_txt = self.font_big.render(f"Score: {result.score}    Turn: {result.turn}", True, (200, 200, 200))
        self.screen.blit(score_txt, score_txt.get_rect(center=(cx, cy)))
        self.new_game_btn.rect.center = (cx, cy + 60)
        self.new_game_btn.draw(self.screen, self.font_big)

    def _draw_progress(self, x: int, y: int, current: int, total: int) -> None:
        w = SIDEBAR_W
        h = 10
        pygame.draw.rect(self.screen, (80, 80, 100), (x, y, w, h))
        frac = 0 if total <= 0 else min(1.0, current / total)
        pygame.draw.rect(self.screen, (120, 200, 120), (x, y, int(w * frac), h))
        pygame.draw.rect(self.screen, (10, 10, 10), (x, y, w, h), width=1)

    def _draw_all(self) -> None:
        self.screen.fill((20, 20, 28))
        draw_top_bar(self.screen, self.state, self.font)
        draw_map(self.screen, self.state)
        draw_city_borders(self.screen, self.state)
        draw_improvements(self.screen, self.state, self.font_sm)
        for city in self.state.cities:
            tile = self.state.tile(city.x, city.y)
            if tile is None or tile.visibility != "hidden":
                draw_city(self.screen, city, self.font_sm)
        for unit in self.state.units:
            tile = self.state.tile(unit.x, unit.y)
            if tile is None:
                continue
            if unit.owner == "player" or tile.visibility == "visible":
                draw_unit(self.screen, unit, self.reg, unit is self.selected_unit, self.font_sm)
        draw_minimap(self.screen, self.state)
        self._draw_sidebar()
        self.toasts.draw(self.screen, self.font_sm)
        if self.state.game_over is not None:
            self._draw_game_over_screen()
        if self._show_difficulty_select:
            self._draw_difficulty_select()

    # ---------- run loop ----------

    def run(self) -> None:
        # If research triggered during generation, notify caller to start subprocess.
        research_fired = False
        running = True
        while running:
            running = self._poll_events()

            r = self.state.research
            if r.status == "generating" and not research_fired and self.research_trigger and r.prompt:
                self.research_trigger(r.prompt)
                research_fired = True
            if r.status != "generating":
                research_fired = False

            if self.research_poll:
                self.research_poll()

            self._draw_all()
            pygame.display.flip()
            self.clock.tick(30)
        pygame.quit()


def _wrap(text: str, width: int, max_lines: int = 3) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:max_lines])
