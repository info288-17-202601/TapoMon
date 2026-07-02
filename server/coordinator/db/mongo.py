"""
server/coordinator/db/mongo.py
Conexión a MongoDB del Coordinador Central.

Sigue el mismo patrón singleton que server/db/mongo.py,
pero conecta a una base de datos propia e independiente
que solo almacena el registro de jugadores y estado de servidores.
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from server.coordinator.config import (
    MONGO_URI,
    MONGO_DB,
    COL_PLAYER_REGISTRY,
    COL_SERVER_STATUS,
)


# ------------------------------------------------------------------ #
#  Singleton de conexión
# ------------------------------------------------------------------ #
_client:   MongoClient | None = None
_database: Database | None    = None


def get_db() -> Database:
    """Retorna la instancia de la base de datos del coordinador (singleton)."""
    global _client, _database

    if _database is not None:
        return _database

    try:
        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
        )
        _client.admin.command("ping")

        # Resolver nombre case-insensitive
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
            print(f"✅  [COORDINATOR] Conectado a MongoDB: {MONGO_URI} / base: {db_name}")
        except UnicodeEncodeError:
            print(f"[OK] [COORDINATOR] Conectado a MongoDB: {MONGO_URI} / base: {db_name}")
        return _database

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        raise ConnectionError(
            f"[COORDINATOR] No se pudo conectar a MongoDB en '{MONGO_URI}'.\n"
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
    Crea índices necesarios para el coordinador.
    Idempotente — se puede llamar múltiples veces.
    """
    db = get_db()
    db[COL_PLAYER_REGISTRY].create_index("usuario_id", unique=True)
    db[COL_PLAYER_REGISTRY].create_index("username",   unique=True)
    db[COL_SERVER_STATUS].create_index("server_name",   unique=True)
