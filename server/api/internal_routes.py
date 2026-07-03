"""
server/api/internal_routes.py
Endpoints internos para migración entre servidores regionales.

Estos endpoints son invocados por el Coordinador Central durante
el proceso de migración de un jugador. NO están expuestos al público
a través de Nginx — solo son accesibles dentro de la red Docker.

Endpoints:
- GET  /internal/export/{usuario_id}  → Exporta todos los datos de un jugador.
- POST /internal/import               → Importa datos de un jugador migrado.
- DELETE /internal/cleanup/{usuario_id} → Elimina datos de un jugador migrado.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from server.db.mongo import get_db
from server.config import COL_USUARIOS, COL_MASCOTAS, COL_INBOX

router = APIRouter()


@router.get("/export/{usuario_id}")
async def export_player(usuario_id: str):
    """
    Exporta todos los datos de un jugador para migración.

    Recopila: documento de usuario, documento del Tapo, y todos
    los mensajes del Inbox dirigidos a su mascota.

    Returns:
        JSON con {usuario, tapo, inbox} — todo lo necesario para
        reconstruir al jugador en otro servidor.
    """
    db = get_db()

    # Buscar usuario
    usuario_doc = db[COL_USUARIOS].find_one({"Id": usuario_id})
    if usuario_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario '{usuario_id}' no encontrado en este servidor."
        )

    # Limpiar _id de MongoDB
    usuario_doc.pop("_id", None)

    tapo_id = usuario_doc.get("Tapo_ID", "")

    # Buscar Tapo
    tapo_doc = None
    if tapo_id:
        tapo_doc = db[COL_MASCOTAS].find_one({"id_mascota": tapo_id})
        if tapo_doc:
            tapo_doc.pop("_id", None)
            # Normalizar Timestamp si es datetime
            if isinstance(tapo_doc.get("Last_Sync"), datetime):
                tapo_doc["Last_Sync"] = tapo_doc["Last_Sync"].isoformat()

    # Recopilar Inbox (todos los mensajes, no solo los no leídos)
    inbox = []
    if tapo_id:
        for msg in db[COL_INBOX].find({"Recipient_ID": tapo_id}):
            msg.pop("_id", None)
            if isinstance(msg.get("Timestamp"), datetime):
                msg["Timestamp"] = msg["Timestamp"].isoformat()
            inbox.append(msg)

    return {
        "usuario": usuario_doc,
        "tapo": tapo_doc,
        "inbox": inbox,
    }


@router.post("/import")
async def import_player(data: dict):
    """
    Importa datos de un jugador migrado desde otro servidor.

    Recibe el paquete completo {usuario, tapo, inbox} exportado
    por el servidor origen e inserta todo en la base de datos local.

    Usa upsert para evitar duplicados si el proceso se repite
    (idempotencia en caso de reintentos).
    """
    db = get_db()

    usuario_doc = data.get("usuario")
    tapo_doc    = data.get("tapo")
    inbox       = data.get("inbox", [])

    if not usuario_doc or not usuario_doc.get("Id"):
        raise HTTPException(
            status_code=400,
            detail="Datos de usuario incompletos."
        )

    # Importar usuario (upsert por Id)
    usuario_doc.pop("_id", None)
    db[COL_USUARIOS].update_one(
        {"Id": usuario_doc["Id"]},
        {"$set": usuario_doc},
        upsert=True,
    )

    # Importar Tapo (upsert por id_mascota)
    if tapo_doc and tapo_doc.get("id_mascota"):
        tapo_doc.pop("_id", None)
        # Limpiar Friend_List y Gift_Cooldowns porque los amigos pertenecen al servidor anterior
        tapo_doc["Friend_List"] = []
        tapo_doc["Gift_Cooldowns"] = []
        db[COL_MASCOTAS].update_one(
            {"id_mascota": tapo_doc["id_mascota"]},
            {"$set": tapo_doc},
            upsert=True,
        )

    # Importar Inbox (upsert por ID_Mensaje)
    for msg in inbox:
        msg.pop("_id", None)
        msg_id = msg.get("ID_Mensaje")
        if msg_id:
            db[COL_INBOX].update_one(
                {"ID_Mensaje": msg_id},
                {"$set": msg},
                upsert=True,
            )

    return {
        "success": True,
        "message": f"Jugador '{usuario_doc.get('Username', '')}' importado correctamente.",
    }


@router.delete("/cleanup/{usuario_id}")
async def cleanup_player(usuario_id: str):
    """
    Elimina todos los datos de un jugador migrado de este servidor.

    Se llama DESPUÉS de que la importación al servidor destino fue exitosa.
    Elimina: usuario, Tapo, y todos los mensajes del Inbox.
    """
    db = get_db()

    # Buscar usuario para obtener su Tapo_ID
    usuario_doc = db[COL_USUARIOS].find_one({"Id": usuario_id})
    if usuario_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario '{usuario_id}' no encontrado en este servidor."
        )

    tapo_id = usuario_doc.get("Tapo_ID", "")

    # Eliminar en orden: Inbox → Tapo → Usuario
    if tapo_id:
        db[COL_INBOX].delete_many({"Recipient_ID": tapo_id})
        db[COL_MASCOTAS].delete_one({"id_mascota": tapo_id})

    db[COL_USUARIOS].delete_one({"Id": usuario_id})

    try:
        print(f"🗑️  [MIGRATION] Datos de '{usuario_doc.get('Username', '')}' eliminados de este servidor.")
    except UnicodeEncodeError:
        print(f"[CLEANUP] Datos de '{usuario_doc.get('Username', '')}' eliminados de este servidor.")

    return {
        "success": True,
        "message": f"Datos del jugador '{usuario_doc.get('Username', '')}' eliminados.",
    }
