"""
server/coordinator/main.py
Punto de entrada del Coordinador Central TapoMon.

Microservicio liviano que gestiona:
- Asignación de jugadores a servidores regionales (POST /assign).
- Resolución de servidor por jugador (GET /resolve/{usuario_id}).
- Migración entre servidores con cooldown (POST /migrate).
- Listado de servidores disponibles (GET /servers).

Este servicio NO maneja datos del juego (tapos, mascotas, inbox).
Solo mantiene el registro de qué jugador está en qué servidor.
"""
from __future__ import annotations

import sys
import os

# Agregar el directorio raíz al PATH para resolver imports absolutos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from server.coordinator.db.mongo import get_db, cerrar_conexion, crear_indices
from server.coordinator.config import COORDINATOR_HOST, COORDINATOR_PORT, REGIONAL_SERVERS
from server.coordinator.models.schemas import (
    AssignRequest,
    AssignResponse,
    MigrateRequest,
    MigrateResponse,
    ResolveResponse,
    ServerListResponse,
    ServerInfo,
)
from server.coordinator.services.registry import (
    asignar_servidor,
    resolver_servidor,
    resolver_servidor_por_username,
    listar_servidores,
)
from server.coordinator.services.migration import migrar_jugador


def safe_print(emoji_text: str, fallback_text: str) -> None:
    """Imprime el texto con emoji, si hay un error de codificación usa el fallback."""
    try:
        print(emoji_text)
    except UnicodeEncodeError:
        print(fallback_text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle del coordinador: conectar a MongoDB al inicio, cerrar al final."""
    safe_print(
        "🌐  Iniciando Coordinador Central TapoMon...",
        "[COORDINATOR] Iniciando Coordinador Central TapoMon..."
    )
    get_db()
    crear_indices()

    servers_list = ", ".join(REGIONAL_SERVERS.keys())
    safe_print(
        f"📡  Servidores regionales configurados: {servers_list}",
        f"[COORDINATOR] Servidores regionales configurados: {servers_list}"
    )

    yield

    safe_print(
        "🛑  Deteniendo Coordinador Central...",
        "[COORDINATOR] Deteniendo Coordinador Central..."
    )
    cerrar_conexion()


# ------------------------------------------------------------------ #
#  Aplicación FastAPI
# ------------------------------------------------------------------ #
app = FastAPI(
    title="TapoMon Coordinator",
    description=(
        "Coordinador Central del sistema multi-servidor TapoMon.\n\n"
        "Gestiona la asignación de jugadores a servidores regionales "
        "y las migraciones entre servidores."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------ #
#  Endpoints
# ------------------------------------------------------------------ #

@app.post("/assign", response_model=AssignResponse)
async def assign_server(request: AssignRequest):
    """
    Asigna un jugador nuevo al servidor regional con menor carga.

    Si el jugador ya está registrado, retorna su servidor actual.
    Se llama durante el registro del jugador en el cliente.
    """
    result = asignar_servidor(
        usuario_id=request.usuario_id,
        username=request.username,
        target_region=request.target_region
    )
    return AssignResponse(**result)


@app.get("/resolve/{usuario_id}", response_model=ResolveResponse)
async def resolve_server(usuario_id: str):
    """
    Resuelve qué servidor regional atiende a un jugador por su ID.

    Se llama durante el login para saber a dónde enviar los requests.
    """
    result = resolver_servidor(usuario_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return ResolveResponse(**result)


@app.get("/resolve-by-username/{username}", response_model=ResolveResponse)
async def resolve_server_by_username(username: str):
    """
    Resuelve qué servidor regional atiende a un jugador por su username.

    Útil durante el login, cuando el cliente solo conoce el username
    y aún no tiene el usuario_id.
    """
    result = resolver_servidor_por_username(username)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return ResolveResponse(**result)


@app.post("/migrate", response_model=MigrateResponse)
async def migrate_player(request: MigrateRequest):
    """
    Migra un jugador a otro servidor regional.

    Cooldown: el jugador puede migrar como máximo una vez cada 24 horas.
    El proceso exporta datos del servidor origen, los importa al destino,
    y limpia el origen.
    """
    result = migrar_jugador(request.usuario_id, request.target_server)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return MigrateResponse(**result)


@app.get("/servers", response_model=ServerListResponse)
async def list_servers():
    """
    Lista todos los servidores regionales disponibles y su carga actual.
    """
    servers = listar_servidores()
    return ServerListResponse(
        success=True,
        servers=[ServerInfo(**s) for s in servers],
    )


@app.get("/", tags=["Health"])
async def health_check():
    """Endpoint de salud del coordinador."""
    return {
        "status": "ok",
        "service": "TapoMon Coordinator",
        "version": "1.0.0",
        "regional_servers": list(REGIONAL_SERVERS.keys()),
    }


# ------------------------------------------------------------------ #
#  Ejecución directa
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.coordinator.main:app",
        host=COORDINATOR_HOST,
        port=COORDINATOR_PORT,
        workers=1,
        reload=False,
    )
