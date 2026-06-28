from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from server.config import COL_INBOX, COL_MASCOTAS, COL_USUARIOS
from server.db.mongo import get_db
from server.services.sync_service import normalizar_friend_list


def _obtener_tapo_del_usuario(db, usuario_id: str) -> tuple[dict | None, dict | None]:
    """Devuelve el usuario y su Tapo asociado a partir del usuario_id."""
    usuario_doc = db[COL_USUARIOS].find_one({"Id": usuario_id})
    if usuario_doc is None:
        return None, None

    tapo_id = usuario_doc.get("Tapo_ID", "")
    if not tapo_id:
        return usuario_doc, None

    tapo_doc = db[COL_MASCOTAS].find_one({"id_mascota": tapo_id})
    return usuario_doc, tapo_doc


def _obtener_informacion_amigo(db, friend_id: str) -> dict | None:
    """Obtiene datos públicos del amigo (usuario y Tapo) a partir de su id de mascota."""
    if not friend_id:
        return None

    amigo_doc = db[COL_USUARIOS].find_one({"Tapo_ID": friend_id})
    if amigo_doc is None:
        return None

    tapo_doc = db[COL_MASCOTAS].find_one({"id_mascota": friend_id})
    if tapo_doc is None:
        return None

    return {
        "friend_id": friend_id,
        "username": amigo_doc.get("Username"),
        "tapo_id": friend_id,
        "tapo_name": tapo_doc.get("Nombre"),
    }


def get_social_state(usuario_id: str) -> dict:
    """Devuelve la lista de amigos y los cooldowns del Tapo del usuario."""
    db = get_db()
    _, tapo_doc = _obtener_tapo_del_usuario(db, usuario_id)
    if tapo_doc is None:
        return {
            "success": False,
            "message": "No se encontró el Tapo del usuario.",
            "friends": [],
            "gift_cooldowns": [],
        }

    friends = []
    for friend_id in normalizar_friend_list(tapo_doc.get("Friend_List")):
        info = _obtener_informacion_amigo(db, friend_id)
        if info is not None:
            friends.append(info)

    cooldowns = tapo_doc.get("Gift_Cooldowns") or []
    return {
        "success": True,
        "message": "Estado social recuperado correctamente.",
        "friends": friends,
        "gift_cooldowns": cooldowns,
    }


def add_friend(usuario_id: str, friend_id: str) -> dict:
    """Agrega un amigo al Tapo del usuario."""
    friend_id = str(friend_id or "").strip()
    if not friend_id:
        return {"success": False, "message": "Debes indicar un amigo válido."}

    db = get_db()
    _, tapo_doc = _obtener_tapo_del_usuario(db, usuario_id)
    if tapo_doc is None:
        return {"success": False, "message": "No se encontró el Tapo del usuario."}

    if friend_id == tapo_doc.get("id_mascota"):
        return {"success": False, "message": "No puedes agregarte a ti mismo como amigo."}

    if db[COL_MASCOTAS].find_one({"id_mascota": friend_id}) is None:
        return {"success": False, "message": "El amigo indicado no existe."}

    friends = normalizar_friend_list(tapo_doc.get("Friend_List"))
    if friend_id not in friends:
        friends.append(friend_id)

    db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo_doc["id_mascota"]},
        {"$set": {
            "Friend_List": friends,
            "Last_Sync": datetime.now().isoformat(),
        }},
    )

    return {
        "success": True,
        "message": "Amigo agregado correctamente.",
        "friends": get_social_state(usuario_id)["friends"],
    }


def remove_friend(usuario_id: str, friend_id: str) -> dict:
    """Quita un amigo del Tapo del usuario."""
    friend_id = str(friend_id or "").strip()
    if not friend_id:
        return {"success": False, "message": "Debes indicar un amigo válido."}

    db = get_db()
    _, tapo_doc = _obtener_tapo_del_usuario(db, usuario_id)
    if tapo_doc is None:
        return {"success": False, "message": "No se encontró el Tapo del usuario."}

    friends = normalizar_friend_list(tapo_doc.get("Friend_List"))
    if friend_id in friends:
        friends.remove(friend_id)

    db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo_doc["id_mascota"]},
        {"$set": {
            "Friend_List": friends,
            "Last_Sync": datetime.now().isoformat(),
        }},
    )

    return {
        "success": True,
        "message": "Amigo quitado correctamente.",
        "friends": get_social_state(usuario_id)["friends"],
    }


def send_gift(usuario_id: str, friend_id: str, gift_type: str = "comida", message: str | None = None) -> dict:
    """Envía un regalo a un amigo del Tapo del usuario."""
    friend_id = str(friend_id or "").strip()
    if not friend_id:
        return {"success": False, "message": "Debes indicar un amigo válido."}

    db = get_db()
    _, tapo_doc = _obtener_tapo_del_usuario(db, usuario_id)
    if tapo_doc is None:
        return {"success": False, "message": "No se encontró el Tapo del usuario."}

    friends = normalizar_friend_list(tapo_doc.get("Friend_List"))
    if friend_id not in friends:
        return {"success": False, "message": "Solo puedes enviar regalos a tus amigos."}

    if db[COL_MASCOTAS].find_one({"id_mascota": friend_id}) is None:
        return {"success": False, "message": "El amigo indicado no existe."}

    msg_id = str(uuid4())
    timestamp = datetime.now().isoformat()
    payload = {
        "tipo": "regalo",
        "gift_type": gift_type,
        "sender_id": tapo_doc.get("id_mascota"),
        "sender_name": tapo_doc.get("Nombre"),
    }
    if message:
        payload["message"] = message

    db[COL_INBOX].insert_one({
        "ID_Mensaje": msg_id,
        "Recipient_ID": friend_id,
        "Sender_ID": tapo_doc.get("id_mascota"),
        "Payload": payload,
        "Status": False,
        "Timestamp": timestamp,
    })

    cooldowns = tapo_doc.get("Gift_Cooldowns") or []
    cooldowns = [entry for entry in cooldowns if entry.get("friend_id") != friend_id]
    cooldowns.append({
        "friend_id": friend_id,
        "last_gift_timestamp": timestamp,
    })

    db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo_doc["id_mascota"]},
        {"$set": {
            "Gift_Cooldowns": cooldowns,
            "Last_Sync": datetime.now().isoformat(),
        }},
    )

    return {
        "success": True,
        "message": "Regalo enviado correctamente.",
        "gift_id": msg_id,
    }
