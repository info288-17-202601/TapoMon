"""
server/models/schemas.py
Schemas Pydantic para validación de request/response del SyncService.

Justificación:
    Pydantic provee validación automática de tipos en FastAPI.
    Estos schemas son el "contrato" entre cliente y servidor:
    - El cliente sabe exactamente qué enviar (TapoStateUpload).
    - El servidor sabe exactamente qué devolver (ResumeStateResponse).
    Esto es equivalente a la definición de interfaces en RMI/RPC.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ================================================================== #
#  Sub-schemas (reflejan la estructura de Tapo del cliente)
# ================================================================== #

class VitalesSchema(BaseModel):
    """Signos vitales de la mascota."""
    hambre:        int = Field(ge=0, le=100, default=100)
    energia:       int = Field(ge=0, le=100, default=100)
    salud:         int = Field(ge=0, le=100, default=100)
    felicidad:     int = Field(ge=0, le=100, default=100)
    independencia: int = Field(ge=0, le=100, default=50)


class EstadisticaSchema(BaseModel):
    """Estadísticas de combate/entrenamiento."""
    vida:      int = Field(ge=0, le=100, default=100)
    fuerza:    int = Field(ge=0, le=100, default=10)
    defensa:   int = Field(ge=0, le=100, default=10)
    velocidad: int = Field(ge=0, le=100, default=10)
    tipo:      str = "Normal"


class GiftCooldownSchema(BaseModel):
    """Cooldown de regalo a un amigo."""
    friend_id:           str
    last_gift_timestamp: str


# ================================================================== #
#  Request schemas
# ================================================================== #

class TapoStateUpload(BaseModel):
    """
    Payload que envía el cliente al hacer sync_upload.
    Contiene el snapshot completo del Tapo.
    """
    id_mascota:     str
    Nombre:         str
    Vitales:        VitalesSchema
    Estadistica:    EstadisticaSchema
    Estado_Sistema: bool = False          # Al subir, siempre será IDLE
    Last_Sync:      str                   # ISO format timestamp
    Friend_List:    list[str] = []
    Gift_Cooldowns: list[GiftCooldownSchema] = []


class LoginRequest(BaseModel):
    """Credenciales de login para obtener JWT."""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """
    Payload para registrar un usuario nuevo en el servidor.

    El cliente genera los UUIDs (usuario_id, tapo_id) localmente
    para que ambas bases de datos compartan los mismos identificadores
    desde el primer momento, sin necesidad de sincronización posterior.
    """
    username:   str
    correo:     str
    password:   str
    usuario_id: str   # UUID generado por el cliente (debe coincidir con DB local)
    tapo_id:    str   # UUID de la mascota generado por el cliente


# ================================================================== #
#  Response schemas
# ================================================================== #

class SyncUploadResponse(BaseModel):
    """Respuesta al sync_upload."""
    success: bool
    message: str
    tapo_id: str


class InboxMessage(BaseModel):
    """Mensaje individual del Inbox."""
    ID_Mensaje:   str
    Sender_ID:    str
    Payload:      dict
    Timestamp:    str


class ResumeStateResponse(BaseModel):
    """
    Respuesta al resume_state.
    Contiene el estado actualizado de la mascota (post-idle)
    y los regalos/mensajes pendientes del Inbox.
    """
    success:  bool
    message:  str
    tapo:     Optional[dict] = None       # Estado completo del Tapo
    inbox:    list[InboxMessage] = []      # Mensajes pendientes


class TokenResponse(BaseModel):
    """Respuesta al login exitoso."""
    access_token: str
    token_type:   str = "bearer"
    usuario_id:   str
    username:     str


class ErrorResponse(BaseModel):
    """Respuesta genérica de error."""
    success: bool = False
    message: str
