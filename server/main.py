"""
server/main.py
Punto de entrada del servidor central TapoMon.

Justificación:
    FastAPI como framework por:
    - Soporte async nativo (mejor rendimiento con I/O concurrente).
    - Validación automática con Pydantic (schemas.py).
    - Documentación OpenAPI auto-generada (/docs).
    - Lifecycle events (startup/shutdown) para manejar DB y scheduler.

    APScheduler ejecuta la simulación IDLE periódicamente sin necesidad
    de infraestructura adicional (Celery/Redis). Suficiente para el MVP.
"""
from __future__ import annotations

import sys
import os
# Agregar el directorio padre al PATH de python para poder resolver 'server' de forma absoluta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

from fastapi.responses import HTMLResponse

from server.api.sync_routes import router as sync_router
from server.api.auth_routes import router as auth_router
from server.api.dashboard_routes import router as dashboard_router
from server.db.mongo import get_db, cerrar_conexion, crear_indices
from server.services.idle_engine import ejecutar_idle_tick
from server.config import SERVER_HOST, SERVER_PORT, IDLE_TICK_INTERVAL_SECONDS


def safe_print(emoji_text: str, fallback_text: str) -> None:
    """Imprime el texto con emoji, si hay un error de codificación usa el fallback sin emojis."""
    try:
        print(emoji_text)
    except UnicodeEncodeError:
        print(fallback_text)


# ------------------------------------------------------------------ #
#  Scheduler para Idle Simulation
# ------------------------------------------------------------------ #
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle de FastAPI:
    - Startup: conectar a MongoDB, crear índices, iniciar scheduler.
    - Shutdown: detener scheduler, cerrar conexión a MongoDB.
    """
    # --- Startup ---
    safe_print("🚀  Iniciando servidor TapoMon...", "[SERVER] Iniciando servidor TapoMon...")
    get_db()                # Forzar conexión a MongoDB
    crear_indices()         # Crear índices necesarios

    # Programar la simulación IDLE
    scheduler.add_job(
        ejecutar_idle_tick,
        "interval",
        seconds=IDLE_TICK_INTERVAL_SECONDS,
        id="idle_simulation",
        replace_existing=True,
    )
    scheduler.start()
    safe_print(
        f"⏰  Idle Simulation programada cada {IDLE_TICK_INTERVAL_SECONDS}s.",
        f"[SERVER] Idle Simulation programada cada {IDLE_TICK_INTERVAL_SECONDS}s."
    )

    yield

    # --- Shutdown ---
    safe_print("🛑  Deteniendo servidor TapoMon...", "[SERVER] Deteniendo servidor TapoMon...")
    scheduler.shutdown(wait=False)
    cerrar_conexion()


# ------------------------------------------------------------------ #
#  Aplicación FastAPI
# ------------------------------------------------------------------ #
app = FastAPI(
    title="TapoMon Central Server",
    description=(
        "Servidor central del sistema TapoMon.\n\n"
        "Expone el **SyncService** para sincronización de estado "
        "y ejecuta la **Idle Simulation** para mascotas desconectadas."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/auth", tags=["Autenticación"])
app.include_router(sync_router, prefix="/sync", tags=["SyncService"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_dashboard():
    """Sirve la interfaz web del Dashboard de monitoreo."""
    try:
        with open("server/templates/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            status_code=404,
            content="<h3>Error: El archivo de la plantilla index.html no fue encontrado.</h3>"
        )


@app.get("/", tags=["Health"])
async def health_check():
    """Endpoint de salud para verificar que el servidor está corriendo."""
    return {
        "status": "ok",
        "service": "TapoMon Central Server",
        "version": "1.0.0",
    }


# ------------------------------------------------------------------ #
#  Ejecución directa
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )
