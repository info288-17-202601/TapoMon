"""
pygame_ui/screen_manager.py
Gestor de pantallas con pila de navegación.
El game loop solo interactúa con esta clase.
"""
from __future__ import annotations
import pygame
from pygame_ui.constants import C_BG
 
 
class Screen:
    """Clase base para todas las pantallas del juego."""
 
    def __init__(self, manager: "ScreenManager"):
        self.manager = manager
 
    def on_enter(self) -> None:
        """Llamado cuando esta pantalla se vuelve activa."""
 
    def on_exit(self) -> None:
        """Llamado cuando se sale de esta pantalla."""
 
    def handle_event(self, event: pygame.event.Event) -> None:
        """Procesa eventos de pygame."""
 
    def update(self, dt: float) -> None:
        """Lógica de actualización."""
 
    def draw(self, surf: pygame.Surface) -> None:
        """Renderizado."""
 
 
class ScreenManager:
    """
    Mantiene una pila de pantallas.
    - push(screen)  → añade pantalla encima (preserva la anterior)
    - pop()         → vuelve a la pantalla anterior
    - replace(screen) → reemplaza la pantalla actual
    """
 
    def __init__(self):
        self._stack: list[Screen] = []
 
    @property
    def current(self) -> Screen | None:
        return self._stack[-1] if self._stack else None
 
    def push(self, screen: Screen) -> None:
        if self.current:
            self.current.on_exit()
        self._stack.append(screen)
        screen.on_enter()
 
    def pop(self) -> None:
        if self._stack:
            self._stack.pop().on_exit()
        if self.current:
            self.current.on_enter()
 
    def replace(self, screen: Screen) -> None:
        if self._stack:
            self._stack.pop().on_exit()
        self._stack.append(screen)
        screen.on_enter()
 
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.current:
            self.current.handle_event(event)
 
    def update(self, dt: float) -> None:
        if self.current:
            self.current.update(dt)
 
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(C_BG)
        if self.current:
            self.current.draw(surf)