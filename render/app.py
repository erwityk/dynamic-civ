from __future__ import annotations

from typing import Callable, Optional

import pygame

from engine.registry import Registry
from engine.state import City, GameState, Terrain, Unit
from engine.ai import run_ai_turn
from engine.turn import attack, end_turn, found_city, move_unit, reset_unit_moves
from render.draw import GRID_ORIGIN, TILE, draw_city, draw_map, draw_top_bar, draw_unit, screen_to_tile, tile_to_screen
from render.ui import Button, TextInput, Toasts

WINDOW_W = 1000
WINDOW_H = 720
SIDEBAR_X = GRID_ORIGIN[0] + 20 * TILE + 16  # right edge of map + gap
SIDEBAR_W = WINDOW_W - SIDEBAR_X - 8

ResearchTrigger = Callable[[str], None]  # invoked with the player's research prompt


class App:
    def __init__(self, state: GameState, reg: Registry, research_trigger: Optional[ResearchTrigger] = None,
                 research_poll: Optional[Callable[[], None]] = None):
        pygame.init()
        pygame.display.set_caption("Dynamic Civ")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_sm = pygame.font.SysFont("consolas", 12)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)

        self.state = state
        self.reg = reg
        self.research_trigger = research_trigger
        self.research_poll = research_poll

        self.selected_unit: Optional[Unit] = None
        self.selected_city: Optional[City] = None
        self.toasts = Toasts()
        self._city_counter = 0

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
        # Build-queue option buttons, rebuilt each frame based on registry.
        self.build_buttons: list[Button] = []

    # ---------- button callbacks ----------

    def _on_end_turn(self) -> None:
        end_turn(self.state, self.reg)
        run_ai_turn(self.state, self.reg)
        self.selected_unit = None
        self.toasts.add(f"Turn {self.state.turn}")

    def _on_found_city(self) -> None:
        if not self.selected_unit:
            return
        self._city_counter += 1
        name = f"City {self._city_counter}"
        city = found_city(self.state, self.reg, self.selected_unit, name)
        if city:
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

    def _set_build(self, city: City, target: str) -> Callable[[], None]:
        def fn() -> None:
            city.build_target = target
            self.toasts.add(f"{city.name} now building {target}")
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
                if unit_here is None and move_unit(self.state, self.selected_unit, tx, ty):
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
            return  # out of moves, not adjacent, or other precondition failed

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

    def _poll_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.end_turn_btn.handle(event):
                continue
            # Sidebar buttons only active when their panel is showing.
            if self._settler_selected() and self.found_btn.handle(event):
                continue
            if self.research_input.handle(event):
                continue
            if self.research_btn.handle(event):
                continue
            for b in self.build_buttons:
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
            y = self._draw_label(SIDEBAR_X, y, f"Atk {ut.attack}  Def {ut.defense}  Move {ut.move}")
            y = self._draw_label(SIDEBAR_X, y, f"HP {u.hp}  Moves left {u.moves_left}")
            y = self._draw_label(SIDEBAR_X, y, _wrap(ut.description, 42), color=(180, 180, 200), font=self.font_sm)
        if self._settler_selected():
            self.found_btn.rect.topleft = (SIDEBAR_X, y + 4)
            self.found_btn.draw(self.screen, self.font)
            y += 36
        return y + 6

    def _draw_city_panel(self, y: int) -> int:
        c = self.selected_city
        if c is None:
            return y
        y = self._draw_label(SIDEBAR_X, y, f"{c.name}", font=self.font_big)
        y = self._draw_label(SIDEBAR_X, y, f"Pop {c.population}  Food {c.food_stock}  Prod {c.production_stock}")
        y = self._draw_label(SIDEBAR_X, y, f"Buildings: {', '.join(c.buildings) or 'none'}", color=(180, 180, 200), font=self.font_sm)
        y = self._draw_label(SIDEBAR_X, y, f"Building: {c.build_target or 'nothing'}")
        y += 4
        y = self._draw_label(SIDEBAR_X, y, "Set production:", color=(200, 200, 220))
        self.build_buttons = []
        options = self.reg.buildable_options()
        for name in options:
            btn = Button(
                rect=pygame.Rect(SIDEBAR_X, y, SIDEBAR_W, 24),
                label=name + (" *" if c.build_target == name else ""),
                on_click=self._set_build(c, name),
            )
            btn.draw(self.screen, self.font_sm)
            self.build_buttons.append(btn)
            y += 26
        return y + 6

    def _draw_research_panel(self) -> None:
        panel_top = WINDOW_H - 160
        pygame.draw.rect(self.screen, (40, 40, 55), (SIDEBAR_X - 8, panel_top, WINDOW_W - (SIDEBAR_X - 8), 160))
        y = panel_top + 8
        y = self._draw_label(SIDEBAR_X, y, "Research", font=self.font_big)
        r = self.state.research
        # Disable button by default; visible branches re-enable it.
        self.research_btn.enabled = False
        if r.status == "idle":
            self.research_input.rect.topleft = (SIDEBAR_X, y)
            self.research_input.draw(self.screen, self.font)
            y += 32
            self.research_btn.rect.topleft = (SIDEBAR_X, y)
            self.research_btn.enabled = bool(self.research_input.value.strip())
            self.research_btn.draw(self.screen, self.font)
        elif r.status == "accumulating":
            y = self._draw_label(SIDEBAR_X, y, f"Researching: {r.prompt}", color=(220, 220, 180))
            self._draw_progress(SIDEBAR_X, y, r.progress, r.cost)
            y += 18
            y = self._draw_label(SIDEBAR_X, y, f"{r.progress}/{r.cost} science", font=self.font_sm)
        elif r.status == "generating":
            y = self._draw_label(SIDEBAR_X, y, f"Inventing: {r.prompt}", color=(220, 200, 120))
            tick = (pygame.time.get_ticks() // 300) % 4
            y = self._draw_label(SIDEBAR_X, y, "Claude is working" + "." * tick, color=(200, 200, 220))
        elif r.status == "done":
            y = self._draw_label(SIDEBAR_X, y, f"Discovered: {r.last_result_name}", color=(180, 240, 180))
            y = self._draw_label(SIDEBAR_X, y, "(now buildable in cities)", color=(160, 200, 160), font=self.font_sm)
            self.research_btn.rect.topleft = (SIDEBAR_X, y + 6)
            self.research_btn.label = "Research Again"
            self.research_btn.on_click = self._on_research_again
            self.research_btn.enabled = True
            self.research_btn.draw(self.screen, self.font)
        elif r.status == "error":
            y = self._draw_label(SIDEBAR_X, y, "Research failed:", color=(240, 140, 140))
            y = self._draw_label(SIDEBAR_X, y, _wrap(r.error or "(unknown)", 38, max_lines=4),
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
        for city in self.state.cities:
            draw_city(self.screen, city, self.font_sm)
        for unit in self.state.units:
            draw_unit(self.screen, unit, self.reg, unit is self.selected_unit, self.font_sm)
        self._draw_sidebar()
        self.toasts.draw(self.screen, self.font_sm)

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
