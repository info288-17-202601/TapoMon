"""
pygame_ui/constants.py
Paleta de colores, tipografía y constantes visuales de TapoMon.
"""
 
# ── Resolución ───────────────────────────────────────────────────────
SCREEN_W = 800
SCREEN_H = 600
FPS      = 60
 
# ── Paleta ───────────────────────────────────────────────────────────
# Fondo oscuro con acento neón — estética tamagotchi retro-futurista
C_BG           = (10,  12,  20)   # negro azulado
C_BG2          = (18,  22,  36)   # panel principal
C_BG3          = (25,  30,  48)   # panel secundario
C_BORDER       = (45,  55,  90)   # bordes tenues
C_BORDER_GLOW  = (80, 140, 255)   # borde iluminado
 
# Acento principal — cian eléctrico
C_ACCENT       = (0,   220, 255)
C_ACCENT_DIM   = (0,   120, 160)
C_ACCENT_DARK  = (0,    40,  60)
 
# Colores semánticos
C_WHITE        = (230, 235, 255)
C_GRAY         = (100, 110, 140)
C_GRAY_LIGHT   = (160, 170, 200)
 
C_HP_HIGH      = (50,  220, 120)  # > 60%
C_HP_MID       = (240, 180,  30)  # 30-60%
C_HP_LOW       = (220,  60,  60)  # < 30%
 
C_HUNGER       = (255, 160,  40)
C_ENERGY       = (80,  180, 255)
C_HAPPINESS    = (255, 100, 180)
C_HEALTH       = (80,  220, 130)
 
# Tipos de Tapo
TYPE_COLORS = {
    "Fuego":     (255,  90,  40),
    "Agua":      ( 40, 140, 255),
    "Planta":    ( 60, 200,  80),
    "Luz":       (255, 230,  80),
    "Oscuridad": (160,  60, 255),
    "Normal":    (160, 170, 200),
}
 
# ── Fuentes (se inicializan en App.setup) ────────────────────────────
FONT_TITLE  = None   # 32px bold
FONT_LABEL  = None   # 18px
FONT_SMALL  = None   # 13px
FONT_MONO   = None   # 14px monoespaciada
 
# ── Dimensiones de UI ────────────────────────────────────────────────
PAD         = 16     # padding base
BAR_H       = 14     # alto de barra de stat
CORNER      = 10     # radio de esquinas
BTN_H       = 44     # alto de botón estándar