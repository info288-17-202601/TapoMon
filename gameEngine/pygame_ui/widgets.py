"""
pygame_ui/widgets.py
Componentes de UI reutilizables: botones, barras, paneles, campos de texto.
"""
from __future__ import annotations
import pygame
from pygame_ui.constants import *
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Utilidades de dibujo
# ──────────────────────────────────────────────────────────────────── #
 
def draw_rounded_rect(surf: pygame.Surface, rect: pygame.Rect,
                      color, radius: int = CORNER,
                      border: int = 0, border_color=None) -> None:
    """Rectángulo con esquinas redondeadas, con borde opcional."""
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, border, border_radius=radius)
 
 
def draw_glowing_rect(surf: pygame.Surface, rect: pygame.Rect,
                      color, glow_color, glow_width: int = 2,
                      radius: int = CORNER) -> None:
    """Rectángulo con borde luminoso."""
    expanded = rect.inflate(glow_width * 2, glow_width * 2)
    pygame.draw.rect(surf, glow_color, expanded, glow_width, border_radius=radius + glow_width)
    pygame.draw.rect(surf, color, rect, border_radius=radius)
 
 
def lerp_color(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Barra de estadística
# ──────────────────────────────────────────────────────────────────── #
 
class StatBar:
    """
    Barra horizontal animada para mostrar HP, hambre, etc.
    Se anima suavemente hacia el valor objetivo.
    """
 
    def __init__(self, x: int, y: int, w: int, h: int = BAR_H,
                 color=C_HP_HIGH, bg_color=C_BG3, label: str = ""):
        self.rect     = pygame.Rect(x, y, w, h)
        self.color    = color
        self.bg_color = bg_color
        self.label    = label
        self._value   = 100.0   # valor actual animado (0-100)
        self._target  = 100.0
 
    def set_value(self, v: float) -> None:
        self._target = max(0.0, min(100.0, v))
 
    def update(self, dt: float) -> None:
        speed = 80.0  # unidades por segundo
        diff  = self._target - self._value
        if abs(diff) < 0.5:
            self._value = self._target
        else:
            self._value += diff * min(1.0, speed * dt / 100)
 
    def _bar_color(self):
        """Color dinámico según nivel."""
        if self.color == C_HP_HIGH:
            if self._value < 30:
                return C_HP_LOW
            elif self._value < 60:
                return C_HP_MID
        return self.color
 
    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        # Fondo
        draw_rounded_rect(surf, self.rect, self.bg_color, radius=self.rect.h // 2)
 
        # Relleno
        fill_w = int(self.rect.w * self._value / 100)
        if fill_w > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.h)
            draw_rounded_rect(surf, fill_rect, self._bar_color(), radius=self.rect.h // 2)
 
        # Etiqueta
        if self.label and font:
            label_surf = font.render(f"{self.label}  {int(self._value)}", True, C_GRAY_LIGHT)
            surf.blit(label_surf, (self.rect.x, self.rect.y - label_surf.get_height() - 2))
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Botón
# ──────────────────────────────────────────────────────────────────── #
 
class Button:
    """
    Botón interactivo con hover y press.
    Llama a `callback` al hacer clic.
    """
 
    def __init__(self, x: int, y: int, w: int, h: int = BTN_H,
                 text: str = "", callback=None,
                 color=C_BG3, hover_color=C_BG2,
                 text_color=C_WHITE, accent_color=C_ACCENT,
                 icon: str = ""):
        self.rect        = pygame.Rect(x, y, w, h)
        self.text        = text
        self.icon        = icon
        self.callback    = callback
        self.color       = color
        self.hover_color = hover_color
        self.text_color  = text_color
        self.accent      = accent_color
        self._hover      = False
        self._pressed    = False
        self._press_t    = 0.0
 
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._pressed = True
                self._press_t = 0.0
                if self.callback:
                    self.callback()
                return True
        if event.type == pygame.MOUSEBUTTONUP:
            self._pressed = False
        return False
 
    def update(self, dt: float) -> None:
        self._hover   = self.rect.collidepoint(pygame.mouse.get_pos())
        self._press_t = max(0.0, self._press_t - dt)
 
    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        # Color de fondo según estado
        base_col = self.hover_color if self._hover else self.color
        rect     = self.rect.inflate(-2, -2) if self._pressed else self.rect
 
        draw_glowing_rect(surf, rect, base_col,
                          self.accent if self._hover else C_BORDER,
                          glow_width=1 if not self._hover else 2)
 
        # Texto + ícono
        label = f"{self.icon}  {self.text}" if self.icon else self.text
        if font:
            txt_surf = font.render(label, True, self.text_color)
            tx = rect.centerx - txt_surf.get_width() // 2
            ty = rect.centery - txt_surf.get_height() // 2
            surf.blit(txt_surf, (tx, ty))
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Campo de texto
# ──────────────────────────────────────────────────────────────────── #
 
class TextField:
    """Campo de texto editable con cursor parpadeante."""
 
    def __init__(self, x: int, y: int, w: int, h: int = BTN_H,
                 placeholder: str = "", password: bool = False):
        self.rect        = pygame.Rect(x, y, w, h)
        self.placeholder = placeholder
        self.password    = password
        self.text        = ""
        self.active      = False
        self._cursor_t   = 0.0
        self._show_cursor= True
        self._got_char   = False   # flag anti-doble-input
 
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self._got_char = False

        if not self.active:
            return False

        if event.type == pygame.KEYDOWN:
            self._got_char = False          # reset al inicio de cada tecla
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                return True
            if event.key in (pygame.K_RETURN, pygame.K_TAB, pygame.K_ESCAPE):
                return True
            # event.unicode funciona para teclas normales (a-z, 0-9, etc.)
            # pero AltGr+tecla devuelve unicode vacío en Windows — lo maneja TEXTINPUT
            if event.unicode and event.unicode.isprintable():
                if len(self.text) < 64:
                    self.text += event.unicode
                self._got_char = True
            return True

        if event.type == pygame.TEXTINPUT:
            # Solo agregar si KEYDOWN no pudo capturar el caracter.
            # Esto cubre AltGr+tecla (@, |, ~, etc.) que event.unicode no ve.
            if not self._got_char:
                for ch in event.text:
                    if ch.isprintable() and len(self.text) < 64:
                        self.text += ch
            self._got_char = False
            return True

        return False
 

    def update(self, dt: float) -> None:
        self._cursor_t += dt
        if self._cursor_t >= 0.5:
            self._cursor_t  = 0.0
            self._show_cursor = not self._show_cursor
 
    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        border_col = C_ACCENT if self.active else C_BORDER
        draw_glowing_rect(surf, self.rect, C_BG3, border_col,
                          glow_width=1 if not self.active else 2)
 
        if font:
            display = self.text if not self.password else "●" * len(self.text)
            if not display and not self.active:
                txt_surf = font.render(self.placeholder, True, C_GRAY)
            else:
                txt_surf = font.render(display, True, C_WHITE)
            surf.blit(txt_surf, (self.rect.x + PAD, self.rect.centery - txt_surf.get_height() // 2))
 
            # Cursor parpadeante
            if self.active and self._show_cursor:
                cx = self.rect.x + PAD + txt_surf.get_width() + 2
                cy1 = self.rect.centery - 10
                cy2 = self.rect.centery + 10
                pygame.draw.line(surf, C_ACCENT, (cx, cy1), (cx, cy2), 2)
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Panel con título
# ──────────────────────────────────────────────────────────────────── #
 
class Panel:
    """Rectángulo con borde y título opcional."""
 
    def __init__(self, x: int, y: int, w: int, h: int,
                 title: str = "", accent_color=C_BORDER):
        self.rect   = pygame.Rect(x, y, w, h)
        self.title  = title
        self.accent = accent_color
 
    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        draw_rounded_rect(surf, self.rect, C_BG2, radius=CORNER,
                          border=1, border_color=self.accent)
        if self.title and font:
            txt = font.render(self.title, True, self.accent)
            surf.blit(txt, (self.rect.x + PAD, self.rect.y + PAD // 2))
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Mensaje flotante (feedback al usuario)
# ──────────────────────────────────────────────────────────────────── #
 
class Toast:
    """Mensaje que aparece brevemente y desaparece."""
 
    DURATION = 2.5
 
    def __init__(self, text: str, ok: bool = True):
        self.text  = text
        self.color = C_HP_HIGH if ok else C_HP_LOW
        self._t    = self.DURATION
 
    @property
    def alive(self) -> bool:
        return self._t > 0
 
    def update(self, dt: float) -> None:
        self._t -= dt
 
    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        if not font:
            return
        alpha = min(1.0, self._t / 0.4)
        txt   = font.render(self.text, True, self.color)
        x     = (surf.get_width() - txt.get_width()) // 2
        y     = surf.get_height() - 80
        # Fondo semitransparente
        bg = pygame.Surface((txt.get_width() + PAD * 2, txt.get_height() + PAD), pygame.SRCALPHA)
        bg.fill((*C_BG2, int(200 * alpha)))
        surf.blit(bg, (x - PAD, y - PAD // 2))
        surf.blit(txt, (x, y))