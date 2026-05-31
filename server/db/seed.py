"""
server/db/seed.py
Script de sembrado de base de datos para TapoMon.
Limpia colecciones de prueba y crea usuarios y mascotas preconfiguradas
para simular diferentes desfases de tiempo y verificar el Idle Simulator.
"""
from __future__ import annotations

import sys
import os
# Agregar el directorio padre al PATH de python para resolver 'server'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import hashlib
from datetime import datetime, timedelta

from server.config import COL_MASCOTAS, COL_USUARIOS, COL_INBOX
from server.db.mongo import get_db, crear_indices


def safe_print(emoji_text: str, fallback_text: str) -> None:
    """Imprime el texto con emoji, si hay un error de codificación usa el fallback sin emojis."""
    try:
        print(emoji_text)
    except UnicodeEncodeError:
        print(fallback_text)


def hash_password(password: str) -> str:
    """Aplica hashing SHA-256 consistente con el servidor."""
    return hashlib.sha256(password.encode()).hexdigest()


def sembrar_base_de_datos() -> None:
    """Limpia las colecciones y siembra datos iniciales de prueba."""
    db = get_db()

    safe_print("🧹  [SEED] Limpiando colecciones existentes...", "[SEED] Limpiando colecciones existentes...")
    db[COL_USUARIOS].delete_many({})
    db[COL_MASCOTAS].delete_many({})
    db[COL_INBOX].delete_many({})

    # Crear índices
    crear_indices()

    # Tiempos de referencia
    ahora = datetime.now()
    hace_10_min = (ahora - timedelta(minutes=10)).isoformat()
    hace_4_horas = (ahora - timedelta(hours=4)).isoformat()
    hace_24_horas = (ahora - timedelta(hours=24)).isoformat()

    safe_print("🌱  [SEED] Sembrando mascotas (Tapo)...", "[SEED] Sembrando mascotas (Tapo)...")
    tapos = [
        {
            "id_mascota": "tapo-fuego-001",
            "Nombre": "FuegoMon",
            "Vitales": {
                "hambre": 100,
                "energia": 100,
                "salud": 100,
                "felicidad": 100,
                "independencia": 50
            },
            "Estadistica": {
                "vida": 100,
                "fuerza": 15,
                "defensa": 12,
                "velocidad": 14,
                "tipo": "Fuego"
            },
            "Estado_Sistema": False,  # IDLE
            "Last_Sync": hace_10_min,
            "Friend_List": [],
            "Gift_Cooldowns": []
        },
        {
            "id_mascota": "tapo-agua-002",
            "Nombre": "AguaMon",
            "Vitales": {
                "hambre": 80,
                "energia": 90,
                "salud": 100,
                "felicidad": 75,
                "independencia": 40
            },
            "Estadistica": {
                "vida": 100,
                "fuerza": 11,
                "defensa": 18,
                "velocidad": 10,
                "tipo": "Agua"
            },
            "Estado_Sistema": False,  # IDLE
            "Last_Sync": hace_4_horas,
            "Friend_List": ["tapo-fuego-001"],
            "Gift_Cooldowns": []
        },
        {
            "id_mascota": "tapo-planta-003",
            "Nombre": "PlantaMon",
            "Vitales": {
                "hambre": 50,
                "energia": 40,
                "salud": 90,
                "felicidad": 60,
                "independencia": 60
            },
            "Estadistica": {
                "vida": 100,
                "fuerza": 13,
                "defensa": 13,
                "velocidad": 12,
                "tipo": "Planta"
            },
            "Estado_Sistema": False,  # IDLE
            "Last_Sync": hace_24_horas,
            "Friend_List": [],
            "Gift_Cooldowns": []
        }
    ]

    for tapo in tapos:
        db[COL_MASCOTAS].insert_one(tapo)
        safe_print(
            f"    🐾 Mascota '{tapo['Nombre']}' creada ({tapo['id_mascota']}).",
            f"    Mascota '{tapo['Nombre']}' creada ({tapo['id_mascota']})."
        )

    safe_print("👤  [SEED] Sembrando usuarios...", "[SEED] Sembrando usuarios...")
    usuarios = [
        {
            "Id": "user-001",
            "Username": "jugador1",
            "Correo": "jugador1@tapomon.cl",
            "Password": hash_password("pass123"),
            "Tapo_ID": "tapo-fuego-001"
        },
        {
            "Id": "user-002",
            "Username": "jugador2",
            "Correo": "jugador2@tapomon.cl",
            "Password": hash_password("pass123"),
            "Tapo_ID": "tapo-agua-002"
        },
        {
            "Id": "user-003",
            "Username": "jugador3",
            "Correo": "jugador3@tapomon.cl",
            "Password": hash_password("pass123"),
            "Tapo_ID": "tapo-planta-003"
        }
    ]

    for user in usuarios:
        db[COL_USUARIOS].insert_one(user)
        safe_print(
            f"    👤 Usuario '{user['Username']}' creado con Tapo_ID: {user['Tapo_ID']}",
            f"    Usuario '{user['Username']}' creado con Tapo_ID: {user['Tapo_ID']}"
        )

    safe_print("✅  [SEED] Sembrado completado exitosamente.", "[SEED] Sembrado completado exitosamente.")


if __name__ == "__main__":
    sembrar_base_de_datos()
