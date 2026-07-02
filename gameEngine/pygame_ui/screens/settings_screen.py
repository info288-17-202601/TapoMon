"""
pygame_ui/screens/settings_screen.py
Pantalla de ajustes del juego. Permite cambiar el servidor regional y cerrar sesión.
"""
from __future__ import annotations
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, Panel, Toast, draw_rounded_rect
from pygame_ui.constants import *

class SettingsScreen(Screen):
    def __init__(self, manager, usuario, tapo, game_engine, local_db, sync_client):
        super().__init__(manager)
        self.usuario = usuario
        self.tapo = tapo
        self.ge = game_engine
        self.local_db = local_db
        self.sync_client = sync_client

        self._toast: Toast | None = None
        self._time = 0.0

        self._build_widgets()

    def _build_widgets(self):
        cx = SCREEN_W // 2
        
        # Panel central
        self.panel_x, self.panel_w = cx - 200, 400
        self.panel_y, self.panel_h = 100, 400

        self.btn_back = Button(
            self.panel_x + 20, self.panel_y + 20, 80, 30,
            text="Volver", callback=lambda: self.manager.pop(),
            color=C_BG3, hover_color=C_BG2, text_color=C_GRAY
        )

        # Botón cerrar sesión
        self.btn_logout = Button(
            cx - 100, self.panel_y + 320, 200, 40,
            text="🚪 Salir del juego", callback=self._logout,
            accent_color=(220, 60, 60)
        )

        # Botones de migración
        self._regiones = ["norte", "sur", "centro"]
        self.migr_btns = []
        reg_w = (self.panel_w - 60) // 3
        for i, r in enumerate(self._regiones):
            x = self.panel_x + 30 + i * (reg_w + 10)
            self.migr_btns.append(
                Button(x, self.panel_y + 220, reg_w, 40,
                       text=r.capitalize(),
                       callback=lambda rr=r: self._migrar(rr),
                       accent_color=C_ACCENT)
            )

    def _logout(self):
        self.tapo.estado_sistema = False
        self.local_db.guardar_tapo(self.tapo)
        self.local_db.guardar_usuario(self.usuario)
        if self.sync_client.is_connected():
            self.sync_client.upload_state(self.tapo)
        from pygame_ui.screens.login_screen import LoginScreen
        
        # Necesitamos la funcion _on_relogin de status_screen
        # Una forma facil es simplemente buscar si alguien la necesita o usar la misma definicion
        def on_relogin(usuario, tapo):
            from pygame_ui.screens.status_screen import StatusScreen
            self.manager._stack.clear()
            self.manager.push(
                StatusScreen(self.manager, usuario, tapo,
                             self.ge, self.local_db, self.sync_client)
            )

        self.manager._stack.clear()
        self.manager.push(
            LoginScreen(self.manager, self.local_db, self.sync_client, on_relogin)
        )

    def _migrar(self, region: str):
        if self.sync_client.server_region == region:
            self._show_toast("Ya estás en este servidor.", ok=False)
            return
            
        self._show_toast(f"Migrando a {region}...", ok=True)
        res = self.sync_client.migrar_servidor(region)
        if res and res.get("success"):
            self._show_toast(f"Migrado exitosamente a {region}", ok=True)
        else:
            msg = res.get("detail", "Error en la migración") if res else "Coordinador no disponible"
            self._show_toast(msg, ok=False)

    def _show_toast(self, msg: str, ok: bool = True):
        self._toast = Toast(msg, ok=ok)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.btn_back.handle_event(event)
            self.btn_logout.handle_event(event)
            for btn in self.migr_btns:
                btn.handle_event(event)

    def update(self, dt: float):
        self._time += dt
        self.btn_back.update(dt)
        self.btn_logout.update(dt)
        for btn in self.migr_btns:
            btn.update(dt)

        if self._toast:
            self._toast.update(dt)
            if not self._toast.alive:
                self._toast = None

    def draw(self, surf: pygame.Surface):
        # Dibujamos una pequeña capa semitransparente sobre la pantalla de status que está debajo
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surf.blit(overlay, (0, 0))

        fonts = self.manager.fonts
        
        # Panel principal
        draw_rounded_rect(surf, pygame.Rect(self.panel_x, self.panel_y, self.panel_w, self.panel_h), C_BG2, radius=14, border=1, border_color=C_BORDER)

        self.btn_back.draw(surf, fonts["small"])

        # Título
        cx = SCREEN_W // 2
        title = fonts["title"].render("Ajustes", True, C_ACCENT)
        surf.blit(title, (cx - title.get_width() // 2, self.panel_y + 30))

        # Sección de Migración
        migr_title = fonts["label"].render("Cambiar de Servidor Regional", True, C_WHITE)
        surf.blit(migr_title, (cx - migr_title.get_width() // 2, self.panel_y + 110))

        desc = fonts["small"].render("Puedes migrar tu mascota una vez cada 24 horas.", True, C_GRAY)
        surf.blit(desc, (cx - desc.get_width() // 2, self.panel_y + 140))

        curr_server = self.sync_client.server_region or "Desconocido"
        curr_lbl = fonts["small"].render(f"Servidor actual: {curr_server.capitalize()}", True, (100, 255, 100))
        surf.blit(curr_lbl, (cx - curr_lbl.get_width() // 2, self.panel_y + 175))

        for btn in self.migr_btns:
            btn.draw(surf, fonts["small"])

        self.btn_logout.draw(surf, fonts["label"])

        if self._toast:
            self._toast.draw(surf, fonts["label"])
