"""
server/coordinator/services/migration.py
Servicio de migración de jugadores entre servidores regionales.

Flujo de migración:
1. El jugador solicita migrar a un servidor destino.
2. Se verifica el cooldown (mínimo 24 horas desde la última migración).
3. Se exportan los datos del jugador del servidor origen.
4. Se importan los datos al servidor destino.
5. Se eliminan los datos del servidor origen.
6. Se actualiza el registro en el coordinador.

Los pasos 3-5 usan endpoints internos (/internal/...) que solo
son accesibles dentro de la red Docker (no expuestos por Nginx).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from server.coordinator.db.mongo import get_db
from server.coordinator.config import (
    REGIONAL_SERVERS,
    MIGRATION_COOLDOWN_HOURS,
    COL_PLAYER_REGISTRY,
)


# Timeout para llamadas HTTP internas entre servicios
_INTERNAL_TIMEOUT = 30.0


def migrar_jugador(usuario_id: str, target_server: str) -> dict:
    """
    Migra un jugador de su servidor actual a otro servidor regional.

    Args:
        usuario_id:    UUID del jugador.
        target_server: Nombre del servidor destino (ej: "sur").

    Returns:
        dict con {success, message, old_server, new_server, new_server_url}
    """
    db = get_db()

    # 1. Verificar que el jugador existe en el registro
    player = db[COL_PLAYER_REGISTRY].find_one({"usuario_id": usuario_id})
    if player is None:
        return {
            "success": False,
            "message": "Jugador no registrado en el coordinador.",
        }

    current_server = player["server_region"]

    # 2. Verificar que el destino es diferente al actual
    if current_server == target_server:
        return {
            "success": False,
            "message": f"Ya estás en el servidor '{target_server}'.",
        }

    # 3. Verificar que el servidor destino existe
    if target_server not in REGIONAL_SERVERS:
        available = ", ".join(REGIONAL_SERVERS.keys())
        return {
            "success": False,
            "message": f"Servidor '{target_server}' no existe. Disponibles: {available}",
        }

    # 4. Verificar cooldown de migración
    last_migration = player.get("last_migration")
    if last_migration:
        try:
            last_dt = datetime.fromisoformat(last_migration)
            cooldown_end = last_dt + timedelta(hours=MIGRATION_COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                remaining = cooldown_end - datetime.now()
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return {
                    "success": False,
                    "message": (
                        f"Debes esperar {hours}h {minutes}m antes de migrar de nuevo. "
                        f"Cooldown: {MIGRATION_COOLDOWN_HOURS} horas."
                    ),
                }
        except (ValueError, TypeError):
            pass

    # 5. URLs de los servidores
    origin_url = REGIONAL_SERVERS[current_server]
    target_url = REGIONAL_SERVERS[target_server]

    try:
        # 6. Exportar datos del servidor origen
        export_resp = httpx.get(
            f"{origin_url}/internal/export/{usuario_id}",
            timeout=_INTERNAL_TIMEOUT,
        )
        if export_resp.status_code != 200:
            return {
                "success": False,
                "message": f"Error al exportar datos del servidor '{current_server}': {export_resp.text}",
            }
        player_data = export_resp.json()

        # 7. Importar datos al servidor destino
        import_resp = httpx.post(
            f"{target_url}/internal/import",
            json=player_data,
            timeout=_INTERNAL_TIMEOUT,
        )
        if import_resp.status_code != 200:
            return {
                "success": False,
                "message": f"Error al importar datos al servidor '{target_server}': {import_resp.text}",
            }

        # 8. Limpiar datos del servidor origen
        cleanup_resp = httpx.delete(
            f"{origin_url}/internal/cleanup/{usuario_id}",
            timeout=_INTERNAL_TIMEOUT,
        )
        if cleanup_resp.status_code != 200:
            # Log warning pero no fallar — los datos ya están en el destino
            try:
                print(f"⚠️  [MIGRATION] Advertencia al limpiar datos de '{current_server}': {cleanup_resp.text}")
            except UnicodeEncodeError:
                print(f"[WARN] [MIGRATION] Advertencia al limpiar datos de '{current_server}'")

    except httpx.ConnectError as e:
        return {
            "success": False,
            "message": f"No se pudo conectar con los servidores regionales: {e}",
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": "Timeout durante la migración. Intente de nuevo.",
        }

    # 9. Actualizar registro en el coordinador
    db[COL_PLAYER_REGISTRY].update_one(
        {"usuario_id": usuario_id},
        {"$set": {
            "server_region":  target_server,
            "last_migration": datetime.now().isoformat(),
        }},
    )

    return {
        "success": True,
        "message": f"Migración exitosa de '{current_server}' a '{target_server}'.",
        "old_server": current_server,
        "new_server": target_server,
        "new_server_url": target_url,
    }
