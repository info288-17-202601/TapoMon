"""
server/services/auth_service.py
Servicio de autenticación basado en JWT.

Justificación:
    El informe requiere autenticación en el servidor central para evitar
    suplantación de identidad. Usamos JWT porque:
    - Es stateless: el servidor no necesita guardar sesiones.
    - El token viaja en cada request (header Authorization).
    - Se firma con un secreto, garantizando integridad.
    
    El hash de password ya existe en el modelo Usuario del cliente,
    así que reutilizamos esa lógica (SHA-256).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from server.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from server.db.mongo import get_db
from server.config import COL_USUARIOS


def _hash_password(plain: str) -> str:
    """Mismo hash SHA-256 que usa el modelo Usuario del cliente."""
    return hashlib.sha256(plain.encode()).hexdigest()


def registrar_usuario(
    username: str,
    correo: str,
    password: str,
    usuario_id: str,
    tapo_id: str,
) -> dict | None:
    """
    Crea un usuario nuevo en la base de datos del servidor.

    Usa los mismos UUIDs que genera el cliente para que ambas bases
    de datos (local y servidor) compartan identificadores consistentes.

    Args:
        username:   Nombre de usuario.
        correo:     Correo electrónico.
        password:   Contraseña en texto plano (se hashea antes de guardar).
        usuario_id: UUID generado por el cliente.
        tapo_id:    UUID de la mascota, generado por el cliente.

    Returns:
        El documento del usuario creado, o None si el username ya existe.
    """
    db = get_db()

    # Verificar unicidad de username (case-insensitive)
    existing = db[COL_USUARIOS].find_one(
        {"Username": {"$regex": f"^{username}$", "$options": "i"}}
    )
    if existing is not None:
        return None

    usuario_doc = {
        "Id":       usuario_id,
        "Username": username,
        "Correo":   correo,
        "Password": _hash_password(password),
        "Tapo_ID":  tapo_id,
    }
    db[COL_USUARIOS].insert_one(usuario_doc)
    return usuario_doc


def autenticar_usuario(username: str, password: str) -> dict | None:
    """
    Verifica credenciales contra la base de datos.
    Retorna el documento del usuario si es válido, None si no.
    """
    db = get_db()
    usuario = db[COL_USUARIOS].find_one(
        {"Username": {"$regex": f"^{username}$", "$options": "i"}}
    )

    if usuario is None:
        return None

    password_hash = _hash_password(password)
    if usuario.get("Password") != password_hash:
        return None

    return usuario


def generar_token(usuario_doc: dict) -> str:
    """
    Genera un JWT firmado con los datos del usuario.
    El token contiene: usuario_id, username, y tiempo de expiración.
    """
    payload = {
        "sub": usuario_doc["Id"],
        "username": usuario_doc["Username"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verificar_token(token: str) -> dict | None:
    """
    Decodifica y valida un JWT.
    Retorna el payload si es válido, None si expiró o es inválido.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def obtener_usuario_id_desde_token(token: str) -> str | None:
    """Extrae el usuario_id (campo 'sub') del token."""
    payload = verificar_token(token)
    if payload:
        return payload.get("sub")
    return None
