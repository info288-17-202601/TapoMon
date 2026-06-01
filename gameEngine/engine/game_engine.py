"""
engine/game_engine.py
Motor central del juego TapoMon.
Gestiona el estado de la mascota, las acciones del usuario y la
simulación IDLE (degradación por tiempo desconectado).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from models.tapo import Tapo


# ------------------------------------------------------------------ #
#  Constantes de balance
# ------------------------------------------------------------------ #
TICK_HAMBRE      = -5    # por acción de tiempo (idle tick)
TICK_ENERGIA     = -3
TICK_FELICIDAD   = -4
TICK_SALUD_BASE  = -2    # solo si hambre o energía llegan a 0

FEED_HAMBRE      = +30

PLAY_FELICIDAD   = +25
PLAY_ENERGIA     = -15

TRAIN_FUERZA     = +2
TRAIN_DEFENSA    = +2
TRAIN_VELOCIDAD  = +2
TRAIN_VIDA       = +3
TRAIN_COSTO_ENERGIA = -10

STAT_MIN         = 0
STAT_MAX         = 100

IDLE_SECONDS_PER_TICK = 1800  # cada cuántos segundos equivale a un tick offline

REALTIME_SECONDS_PER_TICK = 5
REALTIME_HAMBRE = -1
REALTIME_ENERGIA = +1


# ------------------------------------------------------------------ #
#  Utilidades
# ------------------------------------------------------------------ #
def _clamp(value: int, lo: int = STAT_MIN, hi: int = STAT_MAX) -> int:
    return max(lo, min(hi, value))


def _aplicar_delta(tapo: Tapo, **deltas: int) -> list[str]:
    """Aplica cambios a los vitales y retorna mensajes de advertencia."""
    avisos: list[str] = []
    vitales = tapo.vitales
    for attr, delta in deltas.items():
        actual = getattr(vitales, attr)
        nuevo  = _clamp(actual + delta)
        setattr(vitales, attr, nuevo)
    return avisos


def _aplicar_delta_stats(tapo: Tapo, **deltas: int) -> None:
    stats = tapo.estadistica
    for attr, delta in deltas.items():
        actual = getattr(stats, attr)
        setattr(stats, attr, _clamp(actual + delta))


def _bonus_entrenamiento(base: int, felicidad: int) -> int:
    return base + int(base * (felicidad / 100))


# ------------------------------------------------------------------ #
#  Acciones del usuario
# ------------------------------------------------------------------ #

def alimentar(tapo: Tapo) -> list[str]:
    """El usuario da comida a su mascota."""
    msgs = _aplicar_delta(tapo, hambre=FEED_HAMBRE)
    msgs.insert(0, f"🍖  {tapo.nombre} fue alimentado.")
    return msgs


def jugar(tapo: Tapo) -> list[str]:
    """El usuario juega con su mascota."""
    if tapo.vitales.energia < 15:
        return [f"😴  {tapo.nombre} está demasiado cansado para jugar."]
    msgs = _aplicar_delta(tapo, felicidad=PLAY_FELICIDAD,
                          energia=PLAY_ENERGIA)
    msgs.insert(0, f"🎮  Jugaste con {tapo.nombre}.")
    return msgs


def curar(tapo: Tapo) -> list[str]:
    """Recupera la salud de la mascota (ítem de curación)."""
    msgs = _aplicar_delta(tapo, salud=+30)
    msgs.insert(0, f"💊  {tapo.nombre} fue curado.")
    return msgs


def entrenar_fuerza(tapo: Tapo) -> list[str]:
    if tapo.vitales.energia < abs(TRAIN_COSTO_ENERGIA):
        return [f"😴  {tapo.nombre} no tiene energía suficiente para entrenar fuerza."]
    delta = _bonus_entrenamiento(TRAIN_FUERZA, tapo.vitales.felicidad)
    _aplicar_delta_stats(tapo, fuerza=delta)
    msgs = _aplicar_delta(tapo, energia=TRAIN_COSTO_ENERGIA)
    msgs.insert(0, f"🏋️  {tapo.nombre} entrenó fuerza (+{delta}).")
    return msgs


def entrenar_defensa(tapo: Tapo) -> list[str]:
    if tapo.vitales.energia < abs(TRAIN_COSTO_ENERGIA):
        return [f"😴  {tapo.nombre} no tiene energía suficiente para entrenar defensa."]
    delta = _bonus_entrenamiento(TRAIN_DEFENSA, tapo.vitales.felicidad)
    _aplicar_delta_stats(tapo, defensa=delta)
    msgs = _aplicar_delta(tapo, energia=TRAIN_COSTO_ENERGIA)
    msgs.insert(0, f"🛡️  {tapo.nombre} entrenó defensa (+{delta}).")
    return msgs


def entrenar_velocidad(tapo: Tapo) -> list[str]:
    if tapo.vitales.energia < abs(TRAIN_COSTO_ENERGIA):
        return [f"😴  {tapo.nombre} no tiene energía suficiente para entrenar velocidad."]
    delta = _bonus_entrenamiento(TRAIN_VELOCIDAD, tapo.vitales.felicidad)
    _aplicar_delta_stats(tapo, velocidad=delta)
    msgs = _aplicar_delta(tapo, energia=TRAIN_COSTO_ENERGIA)
    msgs.insert(0, f"⚡  {tapo.nombre} entrenó velocidad (+{delta}).")
    return msgs


def entrenar_resistencia(tapo: Tapo) -> list[str]:
    if tapo.vitales.energia < abs(TRAIN_COSTO_ENERGIA):
        return [f"😴  {tapo.nombre} no tiene energía suficiente para entrenar resistencia."]
    delta = _bonus_entrenamiento(TRAIN_VIDA, tapo.vitales.felicidad)
    _aplicar_delta_stats(tapo, vida=delta)
    msgs = _aplicar_delta(tapo, energia=TRAIN_COSTO_ENERGIA)
    msgs.insert(0, f"💪  {tapo.nombre} entrenó resistencia (+{delta} vida).")
    return msgs


# ------------------------------------------------------------------ #
#  Idle Simulation (degradación offline)
# ------------------------------------------------------------------ #

def calcular_idle_ticks(last_sync: datetime) -> int:
    """Cuántos ticks de degradación corresponden desde la última sincronización."""
    delta_segundos = (datetime.now() - last_sync).total_seconds()
    return max(0, int(delta_segundos // IDLE_SECONDS_PER_TICK))


def aplicar_idle(tapo: Tapo) -> list[str]:
    """
    Simula el tiempo que el usuario estuvo desconectado.
    Equivale al componente 'Idle Simulation' del servidor, pero
    ejecutado localmente al volver a conectarse.
    """
    ticks = calcular_idle_ticks(tapo.last_sync)
    if ticks == 0:
        return []

    avisos: list[str] = [f"⏳  {tapo.nombre} estuvo solo12 {ticks} minuto(s)."]

    for _ in range(ticks):
        if not tapo.esta_vivo:
            break

        msgs = _aplicar_delta(
            tapo,
            hambre    = TICK_HAMBRE,
            energia   = abs(TICK_ENERGIA),
            felicidad = TICK_FELICIDAD,
        )

        # La salud cae si hambre o energía llegan a 0
        if tapo.vitales.hambre == 0 or tapo.vitales.energia == 0:
            msgs += _aplicar_delta(tapo, salud=TICK_SALUD_BASE)

        # La salud baja → puntos de vida bajan (1 vida por cada 10 pts de salud perdidos)
        if tapo.vitales.salud == 0:
            _aplicar_delta_vida(tapo, -2)

        avisos.extend(msgs)

    tapo.last_sync = datetime.now()
    return avisos


def aplicar_realtime_ticks(tapo: Tapo, ticks: int) -> list[str]:
    """Aplica ticks en tiempo real mientras el usuario esta conectado."""
    if ticks <= 0:
        return []

    avisos: list[str] = []
    for _ in range(ticks):
        msgs = _aplicar_delta(
            tapo,
            hambre=REALTIME_HAMBRE,
            energia=REALTIME_ENERGIA,
        )

        if tapo.vitales.hambre == 0:
            msgs += _aplicar_delta(tapo, salud=TICK_SALUD_BASE)

        avisos.extend(msgs)

    return avisos


def _aplicar_delta_vida(tapo: Tapo, delta: int) -> None:
    tapo.estadistica.vida = _clamp(tapo.estadistica.vida + delta)


# ------------------------------------------------------------------ #
#  Comprobación de muerte
# ------------------------------------------------------------------ #

def verificar_muerte(tapo: Tapo) -> bool:
    """Retorna True si la mascota murió (vida == 0)."""
    return tapo.estadistica.vida <= 0


# ------------------------------------------------------------------ #
#  Resumen de estado
# ------------------------------------------------------------------ #

def resumen_estado(tapo: Tapo) -> dict:
    return {
        "nombre":       tapo.nombre,
        "tipo":         tapo.estadistica.tipo.value,
        "vida":         tapo.estadistica.vida,
        "fuerza":       tapo.estadistica.fuerza,
        "defensa":      tapo.estadistica.defensa,
        "velocidad":    tapo.estadistica.velocidad,
        "hambre":       tapo.vitales.hambre,
        "energia":      tapo.vitales.energia,
        "felicidad":    tapo.vitales.felicidad,
        "salud":        tapo.vitales.salud,
        "estado":       tapo.estado_label,
        "last_sync":    tapo.last_sync.strftime("%Y-%m-%d %H:%M:%S"),
    }
