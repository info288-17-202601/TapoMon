"""
pygame_ui/screens/status_screen.py
Pantalla principal del juego: muestra el estado del Tapo y acciones.
"""
from __future__ import annotations
import os
import time
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, StatBar, Panel, Toast, draw_rounded_rect
from pygame_ui.tapo_sprite import TapoSprite
from pygame_ui.constants import *
 
 
class StatusScreen(Screen):
    """
    Pantalla principal del juego.
    Muestra el Tapo, sus stats y los botones de acción.
    Integra el realtime tick mientras el usuario está conectado.
    """
    def on_enter(self) -> None:
        if self.ge.verificar_muerte(self.tapo):
            self._handle_death()
        self._refresh_bars()

    def __init__(self, manager, usuario, tapo, game_engine, local_db, sync_client):
        super().__init__(manager)
        self.usuario     = usuario
        self.tapo        = tapo
        self.ge          = game_engine
        self.local_db    = local_db
        self.sync_client = sync_client
 
        self._toast: Toast | None = None
        self._time   = 0.0
        self._last_tick_t = time.time()
        self._death_handled = False
        self._bg = None
        self._name_font = None
 
        # Sprite
        self.sprite = TapoSprite(
            cx=SCREEN_W // 2, cy=280,
            tipo=tapo.estadistica.tipo.value,
            scale=1.4
        )

        self._load_background()
        self._load_name_font()
 
        self._build_widgets()
        self._refresh_bars()
 
    # ---------------------------------------------------------------- #
    #  Construcción de widgets
    # ---------------------------------------------------------------- #
 
    def _build_widgets(self):
        # Panel izquierdo — stats de combate
        self.panel_stats = Panel(20, 60, 210, 360, "Estadísticas", C_ACCENT_DIM)
 
        # Panel derecho — vitales
        self.panel_vitals = Panel(SCREEN_W - 230, 60, 210, 360, "Vitales", C_ACCENT_DIM)
 
        # Barras de vitales (panel derecho)
        rx = SCREEN_W - 210
        self.bars = {
            "hambre":    StatBar(rx, 130, 180, label="hambre", color=C_HUNGER),
            "energia":   StatBar(rx, 185, 180, label="energia", color=C_ENERGY),
            "felicidad": StatBar(rx, 240, 180, label="felicidad", color=C_HAPPINESS),
            "salud":     StatBar(rx, 295, 180, label="salud", color=C_HEALTH),
        }
        self.bar_vida = StatBar(rx, 350, 180, label="vida", color=C_HP_HIGH)
 
        # Botones de acción — grilla 2×4
        actions = [
            ("Alimentar",      self._accion_alimentar),
            ("Jugar",          self._accion_jugar),
            ("Curar",          self._accion_curar),
            ("Fuerza",        self._accion_fuerza),
            ("Defensa",       self._accion_defensa),
            ("Velocidad",      self._accion_velocidad),
            ("Resistencia",    self._accion_resistencia),
            ("Social",         self._accion_social),
            ("Batalla P2P",   self._accion_batalla),
        ]
        self.action_btns: list[Button] = []
        self.action_cols, self.action_btn_w, self.action_btn_h = 2, 170, 28
        self.action_gap_x, self.action_gap_y = 8, 4
        self.action_rows = (len(actions) + self.action_cols - 1) // self.action_cols
        grid_h = self.action_rows * self.action_btn_h + (self.action_rows - 1) * self.action_gap_y
        base_x = SCREEN_W // 2 - (self.action_cols * self.action_btn_w + (self.action_cols - 1) * self.action_gap_x) // 2
        panel_h = grid_h + 24
        max_panel_y = SCREEN_H - panel_h - 12
        self.action_panel_y = max(0, min(432, max_panel_y))
        base_y = self.action_panel_y + 12
        for i, (label, cb) in enumerate(actions):
            col = i % self.action_cols
            row = i // self.action_cols
            x   = base_x + col * (self.action_btn_w + self.action_gap_x)
            y   = base_y + row * (self.action_btn_h + self.action_gap_y)
            self.action_btns.append(
                Button(x, y, self.action_btn_w, self.action_btn_h, text=label, callback=cb,
                       accent_color=C_ACCENT if label != "⚔️ Batalla P2P" else (220, 60, 60))
            )
 
        # Botón de Ajustes
        self.btn_settings = Button(
            SCREEN_W - 120, SCREEN_H - 44, 100, 34,
            text="⚙️ Ajustes", callback=self._open_settings,
            color=C_BG3, hover_color=C_BG2,
            text_color=C_GRAY, accent_color=C_BORDER
        )

    def _load_background(self) -> None:
        bg_path = os.path.join(os.path.dirname(__file__), "..", "sprites", "fondo.jpg")
        try:
            img = pygame.image.load(bg_path)
            self._bg = pygame.transform.smoothscale(img, (SCREEN_W, SCREEN_H)).convert()
        except Exception:
            self._bg = None

    def _load_name_font(self) -> None:
        try:
            self._name_font = pygame.font.SysFont("Comic Sans MS", 32, bold=True)
        except Exception:
            self._name_font = None
 
    # ---------------------------------------------------------------- #
    #  Actualizar barras con datos del Tapo
    # ---------------------------------------------------------------- #
 
    def _refresh_bars(self):
        v = self.tapo.vitales
        e = self.tapo.estadistica
        self.bars["hambre"].set_value(v.hambre)
        self.bars["energia"].set_value(v.energia)
        self.bars["felicidad"].set_value(v.felicidad)
        self.bars["salud"].set_value(v.salud)
        self.bar_vida.set_value(e.vida)
 
    # ---------------------------------------------------------------- #
    #  Acciones del usuario (llaman al game engine real)
    # ---------------------------------------------------------------- #
 
    def _run_action(self, fn, anim="happy"):
        msgs = fn(self.tapo)
        self.local_db.guardar_tapo(self.tapo)
        self._refresh_bars()
        self.sprite.set_state(anim)
        if msgs:
            self._show_toast(msgs[0])
        if self.ge.verificar_muerte(self.tapo):
            self._handle_death()

    def _open_settings(self):
        from pygame_ui.screens.settings_screen import SettingsScreen
        self.manager.push(SettingsScreen(
            self.manager, self.usuario, self.tapo, self.ge, self.local_db, self.sync_client
        ))
 
    def _accion_alimentar(self):  self._run_action(self.ge.alimentar)
    def _accion_jugar(self):      self._run_action(self.ge.jugar)
    def _accion_curar(self):      self._run_action(self.ge.curar)
    def _accion_fuerza(self):     self._run_action(self.ge.entrenar_fuerza, "attack")
    def _accion_defensa(self):    self._run_action(self.ge.entrenar_defensa, "attack")
    def _accion_velocidad(self):  self._run_action(self.ge.entrenar_velocidad, "attack")
    def _accion_resistencia(self):self._run_action(self.ge.entrenar_resistencia, "attack")
 
    def _accion_social(self):
        from pygame_ui.screens.social_screen import SocialScreen
        self.manager.push(
            SocialScreen(self.manager, self.usuario, self.tapo, self.sync_client, self.local_db)
        )

    def _accion_batalla(self):
        from pygame_ui.screens.battle_screen import BattleMenuScreen
        self.manager.push(BattleMenuScreen(self.manager, self.tapo))
 
    def _logout(self):
        self.tapo.estado_sistema = False
        self.local_db.guardar_tapo(self.tapo)
        self.local_db.guardar_usuario(self.usuario)
        if self.sync_client.is_connected():
            self.sync_client.upload_state(self.tapo)
        # Borrar sesión guardada: al reabrir el juego pedirá login+2FA
        self.sync_client.logout_session()
        from pygame_ui.screens.login_screen import LoginScreen
        self.manager.replace(
            LoginScreen(self.manager, self.local_db, self.sync_client,
                        self._on_relogin)
        )
 
    def _on_relogin(self, usuario, tapo):
        self.manager.replace(
            StatusScreen(self.manager, usuario, tapo,
                         self.ge, self.local_db, self.sync_client)
        )
 
    def _show_toast(self, msg: str, ok: bool = True):
        self._toast = Toast(msg, ok=ok)
 
    # ---------------------------------------------------------------- #
    #  Realtime ticks
    # ---------------------------------------------------------------- #
 
    def _check_realtime_tick(self):
        now     = time.time()
        elapsed = now - self._last_tick_t
        ticks   = int(elapsed // self.ge.REALTIME_SECONDS_PER_TICK)
        if ticks > 0:
            self.ge.aplicar_realtime_ticks(self.tapo, ticks)
            self._last_tick_t += ticks * self.ge.REALTIME_SECONDS_PER_TICK
            self._refresh_bars()
            self.local_db.guardar_tapo(self.tapo)
            if self.ge.verificar_muerte(self.tapo):
                self._handle_death()

    def _handle_death(self):
        if self._death_handled:
            return
        self._death_handled = True
        from pygame_ui.screens.death_screen import DeathScreen
        self.manager.replace(
            DeathScreen(
                self.manager,
                usuario=self.usuario,
                tapo=self.tapo,
                game_engine=self.ge,
                local_db=self.local_db,
                sync_client=self.sync_client,
            )
        )
 
    # ---------------------------------------------------------------- #
    #  Eventos, update, draw
    # ---------------------------------------------------------------- #
 
    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for btn in self.action_btns:
                btn.handle_event(event)
            self.btn_settings.handle_event(event)
 
    def update(self, dt: float):
        self._time += dt
        self.sprite.update(dt)
        self._check_realtime_tick()
 
        for bar in self.bars.values():
            bar.update(dt)
        self.bar_vida.update(dt)
 
        for btn in self.action_btns:
            btn.update(dt)
        self.btn_settings.update(dt)
 
        if self._toast:
            self._toast.update(dt)
            if not self._toast.alive:
                self._toast = None
 
    def draw(self, surf: pygame.Surface):
        fonts = self.manager.fonts
        e     = self.tapo.estadistica
        v     = self.tapo.vitales
        tipo  = e.tipo.value
        col   = TYPE_COLORS.get(tipo, C_GRAY_LIGHT)
 
        # Fondo
        if self._bg:
            surf.blit(self._bg, (0, 0))
        else:
            for i in range(20):
                c = tuple(min(255, int(col[j] * 0.15 + C_BG[j] * 0.85)) for j in range(3))
                rect = pygame.Rect(0, i * (SCREEN_H // 20), SCREEN_W, SCREEN_H // 20 + 1)
                pygame.draw.rect(surf, c, rect)
 
        # Nombre + tipo
        name_color = (40, 120, 255)
        name_font = self._name_font or fonts["title"]
        name_surf = name_font.render(self.tapo.nombre, True, name_color)
        tipo_surf = fonts["small"].render(f"[ {tipo} ]", True, col)
        surf.blit(name_surf, (SCREEN_W // 2 - name_surf.get_width() // 2, 14))
        surf.blit(tipo_surf, (SCREEN_W // 2 - tipo_surf.get_width() // 2, 50))
 
        # Panel estadísticas (izquierdo)
        self.panel_stats.draw(surf, fonts["small"])
        stats_data = [
            ("Vida",      e.vida,      C_HP_HIGH),
            ("Fuerza",    e.fuerza,    (255, 100, 80)),
            ("Defensa",   e.defensa,   (80, 160, 255)),
            ("Velocidad", e.velocidad, (80, 255, 200)),
        ]
        for i, (label, val, col_s) in enumerate(stats_data):
            y = 120 + i * 65
            lbl = fonts["small"].render(label, True, C_GRAY_LIGHT)
            val_s = fonts["label"].render(str(val), True, col_s)
            # Mini barra
            bar_rect = pygame.Rect(30, y + 22, 180, 10)
            draw_rounded_rect(surf, bar_rect, C_BG3, radius=5)
            fill_w = int(180 * min(val, 100) / 100)
            if fill_w > 0:
                draw_rounded_rect(surf, pygame.Rect(30, y + 22, fill_w, 10), col_s, radius=5)
            surf.blit(lbl, (30, y))
            surf.blit(val_s, (160, y - 2))
 
        # Estado online
        status_col = C_HP_HIGH if self.tapo.estado_sistema else C_GRAY
        status_lbl = fonts["small"].render(
            "● ACTIVO" if self.tapo.estado_sistema else "○ IDLE", True, status_col
        )
        surf.blit(status_lbl, (30, 385))
 
        sync_lbl = fonts["small"].render(
            f"Sync: {self.tapo.last_sync.strftime('%H:%M')}", True, C_GRAY
        )
        surf.blit(sync_lbl, (30, 405))
 
        # Sprite del Tapo
        self.sprite.draw(surf)
 
        # Panel vitales (derecho)
        self.panel_vitals.draw(surf, fonts["small"])
        for name, bar in self.bars.items():
            bar.draw(surf, fonts["small"])
        self.bar_vida.draw(surf, fonts["small"])
 
        # Botones de acción
        grid_h = self.action_rows * self.action_btn_h + (self.action_rows - 1) * self.action_gap_y
        actions_bg = pygame.Rect(
            SCREEN_W // 2 - 190,
            self.action_panel_y,
            380,
            grid_h + 24,
        )
        draw_rounded_rect(surf, actions_bg, C_BG2, radius=12,
                          border=1, border_color=C_BORDER)
        for btn in self.action_btns:
            btn.draw(surf, fonts["small"])
 
        self.btn_settings.draw(surf, fonts["label"])
 
        # Toast
        if self._toast:
            self._toast.draw(surf, fonts["label"])