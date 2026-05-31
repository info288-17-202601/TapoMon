"""
server/services/idle_engine.py
Motor de simulación IDLE del servidor central.

Justificación:
    Según el informe:
    "Simulación que se encarga de calcular y actualizar el estado de las
     mascotas mientras el usuario está desconectado, descontando estadísticas
     si se está mucho tiempo desconectado."

    Este componente corre como tarea programada (APScheduler) dentro del
    servidor FastAPI. Cada intervalo (configurable, default 60s):
    1. Busca TODOS los Tapos con Estado_Sistema == false (IDLE).
    2. Calcula cuántos "ticks" de degradación han pasado desde Last_Sync.
    3. Aplica la degradación (hambre, energía, felicidad, salud, vida).
    4. Aplica la mecánica de Independencia (acciones autónomas).
    5. Actualiza Last_Sync y registra las acciones en el Inbox.

    Mecánica de Independencia:
    - Cada tick, P(acción autónoma) = independencia / 100.
    - Pool de acciones: comer (40 %), jugar (30 %), entrenar stat (30 %).
    - La independencia crece +1 por tick cuando salud >= umbral (60).
    - Las acciones se notifican en el Inbox para que el cliente las lea
      al reconectarse (resume_state), sin necesidad de lógica extra en el cliente.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from server.db.mongo import get_db
from server.config import (
    COL_MASCOTAS,
    COL_INBOX,
    TICK_HAMBRE,
    TICK_ENERGIA,
    TICK_FELICIDAD,
    TICK_SALUD_BASE,
    STAT_MIN,
    STAT_MAX,
    INDEPENDENCIA_GROWTH,
    INDEPENDENCIA_HEALTH_THRESHOLD,
    SELF_FEED_HAMBRE,
    SELF_PLAY_FELICIDAD,
    SELF_PLAY_ENERGIA,
    SELF_PLAY_ENERGIA_MIN,
    SELF_TRAIN_STAT,
)

# Constante de balance: segundos reales que equivalen a 1 tick de degradación offline (30 minutos)
IDLE_SECONDS_PER_TICK = 1800


# ------------------------------------------------------------------ #
#  Utilidades
# ------------------------------------------------------------------ #

def _clamp(value: int, lo: int = STAT_MIN, hi: int = STAT_MAX) -> int:
    """Limita un valor entre lo y hi."""
    return max(lo, min(hi, value))


def calcular_ticks_pendientes(last_sync_str: str) -> int:
    """
    Calcula cuántos ticks de degradación de 30 minutos corresponden desde la última sync.
    Cada tick equivale a IDLE_SECONDS_PER_TICK (1800 s).
    """
    try:
        last_sync = datetime.fromisoformat(last_sync_str)
    except (ValueError, TypeError):
        last_sync = datetime.now()

    delta_seconds = (datetime.now() - last_sync).total_seconds()
    return max(0, int(delta_seconds // IDLE_SECONDS_PER_TICK))


# ------------------------------------------------------------------ #
#  Mecánica de Independencia
# ------------------------------------------------------------------ #

def intentar_accion_autonoma(tapo_doc: dict, tick_n: int) -> str | None:
    """
    Intenta que el Tapo realice una acción autónoma en base a su independencia.

    Probabilidad de actuar = independencia / 100.
    Pool ponderado:
        - Comer    40 % → hambre + SELF_FEED_HAMBRE
        - Jugar    30 % → felicidad + SELF_PLAY_FELICIDAD, energía + SELF_PLAY_ENERGIA
        - Entrenar 30 % → stat aleatorio (fuerza/defensa/velocidad) + SELF_TRAIN_STAT,
                          energía + SELF_PLAY_ENERGIA

    Si la energía es insuficiente para jugar o entrenar, cae back a comer.

    Args:
        tapo_doc: Documento del Tapo (Vitales y Estadistica se modifican in-place).
        tick_n:   Índice del tick actual (para logging futuro).

    Returns:
        Descripción corta de la acción realizada, o None si no actuó.
    """
    vitales     = tapo_doc.get("Vitales", {})
    estadistica = tapo_doc.get("Estadistica", {})

    # Si la mascota está muerta, no actúa
    if estadistica.get("vida", 0) <= 0:
        return None

    independencia = vitales.get("independencia", 0)

    # Chequeo probabilístico
    if random.random() >= independencia / 100:
        return None

    energia = vitales.get("energia", 0)

    # Selección de acción ponderada
    roll = random.random()
    if roll < 0.40:
        action = "eat"
    elif roll < 0.70:
        action = "play"
    else:
        action = "train"

    # Fallback a comer si no hay energía suficiente
    if action in ("play", "train") and energia < SELF_PLAY_ENERGIA_MIN:
        action = "eat"

    accion_label: str

    if action == "eat":
        vitales["hambre"] = _clamp(vitales.get("hambre", 0) + SELF_FEED_HAMBRE)
        accion_label = "comió solo"

    elif action == "play":
        vitales["felicidad"] = _clamp(vitales.get("felicidad", 0) + SELF_PLAY_FELICIDAD)
        vitales["energia"]   = _clamp(vitales.get("energia",   0) + SELF_PLAY_ENERGIA)
        accion_label = "jugó solo"

    else:  # train
        stat = random.choice(["fuerza", "defensa", "velocidad"])
        estadistica[stat]    = _clamp(estadistica.get(stat, 0) + SELF_TRAIN_STAT)
        vitales["energia"]   = _clamp(vitales.get("energia", 0) + SELF_PLAY_ENERGIA)
        accion_label = f"entrenó {stat} solo"

    tapo_doc["Vitales"]     = vitales
    tapo_doc["Estadistica"] = estadistica
    return accion_label


# ------------------------------------------------------------------ #
#  Degradación + Independencia
# ------------------------------------------------------------------ #

def aplicar_degradacion(tapo_doc: dict, ticks: int) -> tuple[dict, list[str]]:
    """
    Aplica N ticks de degradación a un documento Tapo.

    Por cada tick:
        1. Degrada vitales (hambre, energía, felicidad).
        2. Aplica daño a salud/vida si corresponde.
        3. Intenta acción autónoma según independencia.
        4. Hace crecer la independencia si el Tapo está saludable.

    Args:
        tapo_doc: Documento del Tapo (modificado in-place).
        ticks:    Número de ticks a aplicar.

    Returns:
        Tuple (tapo_doc actualizado, lista de descripciones de acciones autónomas).
    """
    vitales     = tapo_doc.get("Vitales", {})
    estadistica = tapo_doc.get("Estadistica", {})
    acciones: list[str] = []

    for tick_n in range(ticks):
        if estadistica.get("vida", 0) <= 0:
            break

        # 1. Degradar vitales
        vitales["hambre"]    = _clamp(vitales.get("hambre",    100) + TICK_HAMBRE)
        vitales["energia"]   = _clamp(vitales.get("energia",   100) + TICK_ENERGIA)
        vitales["felicidad"] = _clamp(vitales.get("felicidad", 100) + TICK_FELICIDAD)

        # 2. Salud cae si hambre o energía llegan a 0
        if vitales["hambre"] == 0 or vitales["energia"] == 0:
            vitales["salud"] = _clamp(vitales.get("salud", 100) + TICK_SALUD_BASE)

        # 3. Vida cae si salud llega a 0
        if vitales.get("salud", 0) == 0:
            estadistica["vida"] = _clamp(estadistica.get("vida", 100) - 2)

        # Sincronizar antes de la acción autónoma (que también modifica el doc)
        tapo_doc["Vitales"]     = vitales
        tapo_doc["Estadistica"] = estadistica

        # 4. Intentar acción autónoma
        accion = intentar_accion_autonoma(tapo_doc, tick_n)
        if accion:
            acciones.append(accion)

        # Re-leer en caso de que la acción autónoma haya modificado los stats
        vitales     = tapo_doc["Vitales"]
        estadistica = tapo_doc["Estadistica"]

        # 5. Crecer independencia si el Tapo está saludable
        if (vitales.get("salud", 0) >= INDEPENDENCIA_HEALTH_THRESHOLD
                and estadistica.get("vida", 0) > 0):
            vitales["independencia"] = min(
                STAT_MAX,
                vitales.get("independencia", 0) + INDEPENDENCIA_GROWTH,
            )

    tapo_doc["Vitales"]     = vitales
    tapo_doc["Estadistica"] = estadistica
    return tapo_doc, acciones


# ------------------------------------------------------------------ #
#  Inbox
# ------------------------------------------------------------------ #

def _escribir_inbox_autonomia(db, tapo_id: str, acciones: list[str]) -> None:
    """
    Escribe un mensaje resumen en el Inbox con las acciones autónomas del período IDLE.
    El cliente lo leerá en resume_state y lo mostrará como notificación.
    """
    msg = {
        "ID_Mensaje":   str(uuid.uuid4()),
        "Recipient_ID": tapo_id,
        "Sender_ID":    "SYSTEM",
        "Payload": {
            "tipo":     "autonomia",
            "acciones": acciones,
            "resumen":  f"Tu Tapo actuó solo: {', '.join(acciones)}.",
        },
        "Status":    False,
        "Timestamp": datetime.now().isoformat(),
    }
    db[COL_INBOX].insert_one(msg)


# ------------------------------------------------------------------ #
#  Tarea programada
# ------------------------------------------------------------------ #

def ejecutar_idle_tick() -> int:
    """
    Tarea programada: procesa TODOS los Tapos en estado IDLE.

    Por cada Tapo:
        1. Calcula ticks pendientes desde Last_Sync.
        2. Aplica degradación + mecánica de independencia.
        3. Si hubo acciones autónomas, escribe un mensaje en el Inbox.
        4. Actualiza Vitales, Estadistica e independencia en MongoDB.

    Returns:
        Número de Tapos procesados.
    """
    db = get_db()

    idle_tapos = list(db[COL_MASCOTAS].find({"Estado_Sistema": False}))

    procesados = 0
    for tapo_doc in idle_tapos:
        last_sync = tapo_doc.get("Last_Sync", datetime.now().isoformat())

        if isinstance(last_sync, datetime):
            last_sync = last_sync.isoformat()

        ticks = calcular_ticks_pendientes(last_sync)
        if ticks == 0:
            continue

        # Aplicar degradación + independencia
        tapo_doc, acciones = aplicar_degradacion(tapo_doc, ticks)

        # Avanzar Last_Sync exactamente por los ticks procesados
        try:
            last_sync_dt = datetime.fromisoformat(last_sync)
        except Exception:
            last_sync_dt = datetime.now()
        nuevo_sync = (
            last_sync_dt + timedelta(seconds=ticks * IDLE_SECONDS_PER_TICK)
        ).isoformat()

        # Persistir cambios en MongoDB
        db[COL_MASCOTAS].update_one(
            {"id_mascota": tapo_doc["id_mascota"]},
            {"$set": {
                "Vitales":     tapo_doc["Vitales"],
                "Estadistica": tapo_doc["Estadistica"],
                "Last_Sync":   nuevo_sync,
            }},
        )

        # Notificar acciones autónomas en el Inbox
        if acciones:
            _escribir_inbox_autonomia(db, tapo_doc["id_mascota"], acciones)

        procesados += 1

    if procesados > 0:
        try:
            print(f"⏰  [IDLE] Procesados {procesados} Tapo(s) en modo IDLE.")
        except UnicodeEncodeError:
            print(f"[IDLE] Procesados {procesados} Tapo(s) en modo IDLE.")

    return procesados
