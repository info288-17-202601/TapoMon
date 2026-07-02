"""
network/session_manager.py
Gestión de sesión persistente local para TapoMon.

Justificación:
    Guarda el JWT y los datos del usuario en un archivo JSON local
    para que el juego recuerde quién está logueado incluso después
    de cerrar la ventana. La sesión solo se borra explícitamente
    cuando el usuario presiona "Salir" en el menú.

    El archivo se guarda junto al script principal del juego.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


# Ruta del archivo de sesión: directorio raíz del proyecto (donde está main_pygame.py)
_SESSION_FILE = Path(__file__).parent.parent / ".tapomon_session.json"

# Horas de validez del JWT (debe coincidir con JWT_EXPIRATION_HOURS del servidor)
_TOKEN_TTL_HOURS = 24


def save_session(auth_data: dict) -> None:
    """
    Guarda los datos de autenticación en disco.

    Args:
        auth_data: Dict con access_token, usuario_id, username, correo, tapo_id.
    """
    try:
        now = datetime.now(timezone.utc)
        payload = {
            "access_token": auth_data.get("access_token", ""),
            "usuario_id":   auth_data.get("usuario_id", ""),
            "username":     auth_data.get("username", ""),
            "correo":       auth_data.get("correo", ""),
            "tapo_id":      auth_data.get("tapo_id", ""),
            "saved_at":     now.isoformat(),
        }
        _SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  💾  Sesión guardada para {payload['username']}")
    except Exception as e:
        print(f"  ⚠️  No se pudo guardar la sesión: {e}")


def load_session() -> dict | None:
    """
    Carga la sesión guardada si existe y aún no expiró.

    Returns:
        Dict con los datos del usuario o None si no hay sesión válida.
    """
    try:
        if not _SESSION_FILE.exists():
            return None

        data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))

        # Verificar que no haya expirado
        saved_at = datetime.fromisoformat(data.get("saved_at", ""))
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_hours = (now - saved_at).total_seconds() / 3600

        if age_hours >= _TOKEN_TTL_HOURS:
            print("  ⚠️  Sesión expirada. Inicia sesión nuevamente.")
            clear_session()
            return None

        if not data.get("access_token") or not data.get("usuario_id"):
            return None

        print(f"  🔓  Sesión activa: {data.get('username')} "
              f"({int((_TOKEN_TTL_HOURS - age_hours) * 60)} min restantes)")
        return data

    except Exception as e:
        print(f"  ⚠️  Error al leer sesión guardada: {e}")
        return None


def clear_session() -> None:
    """Elimina la sesión guardada (llamar solo en logout explícito)."""
    try:
        if _SESSION_FILE.exists():
            _SESSION_FILE.unlink()
            print("  🔒  Sesión cerrada.")
    except Exception as e:
        print(f"  ⚠️  No se pudo borrar la sesión: {e}")


def session_exists() -> bool:
    """Retorna True si hay un archivo de sesión válido en disco."""
    return load_session() is not None
