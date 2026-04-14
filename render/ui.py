from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import pygame


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    on_click: Callable[[], None]
    enabled: bool = True

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        bg = (70, 90, 130) if self.enabled else (50, 50, 50)
        fg = (240, 240, 240) if self.enabled else (140, 140, 140)
        pygame.draw.rect(surf, bg, self.rect, border_radius=4)
        pygame.draw.rect(surf, (20, 20, 20), self.rect, width=1, border_radius=4)
        text = font.render(self.label, True, fg)
        surf.blit(text, text.get_rect(center=self.rect.center))


@dataclass
class TextInput:
    rect: pygame.Rect
    value: str = ""
    placeholder: str = ""
    active: bool = False
    max_len: int = 120
    on_submit: Optional[Callable[[str], None]] = None

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
            return self.active
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.on_submit:
                    self.on_submit(self.value)
                return True
            ch = event.unicode
            if ch and ch.isprintable() and len(self.value) < self.max_len:
                self.value += ch
                return True
        return False

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        bg = (245, 245, 245) if self.active else (220, 220, 220)
        pygame.draw.rect(surf, bg, self.rect, border_radius=3)
        border_color = (60, 120, 200) if self.active else (100, 100, 100)
        pygame.draw.rect(surf, border_color, self.rect, width=1, border_radius=3)
        display = self.value if self.value else self.placeholder
        color = (20, 20, 20) if self.value else (120, 120, 120)
        text = font.render(display, True, color)
        surf.blit(text, (self.rect.x + 6, self.rect.y + (self.rect.h - text.get_height()) // 2))


@dataclass
class Toast:
    message: str
    ttl_ms: int
    born_ms: int
    color: tuple[int, int, int] = (60, 60, 70)


@dataclass
class Toasts:
    items: list[Toast] = field(default_factory=list)

    def add(self, msg: str, color: tuple[int, int, int] = (60, 60, 70), ttl_ms: int = 4000) -> None:
        self.items.append(Toast(message=msg, ttl_ms=ttl_ms, born_ms=pygame.time.get_ticks(), color=color))

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        now = pygame.time.get_ticks()
        self.items = [t for t in self.items if now - t.born_ms < t.ttl_ms]
        for i, t in enumerate(self.items[-4:]):
            txt = font.render(t.message, True, (240, 240, 240))
            pad = 8
            w = txt.get_width() + pad * 2
            h = txt.get_height() + pad
            rect = pygame.Rect(surf.get_width() - w - 12, 12 + i * (h + 6), w, h)
            pygame.draw.rect(surf, t.color, rect, border_radius=4)
            surf.blit(txt, (rect.x + pad, rect.y + pad // 2))
