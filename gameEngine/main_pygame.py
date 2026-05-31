"""
main_pygame.py
Punto de entrada de TapoMon con interfaz Pygame.
Reemplaza main.py (consola) con un game loop basado en eventos.

Uso:
    python main_pygame.py

Requisitos:
    pip install pygame pymongo python-dotenv
"""
from __future__ import annotations
import sys
import os

# Asegurar que los módulos del proyecto sean importables
sys.path.insert(0, os.path.dirname(__file__))

import pygame

from pygame_ui.constants import (
    SCREEN_W, SCREEN_H, FPS, C_BG,
    FONT_TITLE, FONT_LABEL, FONT_SMALL, FONT_MONO,
)
import pygame_ui.constants as const

from pygame_ui.screen_manager import ScreenManager


# ──────────────────────────────────────────────────────────────────── #
#  Clase principal de la aplicación
# ──────────────────────────────────────────────────────────────────── #

class App:
    """
    Orquesta el ciclo de vida de la aplicación:
      1. Inicializa Pygame y carga fuentes.
      2. Instancia el ScreenManager y las dependencias (DB, engine, sync).
      3. Corre el game loop: events → update → draw.
    """

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("TapoMon")

        # Intentar icono (ignorar si no existe)
        try:
            icon = pygame.image.load(os.path.join("assets", "icon.png"))
            pygame.display.set_icon(icon)
        except Exception:
            pass

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock  = pygame.time.Clock()

        self._load_fonts()
        self._init_backend()
        self._init_screens()

    # ---------------------------------------------------------------- #
    #  Fuentes
    # ---------------------------------------------------------------- #

    def _load_fonts(self):
        """
        Intenta cargar una fuente del sistema. Si no está disponible,
        usa la fuente por defecto de Pygame.
        Prioridad: fuente del sistema → fallback default.
        """
        candidates_title = ["Orbitron", "Exo 2", "Rajdhani", "Share Tech Mono",
                            "Cousine", "Ubuntu Mono", "monospace"]
        candidates_body  = ["Exo 2", "Rajdhani", "Ubuntu", "Verdana", "Arial"]

        def load(names: list[str], size: int, bold: bool = False) -> pygame.font.Font:
            for name in names:
                try:
                    path = pygame.font.match_font(name, bold=bold)
                    if path:
                        return pygame.font.Font(path, size)
                except Exception:
                    pass
            return pygame.font.SysFont("monospace", size, bold=bold)

        self.fonts = {
            "title": load(candidates_title, 30, bold=True),
            "label": load(candidates_body,  18),
            "small": load(candidates_body,  13),
            "mono":  pygame.font.SysFont("monospace", 13),
        }

        # Compartir con constantes para que los widgets puedan acceder
        const.FONT_TITLE = self.fonts["title"]
        const.FONT_LABEL = self.fonts["label"]
        const.FONT_SMALL = self.fonts["small"]
        const.FONT_MONO  = self.fonts["mono"]

    # ---------------------------------------------------------------- #
    #  Backend
    # ---------------------------------------------------------------- #

    def _init_backend(self):
        """Inicializa DB y motor de juego. Muestra loading en pantalla."""
        self.screen.fill(C_BG)
        msg = pygame.font.SysFont("monospace", 16).render(
            "Conectando a la base de datos...", True, (80, 140, 255)
        )
        self.screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2))
        pygame.display.flip()

        try:
            import db.local_db as local_db
            self.local_db = local_db
        except Exception as e:
            self._fatal(f"Error al conectar con MongoDB:\n{e}\n\nVerifica que MongoDB esté corriendo.")

        import engine.game_engine as game_engine
        self.game_engine = game_engine

        from network.sync_client import SyncClient
        self.sync_client = SyncClient()

    # ---------------------------------------------------------------- #
    #  Pantallas
    # ---------------------------------------------------------------- #

    def _init_screens(self):
        self.manager = ScreenManager()
        self.manager.fonts = self.fonts  # disponibles para todas las pantallas

        from pygame_ui.screens.login_screen import LoginScreen

        login = LoginScreen(
            self.manager,
            local_db    = self.local_db,
            sync_client = self.sync_client,
            on_success  = self._on_login_success,
        )
        self.manager.push(login)

    def _on_login_success(self, usuario, tapo):
        """Callback al autenticarse: aplica idle y entra al juego."""
        # Aplicar degradación IDLE (tiempo desconectado)
        self.game_engine.aplicar_idle(tapo)

        if self.game_engine.verificar_muerte(tapo):
            from pygame_ui.screens.death_screen import DeathScreen
            self.manager.replace(
                DeathScreen(
                    self.manager,
                    usuario=usuario,
                    tapo=tapo,
                    game_engine=self.game_engine,
                    local_db=self.local_db,
                    sync_client=self.sync_client,
                )
            )
            return

        tapo.estado_sistema = True
        self.local_db.guardar_tapo(tapo)

        from pygame_ui.screens.status_screen import StatusScreen
        self.manager.replace(
            StatusScreen(
                self.manager,
                usuario      = usuario,
                tapo         = tapo,
                game_engine  = self.game_engine,
                local_db     = self.local_db,
                sync_client  = self.sync_client,
            )
        )

    # ---------------------------------------------------------------- #
    #  Game loop
    # ---------------------------------------------------------------- #

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0   # segundos desde el último frame
            dt = min(dt, 0.1)                      # evitar dt gigante al pausar

            # ── Eventos ──────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    # Toggle fullscreen
                    flags = self.screen.get_flags()
                    if flags & pygame.FULLSCREEN:
                        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                    else:
                        self.screen = pygame.display.set_mode(
                            (SCREEN_W, SCREEN_H), pygame.FULLSCREEN
                        )
                else:
                    self.manager.handle_event(event)

            # ── Update ───────────────────────────────────────────────
            self.manager.update(dt)

            # ── Draw ─────────────────────────────────────────────────
            self.manager.draw(self.screen)

            # FPS counter (esquina superior derecha)
            fps_txt = self.fonts["mono"].render(
                f"{int(self.clock.get_fps())} fps", True, (50, 60, 80)
            )
            self.screen.blit(fps_txt, (SCREEN_W - fps_txt.get_width() - 8, 4))

            pygame.display.flip()

        self._shutdown()

    # ---------------------------------------------------------------- #
    #  Apagado limpio
    # ---------------------------------------------------------------- #

    def _shutdown(self):
        """Guarda estado antes de cerrar."""
        try:
            if self.manager.current and hasattr(self.manager.current, "tapo"):
                tapo = self.manager.current.tapo
                tapo.estado_sistema = False
                self.local_db.guardar_tapo(tapo)
                if self.sync_client.is_connected():
                    self.sync_client.upload_state(tapo)
        except Exception:
            pass
        finally:
            from db.connection import cerrar_conexion
            cerrar_conexion()
            pygame.quit()
            sys.exit(0)

    def _fatal(self, msg: str):
        """Muestra un error crítico y cierra."""
        font = pygame.font.SysFont("monospace", 14)
        self.screen.fill((10, 5, 15))
        y = 60
        for line in msg.split("\n"):
            s = font.render(line, True, (220, 80, 80))
            self.screen.blit(s, (40, y))
            y += 22
        hint = font.render("Presiona cualquier tecla para salir.", True, (100, 100, 120))
        self.screen.blit(hint, (40, y + 20))
        pygame.display.flip()
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.KEYDOWN):
                    waiting = False
        pygame.quit()
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────── #
#  Arranque
# ──────────────────────────────────────────────────────────────────── #

if __name__ == "__main__":
    App().run()