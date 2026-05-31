"""
pygame_ui/screens/new_tapo_screen.py
Pantalla de creacion de un nuevo Tapo tras la muerte.
"""
from __future__ import annotations
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, TextField, Toast, draw_rounded_rect
from pygame_ui.constants import *


class NewTapoScreen(Screen):
    """Formulario para crear un nuevo Tapo."""

    def __init__(self, manager, usuario, game_engine, local_db, sync_client):
        super().__init__(manager)
        self.usuario = usuario
        self.ge = game_engine
        self.local_db = local_db
        self.sync_client = sync_client

        self._toast: Toast | None = None
        self._tipos = ["Fuego", "Agua", "Planta", "Luz", "Oscuridad", "Normal"]
        self._tipo_sel = "Normal"
        self._tipo_btns = []

        self._build_widgets()

    def _build_widgets(self):
        cx = SCREEN_W // 2
        panel_x = cx - 200
        panel_w = 400

        self.tf_name = TextField(panel_x, 280, panel_w, 44, placeholder="Nombre de tu nuevo Tapo")

        tipo_w = panel_w // len(self._tipos) - 4
        for i, t in enumerate(self._tipos):
            x = panel_x + i * (tipo_w + 4)
            self._tipo_btns.append(
                Button(x, 340, tipo_w, 30, text=t[:3],
                       callback=lambda tt=t: setattr(self, "_tipo_sel", tt),
                       accent_color=TYPE_COLORS.get(t, C_ACCENT))
            )

        self.btn_create = Button(
            panel_x, 400, panel_w, BTN_H,
            text="Crear Tapo",
            callback=self._do_create,
            accent_color=C_ACCENT,
        )

    def _show_toast(self, msg: str, ok: bool = True):
        self._toast = Toast(msg, ok=ok)

    def _do_create(self):
        nombre = self.tf_name.text.strip()
        if not nombre:
            self._show_toast("Ingresa un nombre", ok=False)
            return
        try:
            from models.tapo import TipoTapo
            try:
                tipo_enum = TipoTapo(self._tipo_sel)
            except ValueError:
                tipo_enum = TipoTapo.NORMAL

            tapo = self.local_db.registrar_nueva_mascota(self.usuario, nombre, tipo_enum)
            tapo.estado_sistema = True
            self.local_db.guardar_tapo(tapo)
            if self.sync_client.is_connected():
                self.sync_client.upload_state(tapo)

            from pygame_ui.screens.status_screen import StatusScreen
            self.manager.replace(
                StatusScreen(
                    self.manager,
                    usuario=self.usuario,
                    tapo=tapo,
                    game_engine=self.ge,
                    local_db=self.local_db,
                    sync_client=self.sync_client,
                )
            )
        except Exception as e:
            self._show_toast(f"Error: {e}", ok=False)

    def handle_event(self, event: pygame.event.Event):
        for w in [self.tf_name, self.btn_create]:
            w.handle_event(event)
        for b in self._tipo_btns:
            b.handle_event(event)

    def update(self, dt: float):
        for w in [self.tf_name, self.btn_create]:
            w.update(dt)
        for b in self._tipo_btns:
            b.update(dt)
        if self._toast:
            self._toast.update(dt)
            if not self._toast.alive:
                self._toast = None

    def draw(self, surf: pygame.Surface):
        fonts = self.manager.fonts
        surf.fill(C_BG)

        panel = pygame.Rect(SCREEN_W // 2 - 220, 220, 440, 240)
        draw_rounded_rect(surf, panel, C_BG2, radius=14, border=1, border_color=C_BORDER)

        title = fonts["title"].render("Crea tu nuevo Tapo", True, C_ACCENT)
        surf.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 160))

        subtitle = fonts["small"].render("Elige nombre y tipo", True, C_GRAY_LIGHT)
        surf.blit(subtitle, (SCREEN_W // 2 - subtitle.get_width() // 2, 200))

        for b in self._tipo_btns:
            b.draw(surf, fonts["small"])

        self.tf_name.draw(surf, fonts["label"])
        self.btn_create.draw(surf, fonts["label"])

        if self._toast:
            self._toast.draw(surf, fonts["label"])
