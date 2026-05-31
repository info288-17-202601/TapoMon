"""
pygame_ui/screens/death_screen.py
Pantalla de muerte del Tapo y salto a creacion de nueva mascota.
"""
from __future__ import annotations
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, Toast, draw_rounded_rect
from pygame_ui.constants import *


class DeathScreen(Screen):
    """Muestra mensaje de muerte y permite continuar a creacion."""

    def __init__(self, manager, usuario, tapo, game_engine, local_db, sync_client):
        super().__init__(manager)
        self.usuario = usuario
        self.tapo = tapo
        self.ge = game_engine
        self.local_db = local_db
        self.sync_client = sync_client
        self._toast: Toast | None = None
        self._continuing = False

        self.btn_continue = Button(
            SCREEN_W // 2 - 120, SCREEN_H // 2 + 40, 240, BTN_H,
            text="Continuar", callback=self._go_next,
            accent_color=C_ACCENT,
        )

    def on_enter(self) -> None:
        self.tapo.estado_sistema = False
        self.local_db.guardar_tapo(self.tapo)
        if self.sync_client.is_connected():
            self.sync_client.upload_state(self.tapo)

    def _go_next(self):
        if self._continuing:
            return
        self._continuing = True
        from pygame_ui.screens.new_tapo_screen import NewTapoScreen
        self.manager.replace(
            NewTapoScreen(
                self.manager,
                usuario=self.usuario,
                game_engine=self.ge,
                local_db=self.local_db,
                sync_client=self.sync_client,
            )
        )

    def _show_toast(self, msg: str, ok: bool = True):
        self._toast = Toast(msg, ok=ok)

    def handle_event(self, event: pygame.event.Event):
        self.btn_continue.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._go_next()
        if event.type == pygame.KEYDOWN:
            self._go_next()

    def update(self, dt: float):
        self.btn_continue.update(dt)
        if self._toast:
            self._toast.update(dt)
            if not self._toast.alive:
                self._toast = None

    def draw(self, surf: pygame.Surface):
        fonts = self.manager.fonts
        surf.fill(C_BG)

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((15, 10, 20, 180))
        surf.blit(overlay, (0, 0))

        panel = pygame.Rect(SCREEN_W // 2 - 220, SCREEN_H // 2 - 140, 440, 240)
        draw_rounded_rect(surf, panel, C_BG2, radius=14, border=1, border_color=C_BORDER)

        title = fonts["title"].render("Tu Tapo murio", True, C_HP_LOW)
        hint = fonts["label"].render("Haz click para continuar", True, C_GRAY_LIGHT)
        sub = fonts["small"].render("y crear un nuevo Tapo", True, C_GRAY)

        surf.blit(title, (SCREEN_W // 2 - title.get_width() // 2, panel.y + 30))
        surf.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, panel.y + 80))
        surf.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, panel.y + 105))

        self.btn_continue.draw(surf, fonts["label"])

        if self._toast:
            self._toast.draw(surf, fonts["label"])
