"""
server/coordinator/services/registry.py
Servicio de registro y asignación de jugadores a servidores regionales.

Responsabilidades:
- Asignar un jugador nuevo al servidor con menor carga (balanceo simple).
- Resolver qué servidor atiende a un jugador dado.
- Listar servidores con su conteo de jugadores.

La asignación usa una estrategia de "menor carga" (least-connections):
se cuenta cuántos jugadores tiene cada servidor y se asigna al que
tenga menos. Esto es determinista y no requiere heartbeats en tiempo real.
"""
from __future__ import annotations

from datetime import datetime

from server.coordinator.db.mongo import get_db
from server.coordinator.config import (
    REGIONAL_SERVERS,
    COL_PLAYER_REGISTRY,
    COL_SERVER_STATUS,
)


def asignar_servidor(usuario_id: str, username: str, correo: str, target_region: str | None = None) -> dict:
    """
    Asigna un jugador nuevo al servidor regional especificado o al de menor carga.

    Verifica primero que el username y correo sean únicos a nivel global en el coordinador.
    Si el jugador ya está registrado (mismo usuario_id), retorna su servidor actual.

    Args:
        usuario_id: UUID del jugador.
        username:   Nombre de usuario.
        correo:     Correo electrónico.
        target_region: (Opcional) Nombre del servidor destino a asignar.

    Returns:
        dict con {success, message, server_region, server_url}
    """
    db = get_db()

    # Verificar si ya está registrado por ID (caso de retry)
    existing = db[COL_PLAYER_REGISTRY].find_one({"usuario_id": usuario_id})
    if existing:
        region = existing["server_region"]
        url = REGIONAL_SERVERS.get(region, "")
        return {
            "success": True,
            "message": f"Jugador ya asignado al servidor '{region}'.",
            "server_region": region,
            "server_url": url,
        }

    # Verificar unicidad global de Username y Correo
    if db[COL_PLAYER_REGISTRY].find_one({"username": {"$regex": f"^{username}$", "$options": "i"}}):
        return {
            "success": False,
            "message": "El nombre de usuario ya está registrado globalmente.",
            "server_region": None,
            "server_url": None,
        }
        
    if db[COL_PLAYER_REGISTRY].find_one({"correo": {"$regex": f"^{correo}$", "$options": "i"}}):
        return {
            "success": False,
            "message": "El correo electrónico ya está en uso globalmente.",
            "server_region": None,
            "server_url": None,
        }

    # Contar jugadores por servidor para balanceo
    server_counts: dict[str, int] = {}
    for server_name in REGIONAL_SERVERS:
        count = db[COL_PLAYER_REGISTRY].count_documents(
            {"server_region": server_name}
        )
        server_counts[server_name] = count

    # Seleccionar el servidor
    target = target_region if target_region and target_region in REGIONAL_SERVERS else min(server_counts, key=server_counts.get)  # type: ignore[arg-type]
    target_url = REGIONAL_SERVERS[target]

    # Registrar al jugador
    db[COL_PLAYER_REGISTRY].insert_one({
        "usuario_id":     usuario_id,
        "username":       username,
        "correo":         correo,
        "server_region":  target,
        "assigned_at":    datetime.now().isoformat(),
        "last_migration": None,
    })

    return {
        "success": True,
        "message": f"Jugador asignado al servidor '{target}'.",
        "server_region": target,
        "server_url": target_url,
    }


def resolver_servidor(usuario_id: str) -> dict:
    """
    Resuelve qué servidor regional atiende a un jugador.

    Args:
        usuario_id: UUID del jugador.

    Returns:
        dict con {success, message, server_region, server_url}
    """
    db = get_db()

    doc = db[COL_PLAYER_REGISTRY].find_one({"usuario_id": usuario_id})
    if doc is None:
        return {
            "success": False,
            "message": "Jugador no registrado en el coordinador.",
            "server_region": None,
            "server_url": None,
        }

    region = doc["server_region"]
    url = REGIONAL_SERVERS.get(region, "")

    return {
        "success": True,
        "message": f"Jugador asignado al servidor '{region}'.",
        "server_region": region,
        "server_url": url,
    }


def resolver_servidor_por_username(username: str) -> dict:
    """
    Resuelve qué servidor regional atiende a un jugador por su username.

    Útil durante el login, cuando el cliente solo conoce el username
    y aún no tiene el usuario_id.

    Args:
        username: Nombre de usuario.

    Returns:
        dict con {success, message, server_region, server_url, usuario_id}
    """
    db = get_db()

    doc = db[COL_PLAYER_REGISTRY].find_one(
        {"username": {"$regex": f"^{username}$", "$options": "i"}}
    )
    if doc is None:
        return {
            "success": False,
            "message": "Jugador no registrado en el coordinador.",
            "server_region": None,
            "server_url": None,
            "usuario_id": None,
        }

    region = doc["server_region"]
    url = REGIONAL_SERVERS.get(region, "")

    return {
        "success": True,
        "message": f"Jugador asignado al servidor '{region}'.",
        "server_region": region,
        "server_url": url,
        "usuario_id": doc["usuario_id"],
    }


def listar_servidores() -> list[dict]:
    """
    Lista todos los servidores regionales con su conteo de jugadores.

    Returns:
        Lista de dicts con {name, url, player_count}.
    """
    db = get_db()
    result = []

    for server_name, server_url in REGIONAL_SERVERS.items():
        count = db[COL_PLAYER_REGISTRY].count_documents(
            {"server_region": server_name}
        )
        result.append({
            "name": server_name,
            "url": server_url,
            "player_count": count,
        })

    return result
