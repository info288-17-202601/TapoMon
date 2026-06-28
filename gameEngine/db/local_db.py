"""
db/local_db.py
Capa de acceso a datos usando MongoDB (pymongo).
Las colecciones reflejan exactamente el esquema del informe:
  - usuarios   → Tabla Usuario
  - mascotas   → Tabla Tapo
  - inbox      → Tabla Inbox
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime

from db.connection import get_db
from models.usuario import Usuario
from models.tapo import Tapo, Vitales, Estadistica, TipoTapo


# ------------------------------------------------------------------ #
#  Colecciones (nombres fijos, igual que en el informe)
# ------------------------------------------------------------------ #
COL_USUARIOS = "Usuarios"
COL_MASCOTAS = "Tapo"
COL_INBOX    = "Inbox"


def _col(nombre: str):
    """Shortcut para obtener una colección."""
    return get_db()[nombre]


# ================================================================== #
#  USUARIOS
# ================================================================== #

def guardar_usuario(usuario: Usuario) -> None:
    """Inserta o actualiza un usuario (upsert por Id)."""
    _col(COL_USUARIOS).update_one(
        {"Id": usuario.id},
        {"$set": usuario.to_dict()},
        upsert=True,
    )


def buscar_usuario_por_username(username: str) -> Usuario | None:
    doc = _col(COL_USUARIOS).find_one(
        {"Username": {"$regex": f"^{username}$", "$options": "i"}}
    )
    return Usuario.from_dict(doc) if doc else None


def buscar_usuario_por_id(uid: str) -> Usuario | None:
    doc = _col(COL_USUARIOS).find_one({"Id": uid})
    return Usuario.from_dict(doc) if doc else None


# ================================================================== #
#  MASCOTAS (Tapo)
# ================================================================== #

def guardar_tapo(tapo: Tapo) -> None:
    """Inserta o actualiza una mascota (upsert por id_mascota)."""
    data = tapo.to_dict()
    # Last_Sync guardado como datetime nativo de MongoDB (no string)
    data["Last_Sync"] = tapo.last_sync
    _col(COL_MASCOTAS).update_one(
        {"id_mascota": tapo.id_mascota},
        {"$set": data},
        upsert=True,
    )


def cargar_tapo(tapo_id: str) -> Tapo | None:
    doc = _col(COL_MASCOTAS).find_one({"id_mascota": tapo_id})
    if doc is None:
        return None
    # MongoDB devuelve Last_Sync como datetime; normalizar para from_dict
    if isinstance(doc.get("Last_Sync"), datetime):
        doc["Last_Sync"] = doc["Last_Sync"].isoformat()
    return Tapo.from_dict(doc)


def buscar_tapos_por_texto(texto: str) -> list[dict]:
    """Busca mascotas por nombre o por username del propietario."""
    query = str(texto or "").strip()
    if not query:
        return []

    pattern = {"$regex": re.escape(query), "$options": "i"}
    matches: list[dict] = []
    seen_ids: set[str] = set()

    for tapo_doc in _col(COL_MASCOTAS).find({"Nombre": pattern}):
        tapo_id = tapo_doc.get("id_mascota")
        if not tapo_id or tapo_id in seen_ids:
            continue
        seen_ids.add(tapo_id)
        usuario_doc = _col(COL_USUARIOS).find_one({"Tapo_ID": tapo_id})
        matches.append({
            "id_mascota": tapo_id,
            "nombre": tapo_doc.get("Nombre"),
            "username": usuario_doc.get("Username") if usuario_doc else None,
        })

    for usuario_doc in _col(COL_USUARIOS).find({"Username": pattern}):
        tapo_id = usuario_doc.get("Tapo_ID")
        if not tapo_id or tapo_id in seen_ids:
            continue
        seen_ids.add(tapo_id)
        tapo_doc = _col(COL_MASCOTAS).find_one({"id_mascota": tapo_id})
        if tapo_doc is None:
            continue
        matches.append({
            "id_mascota": tapo_id,
            "nombre": tapo_doc.get("Nombre"),
            "username": usuario_doc.get("Username"),
        })

    return matches


# ================================================================== #
#  INBOX (mensajes entre mascotas — Tabla Inbox del informe)
# ================================================================== #

def enviar_mensaje(recipient_id: str, sender_id: str, payload: dict) -> str:
    """Inserta un mensaje en la bandeja de entrada del destinatario."""
    msg_id = str(uuid.uuid4())
    _col(COL_INBOX).insert_one({
        "ID_Mensaje":   msg_id,
        "Recipient_ID": recipient_id,
        "Sender_ID":    sender_id,
        "Payload":      payload,
        "Status":       False,          # claimed: false
        "Timestamp":    datetime.now(),
    })
    return msg_id


def leer_mensajes(recipient_id: str) -> list[dict]:
    """Retorna todos los mensajes no reclamados de un destinatario."""
    cursor = _col(COL_INBOX).find(
        {"Recipient_ID": recipient_id, "Status": False}
    )
    return list(cursor)


def marcar_mensaje_reclamado(msg_id: str) -> None:
    _col(COL_INBOX).update_one(
        {"ID_Mensaje": msg_id},
        {"$set": {"Status": True}},
    )


# ================================================================== #
#  REGISTRO INICIAL
# ================================================================== #

def registrar_nuevo_usuario(
    username: str,
    correo: str,
    password: str,
    nombre_tapo: str,
    tipo_tapo: TipoTapo,
) -> tuple[Usuario, Tapo]:
    """Crea usuario y mascota nuevos, los persiste en MongoDB."""
    uid     = str(uuid.uuid4())
    tapo_id = str(uuid.uuid4())

    usuario = Usuario(id=uid, username=username, correo=correo, tapo_id=tapo_id)
    usuario.set_password(password)

    tapo = Tapo(
        id_mascota  = tapo_id,
        nombre      = nombre_tapo,
        estadistica = Estadistica(tipo=tipo_tapo),
    )

    guardar_usuario(usuario)
    guardar_tapo(tapo)

    # Crear índices útiles la primera vez (idempotente)
    _crear_indices()

    return usuario, tapo


def registrar_nueva_mascota(
    usuario: Usuario,
    nombre_tapo: str,
    tipo_tapo: TipoTapo,
) -> Tapo:
    """Crea una nueva mascota para un usuario existente."""
    tapo_id = str(uuid.uuid4())

    tapo = Tapo(
        id_mascota  = tapo_id,
        nombre      = nombre_tapo,
        estadistica = Estadistica(tipo=tipo_tapo),
    )

    usuario.tapo_id = tapo_id
    guardar_usuario(usuario)
    guardar_tapo(tapo)

    _crear_indices()
    return tapo


def _crear_indices() -> None:
    """
    Crea índices en MongoDB para consultas frecuentes.
    Se puede llamar varias veces sin problema (idempotente).
    """
    db = get_db()
    db[COL_USUARIOS].create_index("Username", unique=True)
    db[COL_USUARIOS].create_index("Id",       unique=True)
    db[COL_MASCOTAS].create_index("id_mascota", unique=True)
    db[COL_INBOX].create_index([("Recipient_ID", 1), ("Status", 1)])
