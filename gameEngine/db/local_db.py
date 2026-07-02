"""
db/local_db.py
Capa de acceso a datos usando un archivo local de texto cifrado.
Reemplaza a MongoDB en el cliente, manteniendo las mismas firmas
para no romper el resto del código del juego.
"""
from __future__ import annotations
import os
import json
import uuid
from datetime import datetime
import base64

from models.usuario import Usuario
from models.tapo import Tapo, Vitales, Estadistica, TipoTapo

# Archivo donde se guardará el estado
SAVE_FILE = "tapo_save.enc"
XOR_KEY = b"TapoMonLocalSaveKey2026"

class _FileDB:
    def __init__(self, filename: str):
        self.filename = filename
        self.data = {
            "Usuarios": [],
            "Tapo": [],
            "Inbox": []
        }
        self.load()

    def _encrypt(self, text: str) -> bytes:
        encoded = text.encode("utf-8")
        xored = bytes(encoded[i] ^ XOR_KEY[i % len(XOR_KEY)] for i in range(len(encoded)))
        return base64.b64encode(xored)

    def _decrypt(self, b64_bytes: bytes) -> str:
        xored = base64.b64decode(b64_bytes)
        decoded = bytes(xored[i] ^ XOR_KEY[i % len(XOR_KEY)] for i in range(len(xored)))
        return decoded.decode("utf-8")

    def load(self):
        if not os.path.exists(self.filename):
            self.save()
            return
        
        try:
            with open(self.filename, "rb") as f:
                content = f.read()
                if content:
                    json_text = self._decrypt(content)
                    self.data = json.loads(json_text)
        except Exception as e:
            print(f"Error cargando guardado local: {e}")
            # Si se corrompe, reiniciamos memoria (en prod tal vez queramos backup)
            pass

    def save(self):
        try:
            json_text = json.dumps(self.data)
            encrypted = self._encrypt(json_text)
            with open(self.filename, "wb") as f:
                f.write(encrypted)
        except Exception as e:
            print(f"Error guardando partida local: {e}")

_db_instance = _FileDB(SAVE_FILE)


# ================================================================== #
#  USUARIOS
# ================================================================== #

def guardar_usuario(usuario: Usuario) -> None:
    data = usuario.to_dict()
    for idx, u in enumerate(_db_instance.data["Usuarios"]):
        if u.get("Id") == usuario.id:
            _db_instance.data["Usuarios"][idx] = data
            _db_instance.save()
            return
    _db_instance.data["Usuarios"].append(data)
    _db_instance.save()


def buscar_usuario_por_username(username: str) -> Usuario | None:
    username_lower = username.lower()
    for u in _db_instance.data["Usuarios"]:
        if u.get("Username", "").lower() == username_lower:
            return Usuario.from_dict(u)
    return None


def buscar_usuario_por_id(uid: str) -> Usuario | None:
    for u in _db_instance.data["Usuarios"]:
        if u.get("Id") == uid:
            return Usuario.from_dict(u)
    return None


# ================================================================== #
#  MASCOTAS (Tapo)
# ================================================================== #

def guardar_tapo(tapo: Tapo) -> None:
    data = tapo.to_dict()
    # Asegurar que Last_Sync sea string para JSON
    data["Last_Sync"] = tapo.last_sync.isoformat() if isinstance(tapo.last_sync, datetime) else tapo.last_sync
    for idx, t in enumerate(_db_instance.data["Tapo"]):
        if t.get("id_mascota") == tapo.id_mascota:
            _db_instance.data["Tapo"][idx] = data
            _db_instance.save()
            return
    _db_instance.data["Tapo"].append(data)
    _db_instance.save()


def cargar_tapo(tapo_id: str) -> Tapo | None:
    for t in _db_instance.data["Tapo"]:
        if t.get("id_mascota") == tapo_id:
            # Si guardamos Last_Sync como isoformat, from_dict lo manejará
            return Tapo.from_dict(t)
    return None


def buscar_tapos_por_texto(texto: str) -> list[dict]:
    query = str(texto or "").strip().lower()
    if not query:
        return []

    matches = []
    seen_ids = set()

    # Buscar por nombre del Tapo
    for t in _db_instance.data["Tapo"]:
        if query in str(t.get("Nombre", "")).lower():
            t_id = t.get("id_mascota")
            if not t_id or t_id in seen_ids:
                continue
            seen_ids.add(t_id)
            # Buscar dueño
            username = None
            for u in _db_instance.data["Usuarios"]:
                if u.get("Tapo_ID") == t_id:
                    username = u.get("Username")
                    break
            matches.append({
                "id_mascota": t_id,
                "nombre": t.get("Nombre"),
                "username": username,
            })

    # Buscar por nombre del dueño
    for u in _db_instance.data["Usuarios"]:
        if query in str(u.get("Username", "")).lower():
            t_id = u.get("Tapo_ID")
            if not t_id or t_id in seen_ids:
                continue
            seen_ids.add(t_id)
            
            nombre_tapo = None
            for t in _db_instance.data["Tapo"]:
                if t.get("id_mascota") == t_id:
                    nombre_tapo = t.get("Nombre")
                    break
            
            if nombre_tapo:
                matches.append({
                    "id_mascota": t_id,
                    "nombre": nombre_tapo,
                    "username": u.get("Username"),
                })

    return matches


# ================================================================== #
#  INBOX
# ================================================================== #

def enviar_mensaje(recipient_id: str, sender_id: str, payload: dict) -> str:
    msg_id = str(uuid.uuid4())
    msg = {
        "ID_Mensaje":   msg_id,
        "Recipient_ID": recipient_id,
        "Sender_ID":    sender_id,
        "Payload":      payload,
        "Status":       False,
        "Timestamp":    datetime.now().isoformat(),
    }
    _db_instance.data["Inbox"].append(msg)
    _db_instance.save()
    return msg_id


def leer_mensajes(recipient_id: str) -> list[dict]:
    return [
        m for m in _db_instance.data["Inbox"]
        if m.get("Recipient_ID") == recipient_id and not m.get("Status", False)
    ]


def marcar_mensaje_reclamado(msg_id: str) -> None:
    for m in _db_instance.data["Inbox"]:
        if m.get("ID_Mensaje") == msg_id:
            m["Status"] = True
    _db_instance.save()


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
    return usuario, tapo


def registrar_nueva_mascota(
    usuario: Usuario,
    nombre_tapo: str,
    tipo_tapo: TipoTapo,
) -> Tapo:
    tapo_id = str(uuid.uuid4())

    tapo = Tapo(
        id_mascota  = tapo_id,
        nombre      = nombre_tapo,
        estadistica = Estadistica(tipo=tipo_tapo),
    )

    usuario.tapo_id = tapo_id
    guardar_usuario(usuario)
    guardar_tapo(tapo)
    return tapo


def _crear_indices() -> None:
    """No-op: los índices no son necesarios en el archivo local cifrado."""
    pass
