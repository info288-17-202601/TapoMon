"""
pygame_ui/tapo_sprite.py
Sprite procedural del Tapo: dibujado con formas geométricas simples.
Soporta estados: idle, attack, hurt, dead.
Diseñado para ser reemplazado por sprites PNG cuando existan los assets.
"""
from __future__ import annotations
import math
import os
import pygame
from pygame_ui.constants import *
 
 
class TapoSprite:
    """
    Representa visualmente al Tapo con animaciones procedurales.
 
    Estados:
        "idle"   — respiración suave (bob vertical)
        "attack" — squash & stretch + flash
        "hurt"   — sacudida lateral
        "dead"   — caída y desvanecimiento
        "happy"  — salto con estela
    """
 
    def __init__(self, cx: int, cy: int, tipo: str = "Normal", scale: float = 1.0):
        self.cx    = cx
        self.cy    = cy
        self.tipo  = tipo
        self.scale = scale
 
        self.state  = "idle"
        self._t     = 0.0       # tiempo acumulado en el estado
        self._flash = 0.0       # flash blanco de golpe
 
        # Offsets animados
        self._bob_y   = 0.0
        self._shake_x = 0.0
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._alpha   = 255
 
    # ---------------------------------------------------------------- #
    #  Control de estado
    # ---------------------------------------------------------------- #
 
    def set_state(self, state: str) -> None:
        self.state = state
        self._t    = 0.0
        self._flash = 0.3 if state in ("attack", "hurt") else 0.0
 
    # ---------------------------------------------------------------- #
    #  Update
    # ---------------------------------------------------------------- #
 
    def update(self, dt: float) -> None:
        self._t    += dt
        self._flash = max(0.0, self._flash - dt * 3)
 
        if self.state == "idle":
            self._bob_y   = math.sin(self._t * 2.0) * 5 * self.scale
            self._shake_x = 0.0
            self._scale_x = 1.0
            self._scale_y = 1.0
            self._alpha   = 255
 
        elif self.state == "attack":
            phase = self._t * 8.0
            self._bob_y   = -abs(math.sin(phase)) * 15 * self.scale
            self._scale_x = 1.0 + abs(math.sin(phase * 0.5)) * 0.25
            self._scale_y = 1.0 - abs(math.sin(phase * 0.5)) * 0.15
            if self._t > 0.6:
                self.set_state("idle")
 
        elif self.state == "hurt":
            self._shake_x = math.sin(self._t * 30) * 12 * (1 - self._t / 0.5)
            if self._t > 0.5:
                self.set_state("idle")
 
        elif self.state == "happy":
            phase = self._t * 6.0
            self._bob_y   = -abs(math.sin(phase)) * 20 * self.scale
            self._scale_x = 1.0 + math.sin(phase * 2) * 0.1
            self._scale_y = 1.0 - math.sin(phase * 2) * 0.1
            if self._t > 1.2:
                self.set_state("idle")
 
        elif self.state == "dead":
            self._bob_y   = min(40.0, self._t * 60)
            self._alpha   = max(0, int(255 * (1.0 - self._t / 1.5)))
 
    # ---------------------------------------------------------------- #
    #  Draw
    # ---------------------------------------------------------------- #
 
    def draw(self, surf):
        # Load sprite relative to this module so CWD doesn't matter.
        base_dir = os.path.dirname(__file__)
        sprite_path = os.path.join(base_dir, "sprites", f"tapo-{self.tipo}.png")
        img = pygame.image.load(sprite_path)
        surf.blit(img, (self.cx - img.get_width()//2,
                        self.cy - img.get_height()//2 + self._bob_y))