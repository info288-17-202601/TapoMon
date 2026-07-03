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
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from server.config import (
    COL_USUARIOS, COL_RESET_TOKENS, COL_2FA_CODES,
    JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS,
)
from server.db.mongo import get_db


def _hash_password(plain: str) -> str:
    """Mismo hash SHA-256 que usa el modelo Usuario del cliente."""
    return hashlib.sha256(plain.encode()).hexdigest()


def registrar_usuario(
    username: str,
    correo: str,
    password: str,
    usuario_id: str,
    tapo_id: str,
) -> tuple[dict | None, str | None]:
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
        Tupla con el documento del usuario (o None si falla) y el mensaje de error (o None si éxito).
    """
    db = get_db()

    # Verificar unicidad de username y correo (case-insensitive)
    existing_username = db[COL_USUARIOS].find_one(
        {"Username": {"$regex": f"^{username}$", "$options": "i"}}
    )
    if existing_username is not None:
        return None, "El nombre de usuario ya está registrado."

    existing_correo = db[COL_USUARIOS].find_one(
        {"Correo": {"$regex": f"^{correo}$", "$options": "i"}}
    )
    if existing_correo is not None:
        return None, "El correo electrónico ya está en uso."

    usuario_doc = {
        "Id":       usuario_id,
        "Username": username,
        "Correo":   correo,
        "Password": _hash_password(password),
        "Tapo_ID":  tapo_id,
    }
    db[COL_USUARIOS].insert_one(usuario_doc)
    return usuario_doc, None


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


# ------------------------------------------------------------------ #
#  Recuperación de contraseña
# ------------------------------------------------------------------ #

RESET_TOKEN_TTL_SECONDS = 3600  # 1 hora


def crear_token_reset(correo: str) -> tuple[str, str] | None:
    """
    Crea un token de reset de contraseña para el usuario con el correo dado.

    Busca todos los usuarios con ese correo (puede haber varios si se registró
    más de una vez con el mismo email). Guarda el correo normalizado en el token
    para que el reset actualice a TODOS los que lo comparten.

    Returns:
        Tupla (token, username) si el correo existe, None si no.
    """
    db = get_db()
    # Normalizar a minúsculas para consistencia
    correo_norm = correo.strip().lower()

    usuario = db[COL_USUARIOS].find_one(
        {"Correo": {"$regex": f"^{correo_norm}$", "$options": "i"}}
    )
    if usuario is None:
        return None

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)

    # Eliminar cualquier token previo para este correo (un reset a la vez)
    db[COL_RESET_TOKENS].delete_many({"correo": correo_norm})

    db[COL_RESET_TOKENS].insert_one({
        "token":      token,
        "correo":     correo_norm,   # guardamos normalizado
        "usuario_id": usuario["Id"],
        "expires_at": expires_at,
    })

    # Asegurar que el índice TTL exista (idempotente)
    db[COL_RESET_TOKENS].create_index(
        "expires_at", expireAfterSeconds=0, background=True
    )

    return token, usuario.get("Username", "usuario")


def resetear_password(token: str, nueva_password: str) -> bool:
    """
    Valida el token de reset y actualiza la contraseña del usuario.

    Actualiza por correo (no solo por usuario_id) para cubrir el caso
    en que el mismo correo esté asociado a más de un usuario.

    Args:
        token:           Token de reset recibido en el link del email.
        nueva_password:  Nueva contraseña en texto plano (se hashea aquí).

    Returns:
        True si el reset fue exitoso, False si el token es inválido/expirado.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    doc = db[COL_RESET_TOKENS].find_one({"token": token})
    if doc is None:
        print(f"  ⚠️  reset_password: token no encontrado")
        return False

    # Verificar expiración manual
    expires_at = doc.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            db[COL_RESET_TOKENS].delete_one({"token": token})
            print(f"  ⚠️  reset_password: token expirado")
            return False

    correo = doc.get("correo", "")
    nuevo_hash = _hash_password(nueva_password)

    # Actualizar TODOS los usuarios que tengan ese correo (case-insensitive)
    # Esto evita el bug donde hay múltiples cuentas con el mismo email
    resultado = db[COL_USUARIOS].update_many(
        {"Correo": {"$regex": f"^{correo}$", "$options": "i"}},
        {"$set": {"Password": nuevo_hash}},
    )
    print(f"  ✅  reset_password: {resultado.modified_count} usuario(s) actualizados para correo={correo}")

    # Consumir el token (un solo uso)
    db[COL_RESET_TOKENS].delete_one({"token": token})

    return True


# ------------------------------------------------------------------ #
#  Verificación de dos pasos (2FA via email)
# ------------------------------------------------------------------ #

_2FA_TTL_SECONDS = 600   # 10 minutos


def _hint_correo(correo: str) -> str:
    """Oculta parte del correo para mostrarlo al usuario sin revelar todo.
    Ejemplo: yiyo.zx@hotmail.com → y******@h******.com
    """
    try:
        local, _, domain = correo.partition("@")
        hint_local = local[0] + "*" * max(1, len(local) - 1)
        parts = domain.split(".")
        hint_domain = parts[0][0] + "*" * max(1, len(parts[0]) - 1)
        ext = "." + ".".join(parts[1:])
        return f"{hint_local}@{hint_domain}{ext}"
    except Exception:
        return "****@****.***"


def crear_sesion_2fa(usuario_doc: dict) -> tuple[str, str, str]:
    """
    Genera un código de 6 dígitos para 2FA, lo almacena en MongoDB
    con TTL de 10 minutos y retorna (session_id, codigo, correo_hint).

    El `usuario_doc` completo se guarda para poder generar el JWT
    directamente al verificar, sin otra consulta.
    """
    db = get_db()
    session_id = str(uuid.uuid4())
    codigo     = f"{random.randint(0, 999_999):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_2FA_TTL_SECONDS)

    # Un solo intento activo por usuario a la vez
    db[COL_2FA_CODES].delete_many({"usuario_id": usuario_doc["Id"]})

    # Guardar una copia del doc sin _id (no es serializable)
    doc_limpio = {k: v for k, v in usuario_doc.items() if k != "_id"}

    db[COL_2FA_CODES].insert_one({
        "session_id":  session_id,
        "codigo":      codigo,
        "usuario_id":  usuario_doc["Id"],
        "usuario_doc": doc_limpio,
        "expires_at":  expires_at,
    })

    # Índice TTL (idempotente)
    db[COL_2FA_CODES].create_index(
        "expires_at", expireAfterSeconds=0, background=True
    )

    correo_hint = _hint_correo(usuario_doc.get("Correo", ""))
    return session_id, codigo, correo_hint


def verificar_2fa_codigo(session_id: str, codigo: str) -> dict | None:
    """
    Valida el session_id y el código de 6 dígitos.

    Si son correctos, consume el código (un solo uso) y retorna
    el usuario_doc original para que se pueda generar el JWT.
    Retorna None si el código es inválido o expiró.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    doc = db[COL_2FA_CODES].find_one({"session_id": session_id})
    if doc is None:
        print("  ⚠️  2FA: session_id no encontrado")
        return None

    expires_at = doc.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            db[COL_2FA_CODES].delete_one({"session_id": session_id})
            print("  ⚠️  2FA: código expirado")
            return None

    if doc.get("codigo") != codigo:
        print(f"  ⚠️  2FA: código incorrecto (esperado {doc.get('codigo')}, recibido {codigo})")
        return None

    # Consumir (un solo uso)
    db[COL_2FA_CODES].delete_one({"session_id": session_id})
    print(f"  ✅  2FA verificado para usuario_id={doc.get('usuario_id')}")
    return doc.get("usuario_doc")
