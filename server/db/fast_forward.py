"""
server/db/fast_forward.py
Script utilitario de viaje en el tiempo para TapoMon.
Resta horas a Last_Sync para simular el paso del tiempo y forzar degradaciones.
"""
from __future__ import annotations

import sys
import os
# Agregar el directorio padre al PATH de python para resolver 'server'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from datetime import datetime, timedelta

from server.config import COL_MASCOTAS
from server.db.mongo import get_db


def safe_print(emoji_text: str, fallback_text: str) -> None:
    """Imprime el texto con emoji, si hay un error de codificación usa el fallback sin emojis."""
    try:
        print(emoji_text)
    except UnicodeEncodeError:
        print(fallback_text)


def fast_forward_tapo(tapo_identifier: str, hours: float) -> bool:
    """
    Resta N horas a la fecha de sincronización de la mascota.
    
    Args:
        tapo_identifier: ID o Nombre de la mascota.
        hours: Cantidad de horas a retroceder (viaje en el tiempo).
        
    Returns:
        True si se modificó correctamente, False de lo contrario.
    """
    db = get_db()
    
    # Buscar por id_mascota o por Nombre
    tapo = db[COL_MASCOTAS].find_one({"id_mascota": tapo_identifier})
    if not tapo:
        tapo = db[COL_MASCOTAS].find_one({"Nombre": tapo_identifier})
        
    if not tapo:
        safe_print(
            f"❌  [FAST-FORWARD] No se encontró mascota con ID o Nombre: '{tapo_identifier}'",
            f"[FAST-FORWARD] No se encontró mascota con ID o Nombre: '{tapo_identifier}'"
        )
        return False
        
    last_sync_str = tapo.get("Last_Sync")
    try:
        last_sync = datetime.fromisoformat(last_sync_str)
    except (ValueError, TypeError):
        last_sync = datetime.now()
        
    nuevo_sync = last_sync - timedelta(hours=hours)
    
    db[COL_MASCOTAS].update_one(
        {"id_mascota": tapo["id_mascota"]},
        {"$set": {"Last_Sync": nuevo_sync.isoformat()}}
    )
    
    safe_print(
        f"⏳  [FAST-FORWARD] Viaje en el tiempo exitoso para '{tapo['Nombre']}':\n"
        f"    Last_Sync previo: {last_sync_str}\n"
        f"    Last_Sync nuevo : {nuevo_sync.isoformat()} (-{hours} hora(s))",
        f"[FAST-FORWARD] Viaje en el tiempo exitoso para '{tapo['Nombre']}':\n"
        f"    Last_Sync previo: {last_sync_str}\n"
        f"    Last_Sync nuevo : {nuevo_sync.isoformat()} (-{hours} hora(s))"
    )
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python -m server.db.fast_forward <id_o_nombre_mascota> <horas>")
        sys.exit(1)
        
    identificador = sys.argv[1]
    try:
        cant_horas = float(sys.argv[2])
    except ValueError:
        print("Error: El parámetro horas debe ser un número decimal/entero.")
        sys.exit(1)
        
    fast_forward_tapo(identificador, cant_horas)
