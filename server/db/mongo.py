"""
server/db/mongo.py
Conexión a MongoDB del servidor central (Pet State Store).

Justificación:
    Este módulo es independiente del connection.py del cliente porque:
    - El servidor puede apuntar a una instancia MongoDB diferente.
    - Necesita su propio ciclo de vida (startup/shutdown de FastAPI).
    - Usa el mismo patrón singleton que el cliente para consistencia,
      pero con soporte para el lifecycle de FastAPI (startup/shutdown events).
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from server.config import MONGO_URI, MONGO_DB, COL_USUARIOS, COL_MASCOTAS, COL_INBOX


# ------------------------------------------------------------------ #
#  Singleton de conexión
# ------------------------------------------------------------------ #
_client:   MongoClient | None = None
_database: Database | None    = None


def get_db() -> Database:
    """Retorna la instancia de la base de datos del servidor (singleton)."""
    global _client, _database

    if _database is not None:
        return _database

    try:
        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
        )
        _client.admin.command("ping")

        # Resolver nombre case-insensitive (misma lógica que el cliente)
        db_name = MONGO_DB
        try:
            existing = _client.list_database_names()
            for name in existing:
                if name.lower() == db_name.lower():
                    db_name = name
                    break
        except Exception:
            pass

        _database = _client[db_name]
        try:
            print(f"✅  [SERVER] Conectado a MongoDB: {MONGO_URI} / base: {db_name}")
        except UnicodeEncodeError:
            print(f"[OK] [SERVER] Conectado a MongoDB: {MONGO_URI} / base: {db_name}")
        return _database

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        raise ConnectionError(
            f"❌  [SERVER] No se pudo conectar a MongoDB en '{MONGO_URI}'.\n"
            f"    Detalle: {e}"
        )


def cerrar_conexion() -> None:
    """Cierra la conexión con MongoDB."""
    global _client, _database
    if _client:
        _client.close()
        _client   = None
        _database = None


def crear_indices() -> None:
    """
    Crea índices necesarios para el servidor.
    Idempotente — se puede llamar múltiples veces.
    """
    db = get_db()
    db[COL_USUARIOS].create_index("Id",       unique=True)
    
    # Crear índices únicos case-insensitive para Username y Correo
    db[COL_USUARIOS].create_index(
        "Username", 
        unique=True,
        collation={"locale": "en", "strength": 2}
    )
    db[COL_USUARIOS].create_index(
        "Correo", 
        unique=True,
        collation={"locale": "en", "strength": 2}
    )
    
    db[COL_MASCOTAS].create_index("id_mascota", unique=True)
    db[COL_INBOX].create_index([("Recipient_ID", 1), ("Status", 1)])
