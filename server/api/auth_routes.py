"""
server/api/auth_routes.py
Endpoints de autenticación del servidor central.

Justificación:
    El informe requiere protección de procesos y canales:
    "Para evitar que un atacante suplante la identidad de un usuario
     y altere las estadísticas de una mascota ajena, se establecen
     procesos de autenticación en el servidor central."

    Este módulo expone:
    - POST /auth/login → Retorna un JWT si las credenciales son válidas.
    - Dependency get_current_user → Extrae y valida el JWT de cada request.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional

from server.models.schemas import LoginRequest, TokenResponse, ErrorResponse, RegisterRequest
from server.services.auth_service import (
    autenticar_usuario,
    generar_token,
    verificar_token,
    registrar_usuario,
)

router = APIRouter()


# ------------------------------------------------------------------ #
#  Dependency: Extraer usuario autenticado del token
# ------------------------------------------------------------------ #

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI Dependency que valida el JWT en el header Authorization.
    Uso: cualquier endpoint protegido recibe este dependency.
    
    Header esperado: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado.")

    # Extraer token del header "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Formato de token inválido. Usar: Bearer <token>")

    token = parts[1]
    payload = verificar_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    return payload


# ------------------------------------------------------------------ #
#  Endpoints
# ------------------------------------------------------------------ #

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Autentica al usuario y retorna un JWT.
    
    El cliente usa este token en todas las llamadas subsiguientes
    al SyncService (header Authorization: Bearer <token>).
    """
    usuario_doc = autenticar_usuario(request.username, request.password)

    if usuario_doc is None:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    token = generar_token(usuario_doc)

    return TokenResponse(
        access_token=token,
        usuario_id=usuario_doc["Id"],
        username=usuario_doc["Username"],
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Registra un usuario nuevo en el servidor y retorna un JWT.

    El cliente genera los UUIDs (usuario_id, tapo_id) para garantizar
    que ambas bases de datos (local y servidor) usen los mismos IDs.

    Retorna 409 si el username ya está registrado en el servidor.
    Retorna 201 + JWT si el registro fue exitoso.
    """
    usuario_doc = registrar_usuario(
        username=request.username,
        correo=request.correo,
        password=request.password,
        usuario_id=request.usuario_id,
        tapo_id=request.tapo_id,
    )

    if usuario_doc is None:
        raise HTTPException(
            status_code=409,
            detail="El nombre de usuario ya está registrado en el servidor."
        )

    token = generar_token(usuario_doc)

    return TokenResponse(
        access_token=token,
        usuario_id=usuario_doc["Id"],
        username=usuario_doc["Username"],
    )
