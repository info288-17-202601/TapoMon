"""
p2pEngine/combat_engine.py
Motor de combate basado en dados para TapoMon.

Mecánicas:
  - Attack Roll  = D20 + mod_velocidad  (siempre 1 dado, sin ventaja en el roll)
  - Armor Class  = BASE_AC + mod_velocidad(defensor)
  - Ventaja de tipo  → daño × 1.5  (redondeado, mínimo 1)
  - Desventaja de tipo → daño × 0.5 (redondeado, mínimo 1)
  - Daño base    = D6 + mod_fuerza − mod_defensa_enemigo  (mínimo 1 antes del multiplicador)

Modificadores derivados de estadísticas:
  velocidad / 10  → mod_velocidad  (ej: velocidad=30 → mod=3)
  fuerza    / 10  → mod_fuerza
  defensa   / 10  → mod_defensa
"""
from __future__ import annotations

import random
from typing import Literal

from models.tapo import Tapo, TipoTapo


# ------------------------------------------------------------------ #
#  Constantes de combate
# ------------------------------------------------------------------ #

BASE_AC = 10          # Armor Class base antes de agregar mod de velocidad
TURN_DELAY_SEC = 1.0  # Pausa entre acciones para ritmo de combate

# Tabla de ventajas de tipo (atacante → defensor)
# "ventaja"    : daño × 1.5  (redondeado hacia abajo, mínimo 1)
# "desventaja" : daño × 0.5  (redondeado hacia abajo, mínimo 1)
# None         : sin modificador de tipo

MULT_VENTAJA    = 1.5
MULT_DESVENTAJA = 0.5

TABLA_TIPOS: dict[TipoTapo, dict[TipoTapo, Literal["ventaja", "desventaja"] | None]] = {
    #            Fuego          Agua           Planta         Luz            Oscuridad      Normal
    TipoTapo.FUEGO: {
        TipoTapo.FUEGO:      None,
        TipoTapo.AGUA:       "desventaja",   # Agua apaga el fuego
        TipoTapo.PLANTA:     "ventaja",      # Fuego quema la planta
        TipoTapo.LUZ:        None,
        TipoTapo.OSCURIDAD:  None,
        TipoTapo.NORMAL:     None,
    },
    TipoTapo.AGUA: {
        TipoTapo.FUEGO:      "ventaja",      # Agua apaga el fuego
        TipoTapo.AGUA:       None,
        TipoTapo.PLANTA:     "desventaja",   # Planta absorbe el agua
        TipoTapo.LUZ:        None,
        TipoTapo.OSCURIDAD:  None,
        TipoTapo.NORMAL:     None,
    },
    TipoTapo.PLANTA: {
        TipoTapo.FUEGO:      "desventaja",   # Fuego quema la planta
        TipoTapo.AGUA:       "ventaja",      # Planta absorbe el agua
        TipoTapo.PLANTA:     None,
        TipoTapo.LUZ:        None,
        TipoTapo.OSCURIDAD:  None,
        TipoTapo.NORMAL:     None,
    },
    TipoTapo.LUZ: {
        TipoTapo.FUEGO:      None,
        TipoTapo.AGUA:       None,
        TipoTapo.PLANTA:     None,
        TipoTapo.LUZ:        None,
        TipoTapo.OSCURIDAD:  "ventaja",      # Luz disipa la oscuridad
        TipoTapo.NORMAL:     None,
    },
    TipoTapo.OSCURIDAD: {
        TipoTapo.FUEGO:      None,
        TipoTapo.AGUA:       None,
        TipoTapo.PLANTA:     None,
        TipoTapo.LUZ:        "ventaja",      # Oscuridad apaga la luz
        TipoTapo.OSCURIDAD:  None,
        TipoTapo.NORMAL:     None,
    },
    TipoTapo.NORMAL: {                       # Normal es neutro a todo
        TipoTapo.FUEGO:      None,
        TipoTapo.AGUA:       None,
        TipoTapo.PLANTA:     None,
        TipoTapo.LUZ:        None,
        TipoTapo.OSCURIDAD:  None,
        TipoTapo.NORMAL:     None,
    },
}


# ------------------------------------------------------------------ #
#  Modificadores
# ------------------------------------------------------------------ #

def mod_velocidad(tapo: Tapo) -> int:
    """Modificador de velocidad: velocidad // 10."""
    return tapo.estadistica.velocidad // 10

def mod_fuerza(tapo: Tapo) -> int:
    """Modificador de fuerza: fuerza // 10."""
    return tapo.estadistica.fuerza // 10

def mod_defensa(tapo: Tapo) -> int:
    """Modificador de defensa: defensa // 10."""
    return tapo.estadistica.defensa // 10


# ------------------------------------------------------------------ #
#  Tiradas de dados
# ------------------------------------------------------------------ #

def _d(n: int) -> int:
    """Tira un dado de n caras."""
    return random.randint(1, n)


def tipo_ventaja(atacante: Tapo, defensor: Tapo) -> Literal["ventaja", "desventaja"] | None:
    """Determina si el atacante tiene ventaja, desventaja o ninguna contra el defensor."""
    tipo_atk = atacante.estadistica.tipo
    tipo_def = defensor.estadistica.tipo
    return TABLA_TIPOS.get(tipo_atk, {}).get(tipo_def, None)


def tirar_d20() -> tuple[int, list[int]]:
    """Tira 1D20. Retorna (resultado, [tirada])."""
    t = _d(20)
    return t, [t]


# ------------------------------------------------------------------ #
#  Mecánicas principales
# ------------------------------------------------------------------ #

def calcular_attack_roll(atacante: Tapo, defensor: Tapo) -> dict:
    """
    Calcula el Attack Roll del atacante contra el defensor.
    Siempre es 1D20 + mod_velocidad; la ventaja de tipo afecta al daño, no al roll.

    Retorna un dict con:
      - resultado      : valor final del ataque
      - tiradas        : [valor del D20]
      - mod_vel        : modificador de velocidad del atacante
      - ventaja_tipo   : "ventaja" | "desventaja" | None  (para aplicar al daño)
    """
    d20_res, tiradas = tirar_d20()
    mv = mod_velocidad(atacante)
    resultado = d20_res + mv

    return {
        "resultado":    resultado,
        "tiradas":      tiradas,
        "mod_vel":      mv,
        "ventaja_tipo": tipo_ventaja(atacante, defensor),
    }


def calcular_armor_class(defensor: Tapo) -> int:
    """
    Armor Class del defensor.
    AC = BASE_AC + mod_velocidad(defensor)
    """
    return BASE_AC + mod_velocidad(defensor)


def calcular_dano(
    atacante: Tapo,
    defensor: Tapo,
    ventaja_tipo: Literal["ventaja", "desventaja"] | None = None,
) -> dict:
    """
    Calcula el daño del atacante al defensor.

    Fórmula base : D6 + mod_fuerza(atacante) − mod_defensa(defensor)  (mínimo 1)
    Ventaja tipo : daño base × 1.5  → redondeado, mínimo 1
    Desventaja   : daño base × 0.5  → redondeado, mínimo 1

    Retorna dict con:
      - dano          : daño final tras multiplicador de tipo
      - dano_base     : daño antes del multiplicador
      - d6            : valor del dado D6
      - mod_atk       : mod de fuerza del atacante
      - mod_def       : mod de defensa del defensor
      - multiplicador : 1.5 | 0.5 | 1.0
    """
    d6  = _d(6)
    mf  = mod_fuerza(atacante)
    md  = mod_defensa(defensor)
    dano_base = max(1, d6 + mf - md)

    if ventaja_tipo == "ventaja":
        mult = MULT_VENTAJA
    elif ventaja_tipo == "desventaja":
        mult = MULT_DESVENTAJA
    else:
        mult = 1.0

    dano = max(1, int(dano_base * mult))

    return {
        "dano":         dano,
        "dano_base":    dano_base,
        "d6":           d6,
        "mod_atk":      mf,
        "mod_def":      md,
        "multiplicador": mult,
    }


def resolver_turno(atacante: Tapo, defensor: Tapo) -> dict:
    """
    Resuelve un turno completo de combate localmente.
    Útil para simulación/pruebas sin conexión P2P.

    Retorna dict con toda la información del turno.
    """
    atk    = calcular_attack_roll(atacante, defensor)
    ac     = calcular_armor_class(defensor)
    golpeo = atk["resultado"] >= ac

    resultado_dano = None
    if golpeo:
        resultado_dano = calcular_dano(atacante, defensor, atk["ventaja_tipo"])

    return {
        "atacante":    atacante.nombre,
        "defensor":    defensor.nombre,
        "attack_roll": atk,
        "armor_class": ac,
        "golpeo":      golpeo,
        "dano":        resultado_dano,
    }


# ------------------------------------------------------------------ #
#  HP de combate temporal
# ------------------------------------------------------------------ #

def hp_combate(tapo: Tapo) -> int:
    """
    HP que se usa durante el combate.
    Se basa en estadistica.vida del Tapo (no se persiste automáticamente).
    """
    return tapo.estadistica.vida


class EstadoCombate:
    """
    Contiene el estado mutable de HP durante una batalla.
    No modifica al Tapo original hasta que se decide aplicar el resultado.
    """

    def __init__(self, tapo_local: Tapo, tapo_rival: Tapo) -> None:
        self.tapo_local  = tapo_local
        self.tapo_rival  = tapo_rival
        self.hp_local    = hp_combate(tapo_local)
        self.hp_rival    = hp_combate(tapo_rival)
        self.turno       = 0       # número de turno global
        self.es_atacante = True    # si este jugador ataca en el turno actual

    def aplicar_dano_a_rival(self, dano: int) -> None:
        self.hp_rival = max(0, self.hp_rival - dano)

    def aplicar_dano_a_local(self, dano: int) -> None:
        self.hp_local = max(0, self.hp_local - dano)

    @property
    def batalla_terminada(self) -> bool:
        return self.hp_local <= 0 or self.hp_rival <= 0

    @property
    def ganador_local(self) -> bool:
        """True si el jugador local ganó (rival sin HP)."""
        return self.hp_rival <= 0 and self.hp_local > 0

    def siguiente_turno(self) -> None:
        self.turno += 1
        self.es_atacante = not self.es_atacante
