"""
pygame_ui/screens/battle_screen.py
Pantalla de combate P2P — host y challenger.
Corre el servidor/cliente en hilos separados y recibe
eventos de combate via pygame.event.post().
"""
from __future__ import annotations
import threading
import queue
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, TextField, Panel, Toast, draw_rounded_rect, draw_glowing_rect
from pygame_ui.tapo_sprite import TapoSprite
from pygame_ui.constants import *

# Evento pygame custom para recibir logs del combate P2P
COMBAT_LOG_EVENT = pygame.USEREVENT + 1
COMBAT_END_EVENT = pygame.USEREVENT + 2


# ──────────────────────────────────────────────────────────────────── #
#  Menú de batalla
# ──────────────────────────────────────────────────────────────────── #

class BattleMenuScreen(Screen):
    """Menú previo: elige HOST o CHALLENGER."""

    def __init__(self, manager, tapo):
        super().__init__(manager)
        self.tapo = tapo
        self._time = 0.0

        cx = SCREEN_W // 2
        self.btn_host = Button(
            cx - 180, 290, 160, 60,
            text="Ser HOST",
            callback=self._go_host,
            accent_color=(255, 140, 40)
        )
        self.btn_join = Button(
            cx + 20, 290, 160, 60,
            text="Unirse",
            callback=self._go_join,
            accent_color=C_ACCENT
        )
        self.btn_back = Button(
            cx - 80, 455, 160, 40,
            text="Volver",
            callback=self.manager.pop,
            color=C_BG3, hover_color=C_BG2,
            text_color=C_GRAY, accent_color=C_BORDER
        )
        self.tf_ip = TextField(cx - 140, 392, 280, 44, placeholder="IP:PORT (ej: 127.0.0.1:55201)")

    def _go_host(self):
        self.manager.replace(BattleScreen(self.manager, self.tapo, mode="host", ip=""))

    def _go_join(self):
        ip_port = self.tf_ip.text.strip()
        if not ip_port:
            return

        from p2pEngine.p2p_server import DEFAULT_PORT
        if ":" in ip_port:
            ip_host, port_str = ip_port.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                return
        else:
            ip_host = ip_port
            port = DEFAULT_PORT

        self.manager.replace(BattleScreen(self.manager, self.tapo, mode="client", ip=ip_host, port=port))

    def handle_event(self, event):
        self.btn_host.handle_event(event)
        self.btn_join.handle_event(event)
        self.btn_back.handle_event(event)
        self.tf_ip.handle_event(event)

    def update(self, dt):
        self._time += dt
        for w in [self.btn_host, self.btn_join, self.btn_back, self.tf_ip]:
            w.update(dt)

    def draw(self, surf):
        fonts = self.manager.fonts
        cx    = SCREEN_W // 2

        surf.fill(C_BG)
        # Título
        t = fonts["title"].render("Combate P2P", True, (220, 60, 60))
        surf.blit(t, (cx - t.get_width() // 2, 120))

        # Info del Tapo
        e = self.tapo.estadistica
        tipo_col = TYPE_COLORS.get(e.tipo.value, C_GRAY_LIGHT)
        info = fonts["label"].render(
            f"{self.tapo.nombre}  [{e.tipo.value}]  HP:{e.vida}  ATK:{e.fuerza}  DEF:{e.defensa}",
            True, tipo_col
        )
        surf.blit(info, (cx - info.get_width() // 2, 200))

        # Widgets
        self.btn_host.draw(surf, fonts["label"])
        self.btn_join.draw(surf, fonts["label"])
        self.btn_back.draw(surf, fonts["small"])

        # Label + campo IP
        lbl = fonts["small"].render("IP del host para unirte:", True, C_GRAY_LIGHT)
        surf.blit(lbl, (cx - 140, 368))
        self.tf_ip.draw(surf, fonts["label"])


# ──────────────────────────────────────────────────────────────────── #
#  Pantalla activa de batalla
# ──────────────────────────────────────────────────────────────────── #

class BattleScreen(Screen):
    """
    Pantalla de combate activo.
    Corre ServidorCombate o ClienteCombate en un hilo,
    muestra logs en tiempo real y anima sprites.
    """

    MAX_LOG = 18

    def __init__(self, manager, tapo, mode: str, ip: str, port: int = 55201):
        super().__init__(manager)
        self.tapo   = tapo
        self.mode   = mode     # "host" | "client"
        self.ip     = ip
        self.port   = port
        self._log_lines: list[tuple[str, tuple]] = []  # (texto, color)
        self._status   = "connecting"   # connecting | fighting | ended
        self._winner   = ""
        self._time     = 0.0

        # Sprites (el rival se crea cuando se conecta)
        self.sprite_local = TapoSprite(180, 300, tapo.estadistica.tipo.value, scale=1.2)
        self.sprite_rival: TapoSprite | None = None

        # HP para mostrar
        self.hp_local = tapo.estadistica.vida
        self.hp_rival = 0
        self.hp_max_local = tapo.estadistica.vida
        self.hp_max_rival = 1

        self.btn_surrender = Button(
            SCREEN_W // 2 - 80, SCREEN_H - 54, 160, 40,
            text="Rendirse",
            callback=self._surrender,
            accent_color=(200, 60, 60)
        )
        self.btn_back = Button(
            SCREEN_W - 130, SCREEN_H - 54, 110, 40,
            text="Volver",
            callback=self._go_back,
            color=C_BG3, hover_color=C_BG2,
            text_color=C_GRAY, accent_color=C_BORDER
        )

        self._combat_obj = None
        self._thread: threading.Thread | None = None
        self._start_combat()

    # ---------------------------------------------------------------- #
    #  Arrancar combate en hilo
    # ---------------------------------------------------------------- #

    def _log_cb(self, msg: str):
        """Callback llamado desde el hilo de combate."""
        color = C_WHITE
        if "GOLPE" in msg:
            color = C_HP_LOW
        elif "Fallo" in msg:
            color = C_GRAY
        elif "Ganador" in msg:
            color = (255, 200, 50)
        elif "HP" in msg:
            color = C_HP_HIGH

        pygame.event.post(pygame.event.Event(COMBAT_LOG_EVENT, {"msg": msg, "color": color}))

        # Detectar rival
        if "presenta a:" in msg:
            parts = msg.split("presenta a:", 1)
            if len(parts) > 1:
                rest = parts[1].strip()
                nombre = rest.split("(")[0].strip()
                tipo = None
                if "(" in rest and ")" in rest:
                    tipo = rest.split("(", 1)[1].split(")", 1)[0].strip()
                payload = f"{nombre}|{tipo}" if tipo else nombre
                pygame.event.post(pygame.event.Event(COMBAT_LOG_EVENT, {
                    "msg": f"__rival_info__{payload}", "color": C_WHITE
                }))

        # Detectar fin
        if "Ganador:" in msg:
            pygame.event.post(pygame.event.Event(COMBAT_END_EVENT, {"msg": msg}))

        # Detectar HP
        if "HP" in msg and "|" in msg:
            pygame.event.post(pygame.event.Event(COMBAT_LOG_EVENT, {
                "msg": f"__hp_update__", "color": C_WHITE
            }))

    def _start_combat(self):
        try:
            if self.mode == "host":
                import socket
                import os
                from p2pEngine.p2p_server import DEFAULT_PORT
                
                advertised_ip = (
                    os.getenv("P2P_HOST_IP")
                    or socket.gethostbyname(socket.gethostname())
                )
                advertised_port = int(os.getenv("P2P_HOST_PORT", str(DEFAULT_PORT)))

                from p2pEngine.p2p_server import ServidorCombate
                self._combat_obj = ServidorCombate(self.tapo, callback_log=self._log_cb)
                self._thread = threading.Thread(
                    target=self._combat_obj.iniciar, daemon=True
                )
                self._thread.start()
                self._add_log(f"Host IP:PUERTO -> {advertised_ip}:{advertised_port}", C_ACCENT)
                self._add_log("Esperando challenger...", C_ACCENT)
            else:
                from p2pEngine.p2p_client import ClienteCombate
                self._combat_obj = ClienteCombate(
                    self.tapo, host_ip=self.ip, port=self.port, callback_log=self._log_cb
                )
                self._thread = threading.Thread(
                    target=self._combat_obj.conectar, daemon=True
                )
                self._thread.start()
                self._add_log(f"Conectando a {self.ip}:{self.port}...", C_ACCENT)
        except Exception as e:
            self._add_log(f"Error: {e}", C_HP_LOW)

    def _add_log(self, msg: str, color=C_WHITE):
        self._log_lines.append((msg, color))
        if len(self._log_lines) > self.MAX_LOG:
            self._log_lines.pop(0)

    def _surrender(self):
        if self._combat_obj and hasattr(self._combat_obj, "rendirse"):
            self._combat_obj.rendirse()
        self._go_back()

    def _go_back(self):
        self.manager.pop()

    def _ensure_rival_sprite(self, tipo: str | None, hp_max: int | None = None) -> None:
        if self.sprite_rival is None:
            self.sprite_rival = TapoSprite(
                SCREEN_W - 180, 300, tipo or "Normal", scale=1.2
            )
        if hp_max is not None:
            self.hp_max_rival = max(1, hp_max)
            if self.hp_rival <= 0:
                self.hp_rival = self.hp_max_rival

    # ---------------------------------------------------------------- #
    #  Eventos
    # ---------------------------------------------------------------- #

    def handle_event(self, event: pygame.event.Event):
        if self._status == "ended":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._go_back()
            return

        self.btn_surrender.handle_event(event)
        self.btn_back.handle_event(event)

        if event.type == COMBAT_LOG_EVENT:
            msg   = event.msg
            color = event.color

            if msg.startswith("__rival_info__"):
                data = msg[len("__rival_info__"):]
                nombre = data
                tipo = None
                if "|" in data:
                    nombre, tipo = data.split("|", 1)
                    nombre = nombre.strip()
                    tipo = tipo.strip() or None

                hp_max = None
                if self._combat_obj and hasattr(self._combat_obj, "estado") and self._combat_obj.estado:
                    rival = self._combat_obj.estado.tapo_rival
                    tipo = rival.estadistica.tipo.value
                    hp_max = rival.estadistica.vida

                self._ensure_rival_sprite(tipo, hp_max)
            elif msg == "__hp_update__":
                if self._combat_obj and hasattr(self._combat_obj, "estado") and self._combat_obj.estado:
                    est = self._combat_obj.estado
                    if self.sprite_rival is None:
                        self._ensure_rival_sprite(est.tapo_rival.estadistica.tipo.value, est.tapo_rival.estadistica.vida)
                    self.hp_local = est.hp_local
                    self.hp_rival = est.hp_rival
                    if self.hp_rival < self.hp_max_rival * 0.3:
                        self.sprite_rival and self.sprite_rival.set_state("hurt")
                    if self.hp_local < self.hp_max_local * 0.3:
                        self.sprite_local.set_state("hurt")
            else:
                self._add_log(msg, color)
                # Animar según evento
                if "GOLPE" in msg or "💥" in msg:
                    self.sprite_local.set_state("attack")
                    self.sprite_rival and self.sprite_rival.set_state("hurt")
                if self._status == "connecting" and ("iniciado" in msg.lower() or "combate" in msg.lower()):
                    self._status = "fighting"

        elif event.type == COMBAT_END_EVENT:
            self._status = "ended"
            self._winner = event.msg
            self.sprite_local.set_state("dead" if "rival" in event.msg else "happy")

    # ---------------------------------------------------------------- #
    #  Update
    # ---------------------------------------------------------------- #

    def update(self, dt: float):
        self._time += dt
        self.sprite_local.update(dt)
        if self.sprite_rival:
            self.sprite_rival.update(dt)
        self.btn_surrender.update(dt)
        self.btn_back.update(dt)

    # ---------------------------------------------------------------- #
    #  Draw
    # ---------------------------------------------------------------- #

    def draw(self, surf: pygame.Surface):
        fonts = self.manager.fonts
        surf.fill(C_BG)

        # Título
        mode_str = "HOST" if self.mode == "host" else "CHALLENGER"
        t = fonts["label"].render(f"Combate P2P  —  {mode_str}", True, (220, 80, 80))
        surf.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 12))

        # Zona de sprites
        battle_rect = pygame.Rect(0, 50, SCREEN_W, 320)
        draw_rounded_rect(surf, battle_rect, C_BG2, radius=0)

        # Sprite local (izquierda)
        self.sprite_local.draw(surf)
        # Sprite rival (derecha)
        if self.sprite_rival:
            self.sprite_rival.draw(surf)
        else:
            # Placeholder "Esperando..."
            wait = fonts["small"].render("Esperando rival...", True, C_GRAY)
            surf.blit(wait, (SCREEN_W - 180 - wait.get_width() // 2, 290))

        # HP bars (abajo de los sprites)
        self._draw_hp_bar(surf, 30, 340, 200, self.hp_local, self.hp_max_local,
                          self.tapo.nombre, fonts)
        if self.sprite_rival:
            self._draw_hp_bar(surf, SCREEN_W - 230, 340, 200, self.hp_rival, self.hp_max_rival,
                              "Rival", fonts)

        # VS
        vs = fonts["title"].render("VS", True, (180, 50, 50))
        surf.blit(vs, (SCREEN_W // 2 - vs.get_width() // 2, 200))

        # Panel de log
        log_rect = pygame.Rect(20, 375, SCREEN_W - 40, 185)
        draw_rounded_rect(surf, log_rect, C_BG3, radius=8, border=1, border_color=C_BORDER)

        # Log lines
        for i, (line, col) in enumerate(self._log_lines[-12:]):
            lsurf = fonts["small"].render(line[:90], True, col)
            surf.blit(lsurf, (30, 382 + i * 14))

        # Estado
        status_map = {
            "connecting": ("Conectando...",  C_GRAY),
            "fighting":   ("En combate",     C_HP_HIGH),
            "ended":      ("Fin",            (255, 200, 50)),
        }
        st_txt, st_col = status_map.get(self._status, ("", C_GRAY))
        st_surf = fonts["small"].render(st_txt, True, st_col)
        surf.blit(st_surf, (SCREEN_W // 2 - st_surf.get_width() // 2, SCREEN_H - 80))

        # Botones
        self.btn_surrender.draw(surf, fonts["small"])
        self.btn_back.draw(surf, fonts["small"])

        # Ganador overlay
        if self._status == "ended":
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            surf.blit(overlay, (0, 0))
            txt = fonts["title"].render(f"{self._winner}", True, (255, 200, 50))
            surf.blit(txt, (SCREEN_W // 2 - txt.get_width() // 2, SCREEN_H // 2 - 40))
            hint = fonts["small"].render("Click para continuar", True, C_GRAY_LIGHT)
            surf.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H // 2 + 10))

    def _draw_hp_bar(self, surf, x, y, w, hp, hp_max, name, fonts):
        ratio = max(0.0, hp / max(1, hp_max))
        col   = C_HP_HIGH if ratio > 0.5 else (C_HP_MID if ratio > 0.25 else C_HP_LOW)
        bg    = pygame.Rect(x, y, w, 16)
        fg    = pygame.Rect(x, y, int(w * ratio), 16)
        draw_rounded_rect(surf, bg, C_BG3, radius=8)
        if fg.width > 0:
            draw_rounded_rect(surf, fg, col, radius=8)
        lbl = fonts["small"].render(f"{name}  {hp}/{hp_max}", True, C_GRAY_LIGHT)
        surf.blit(lbl, (x, y - 18))