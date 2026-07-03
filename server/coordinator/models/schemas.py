"""
server/coordinator/models/schemas.py
Schemas Pydantic del Coordinador Central.

Define los contratos de request/response para los endpoints
del coordinador: asignación, resolución, migración y listado de servidores.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


# ================================================================== #
#  Request schemas
# ================================================================== #

class AssignRequest(BaseModel):
    """Solicitud para asignar un jugador nuevo a un servidor regional."""
    usuario_id: str
    username:   str
    correo:     str
    target_region: Optional[str] = None


class ResolveRequest(BaseModel):
    """No se usa como body — el usuario_id va en la URL."""
    pass


class MigrateRequest(BaseModel):
    """Solicitud para migrar un jugador a otro servidor."""
    usuario_id:    str
    target_server: str     # Nombre del servidor destino (ej: "sur")


# ================================================================== #
#  Response schemas
# ================================================================== #

class ServerInfo(BaseModel):
    """Información de un servidor regional."""
    name:         str
    url:          str
    player_count: int = 0


class AssignResponse(BaseModel):
    """Respuesta a la asignación de servidor."""
    success:       bool
    message:       str
    server_region: Optional[str] = None
    server_url:    Optional[str] = None


class ResolveResponse(BaseModel):
    """Respuesta a la resolución de servidor de un jugador."""
    success:       bool
    message:       str
    server_region: Optional[str] = None
    server_url:    Optional[str] = None


class MigrateResponse(BaseModel):
    """Respuesta a la migración de servidor."""
    success:       bool
    message:       str
    old_server:    Optional[str] = None
    new_server:    Optional[str] = None
    new_server_url: Optional[str] = None


class ServerListResponse(BaseModel):
    """Respuesta con la lista de servidores disponibles."""
    success: bool
    servers: list[ServerInfo] = Field(default_factory=list)
