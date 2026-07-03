"""
network/config.py
Configuración de red del cliente TapoMon.

Justificación:
    Centraliza la URL del servidor, timeouts, y la región asignada
    para que sean fácilmente configurables. Usa variables de entorno
    para permitir apuntar a diferentes servidores (dev, staging, prod).

    En el sistema multi-servidor, el cliente necesita saber su región
    para enviar el header X-Server-Region en cada request.
    La región se resuelve automáticamente al hacer login/register
    a través del coordinador.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()  # Cargar variables desde el archivo .env si existe

# URL base del servidor central (apunta a Nginx en producción)
SERVER_URL = os.getenv("TAPOMON_SERVER_URL", "http://localhost:8000")

# Timeout para requests HTTP (segundos)
REQUEST_TIMEOUT = int(os.getenv("TAPOMON_REQUEST_TIMEOUT", "10"))

# Región del servidor asignada al jugador.
# Se establece automáticamente al hacer login/register vía el coordinador.
# Se puede forzar manualmente para testing.
SERVER_REGION = os.getenv("TAPOMON_SERVER_REGION", "")
