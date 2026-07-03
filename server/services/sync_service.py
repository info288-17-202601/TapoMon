"""
server/services/sync_service.py
Lógica de negocio del SyncService (Handover API).

Justificación:
    Este es el componente central descrito en el informe:
    "Componente que mantiene comunicación entre el servidor y el usuario,
     el cual permite mantener actualizada las características de la mascota."

    Implementa las dos operaciones fundamentales:
    - sync_upload: El cliente envía un "snapshot" al desconectarse.
      El servidor lo guarda en el Pet State Store (MongoDB).
    - resume_state: El cliente solicita el estado actualizado al reconectarse.
      El servidor devuelve el estado post-simulación IDLE + inbox.

    La separación de la lógica de negocio en un servicio independiente
    (fuera de las rutas) permite testearla unitariamente sin levantar FastAPI.
"""
from __future__ import annotations

from datetime import datetime

from server.db.mongo import get_db
from server.config import COL_MASCOTAS, COL_USUARIOS, COL_INBOX


def normalizar_friend_list(friend_list: object | None) -> list[str]:
    """Convierte la Friend_List del Tapo a una lista limpia de IDs de amigos."""
    if friend_list is None:
        return []

    if isinstance(friend_list, str):
        values = [friend_list]
    elif isinstance(friend_list, (list, tuple, set)):
        values = list(friend_list)
    else:
        values = [friend_list]

    friends: list[str] = []
    seen: set[str] = set()

    for item in values:
        if item is None:
            continue

        if isinstance(item, str):
            candidate = item.strip()
        else:
            candidate = str(item).strip()

        if not candidate or candidate in seen:
            continue

        seen.add(candidate)
        friends.append(candidate)

    return friends


def sync_upload(tapo_id: str, tapo_state: dict) -> bool:
    """
    Recibe el "Snapshot" del cliente y lo guarda en el Pet State Store.
    
    Flujo:
        1. El cliente cierra sesión.
        2. El cliente envía el estado completo del Tapo via HTTP POST.
        3. Este método guarda/actualiza el documento en MongoDB.
        4. El Tapo queda marcado como IDLE (Estado_Sistema: false).
    
    Args:
        tapo_id:    Identificador único de la mascota.
        tapo_state: Diccionario con el estado completo del Tapo.
    
    Returns:
        True si se guardó correctamente, False si hubo error.
    """
    db = get_db()

    state_to_store = dict(tapo_state)

    # Asegurar que el estado se marca como IDLE al subir y que la lista de amigos
    # se guarde como una lista limpia de IDs.
    state_to_store["Estado_Sistema"] = False
    state_to_store["Last_Sync"] = datetime.now().isoformat()
    
    # Filtrar Friend_List para contener solo IDs que existen en el servidor regional
    raw_friends = normalizar_friend_list(state_to_store.get("Friend_List"))
    validated_friends = []
    if raw_friends:
        # Consultar la existencia de estos IDs en la base de datos local (este servidor)
        existing_mascotas = db[COL_MASCOTAS].find(
            {"id_mascota": {"$in": raw_friends}},
            {"id_mascota": 1}
        )
        existing_ids = {doc["id_mascota"] for doc in existing_mascotas}
        validated_friends = [fid for fid in raw_friends if fid in existing_ids]
    state_to_store["Friend_List"] = validated_friends

    result = db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo_id},
        {"$set": state_to_store},
        upsert=True,
    )

    return result.acknowledged


def resume_state(usuario_id: str) -> dict | None:
    """
    Descarga el estado actualizado de la mascota y los mensajes pendientes.
    
    Flujo:
        1. El cliente inicia sesión.
        2. El cliente solicita el estado actual via HTTP GET.
        3. Este método busca el usuario → obtiene tapo_id → carga el Tapo.
        4. Recopila mensajes del Inbox no reclamados.
        5. Marca el Tapo como ACTIVE (Estado_Sistema: true).
        6. Retorna estado + inbox.
    
    Args:
        usuario_id: Identificador único del usuario.
    
    Returns:
        dict con {tapo: {...}, inbox: [...]} o None si no existe.
    """
    db = get_db()

    # Buscar usuario
    usuario_doc = db[COL_USUARIOS].find_one({"Id": usuario_id})
    if usuario_doc is None:
        return None

    tapo_id = usuario_doc.get("Tapo_ID", "")
    if not tapo_id:
        return None

    # Cargar estado del Tapo
    tapo_doc = db[COL_MASCOTAS].find_one({"id_mascota": tapo_id})
    if tapo_doc is None:
        return None

    tapo_doc["Friend_List"] = normalizar_friend_list(tapo_doc.get("Friend_List"))

    # Marcar como ACTIVE al descargar
    db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo_id},
        {"$set": {
            "Estado_Sistema": True,
            "Last_Sync": datetime.now().isoformat(),
        }}
    )
    tapo_doc["Estado_Sistema"] = True
    tapo_doc["Last_Sync"] = datetime.now().isoformat()

    # Limpiar _id de MongoDB (no es serializable a JSON)
    tapo_doc.pop("_id", None)

    # Recopilar mensajes del Inbox
    inbox_cursor = db[COL_INBOX].find(
        {"Recipient_ID": tapo_id, "Status": False}
    )
    inbox = []
    for msg in inbox_cursor:
        msg.pop("_id", None)
        # Normalizar Timestamp a string si es datetime
        if isinstance(msg.get("Timestamp"), datetime):
            msg["Timestamp"] = msg["Timestamp"].isoformat()
        inbox.append(msg)

    return {
        "tapo": tapo_doc,
        "inbox": inbox,
    }


def verificar_propietario(usuario_id: str, tapo_id: str) -> bool:
    """
    Verifica que el tapo_id pertenece al usuario_id.
    Previene que un usuario suba el estado de una mascota ajena.
    Si el tapo_id no pertenece a nadie, se asume que el usuario
    está reemplazando a un Tapo muerto y se actualiza su Tapo_ID.
    """
    db = get_db()
    usuario_doc = db[COL_USUARIOS].find_one({"Id": usuario_id})
    if usuario_doc is None:
        return False
        
    current_tapo_id = usuario_doc.get("Tapo_ID")
    if current_tapo_id == tapo_id:
        return True
        
    # Verificar si alguien más ya es dueño de este Tapo
    otro_dueno = db[COL_USUARIOS].find_one({"Tapo_ID": tapo_id, "Id": {"$ne": usuario_id}})
    if otro_dueno is not None:
        return False
        
    # Si nadie más lo tiene, es un Tapo nuevo para este usuario (reemplazo)
    db[COL_USUARIOS].update_one({"Id": usuario_id}, {"$set": {"Tapo_ID": tapo_id}})
    return True
