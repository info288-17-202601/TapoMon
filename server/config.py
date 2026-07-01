"""
server/config.py
Configuración centralizada del servidor TapoMon.

Justificación:
    Centralizar toda la configuración en un solo archivo permite:
    - Cambiar puertos, URIs y secretos sin tocar código de negocio.
    - Usar variables de entorno (.env) para cada ambiente (dev, prod).
    - Un único punto de verdad para constantes compartidas.
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass


# ------------------------------------------------------------------ #
#  MongoDB
# ------------------------------------------------------------------ #
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "Tapomon")

# ------------------------------------------------------------------ #
#  Servidor
# ------------------------------------------------------------------ #
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Región de este servidor (usada para identificación en el sistema multi-servidor).
# Cada instancia regional recibe un nombre único via variable de entorno.
SERVER_REGION = os.getenv("SERVER_REGION", "default")

# ------------------------------------------------------------------ #
#  JWT
# ------------------------------------------------------------------ #
JWT_SECRET  = os.getenv("JWT_SECRET", "tapomon-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# ------------------------------------------------------------------ #
#  Idle Simulation
# ------------------------------------------------------------------ #
IDLE_TICK_INTERVAL_SECONDS = int(os.getenv("IDLE_TICK_INTERVAL", "60"))

# Constantes de degradación (mismas que el game_engine del cliente)
TICK_HAMBRE      = -5
TICK_ENERGIA     = -3
TICK_FELICIDAD   = -4
TICK_SALUD_BASE  = -2

STAT_MIN = 0
STAT_MAX = 100

# ------------------------------------------------------------------ #
#  Independencia Mechanic (self-actions during IDLE)
# ------------------------------------------------------------------ #

# Independencia crece +1 por tick cuando salud >= este umbral
INDEPENDENCIA_GROWTH             = int(os.getenv("INDEPENDENCIA_GROWTH", "1"))
INDEPENDENCIA_HEALTH_THRESHOLD   = int(os.getenv("INDEPENDENCIA_HEALTH_THRESHOLD", "60"))

# Efectos de las acciones autónomas
SELF_FEED_HAMBRE     = int(os.getenv("SELF_FEED_HAMBRE",     "25"))   # comer solo
SELF_PLAY_FELICIDAD  = int(os.getenv("SELF_PLAY_FELICIDAD",  "20"))   # jugar solo: +felicidad
SELF_PLAY_ENERGIA    = int(os.getenv("SELF_PLAY_ENERGIA",    "-10"))  # jugar/entrenar: -energía
SELF_PLAY_ENERGIA_MIN = int(os.getenv("SELF_PLAY_ENERGIA_MIN", "15")) # energía mínima para jugar/entrenar
SELF_TRAIN_STAT      = int(os.getenv("SELF_TRAIN_STAT",      "1"))    # entrenar solo: +stat

# ------------------------------------------------------------------ #
#  Colecciones MongoDB (consistente con el cliente)
# ------------------------------------------------------------------ #
COL_USUARIOS = "Usuarios"
COL_MASCOTAS = "Tapo"
COL_INBOX    = "Inbox"
