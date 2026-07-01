"""
server/coordinator/config.py
Configuración del Coordinador Central TapoMon.

El coordinador es un microservicio liviano que gestiona:
- Asignación de jugadores a servidores regionales.
- Migraciones entre servidores (con cooldown de 24 horas).
- Registro global de qué servidor atiende a cada jugador.

Las URLs internas de los servidores regionales se configuran
mediante la variable REGIONAL_SERVERS_JSON, que es un JSON
con el mapeo nombre → URL interna (red Docker).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# ------------------------------------------------------------------ #
#  MongoDB del coordinador (base de datos propia, independiente)
# ------------------------------------------------------------------ #
MONGO_URI = os.getenv("COORDINATOR_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("COORDINATOR_MONGO_DB",  "TapomonCoordinator")

# ------------------------------------------------------------------ #
#  Coordinador
# ------------------------------------------------------------------ #
COORDINATOR_HOST = os.getenv("COORDINATOR_HOST", "0.0.0.0")
COORDINATOR_PORT = int(os.getenv("COORDINATOR_PORT", "8080"))

# ------------------------------------------------------------------ #
#  Migración
# ------------------------------------------------------------------ #
# Cooldown de migración en horas (el jugador puede migrar cada N horas)
MIGRATION_COOLDOWN_HOURS = int(os.getenv("MIGRATION_COOLDOWN_HOURS", "24"))

# ------------------------------------------------------------------ #
#  Servidores regionales disponibles
# ------------------------------------------------------------------ #
# JSON string: {"norte": "http://server-norte:8000", "sur": "http://server-sur:8000", ...}
_default_servers = json.dumps({
    "norte":  "http://server-norte:8000",
    "sur":    "http://server-sur:8000",
    "centro": "http://server-centro:8000",
})
REGIONAL_SERVERS: dict[str, str] = json.loads(
    os.getenv("REGIONAL_SERVERS_JSON", _default_servers)
)

# ------------------------------------------------------------------ #
#  Colecciones MongoDB del coordinador
# ------------------------------------------------------------------ #
COL_PLAYER_REGISTRY = "PlayerRegistry"   # {usuario_id, username, server_region, last_migration}
COL_SERVER_STATUS   = "ServerStatus"     # {server_name, player_count, last_heartbeat}
