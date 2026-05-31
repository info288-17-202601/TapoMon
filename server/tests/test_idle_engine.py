"""
tests/test_idle_engine.py
Tests unitarios del motor de simulación IDLE.

Verifica:
    - Cálculo correcto de ticks pendientes.
    - Degradación de vitales (hambre, energía, felicidad).
    - Degradación de salud cuando hambre/energía llegan a 0.
    - Degradación de vida cuando salud llega a 0.
    - La mascota no se degrada más allá de vida == 0.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.services.idle_engine import (
    calcular_ticks_pendientes,
    aplicar_degradacion,
    _clamp,
    IDLE_SECONDS_PER_TICK,
)
from server.config import (
    TICK_HAMBRE, TICK_ENERGIA, TICK_FELICIDAD, TICK_SALUD_BASE,
)


class TestClamp:
    """Tests de la función clamp."""

    def test_valor_normal(self):
        assert _clamp(50) == 50

    def test_valor_minimo(self):
        assert _clamp(-10) == 0

    def test_valor_maximo(self):
        assert _clamp(150) == 100

    def test_valor_en_limites(self):
        assert _clamp(0) == 0
        assert _clamp(100) == 100


class TestCalcularTicks:
    """Tests del cálculo de ticks pendientes."""

    def test_sin_ticks(self):
        """Si la última sync fue hace poco, 0 ticks."""
        now = datetime.now().isoformat()
        assert calcular_ticks_pendientes(now) == 0

    def test_un_tick(self):
        """Después de 30 minutos (default), 1 tick."""
        hace = (datetime.now() - timedelta(seconds=IDLE_SECONDS_PER_TICK + 1)).isoformat()
        ticks = calcular_ticks_pendientes(hace)
        assert ticks >= 1

    def test_multiples_ticks(self):
        """Después de 2.5 horas, debería haber ~5 ticks (con intervalo de 30 minutos)."""
        hace = (datetime.now() - timedelta(minutes=150)).isoformat()
        ticks = calcular_ticks_pendientes(hace)
        assert ticks >= 4  # Tolerancia de 1 por timing

    def test_valor_invalido(self):
        """Un Last_Sync inválido da 0 ticks (no crashea)."""
        ticks = calcular_ticks_pendientes("invalido")
        assert ticks == 0


class TestAplicarDegradacion:
    """Tests de la degradación de vitales."""

    def _make_tapo_doc(self, **kwargs):
        """Helper: crea un documento Tapo de prueba."""
        doc = {
            "Vitales": {
                "hambre": 100, "energia": 100, "salud": 100,
                "felicidad": 100, "independencia": 50,
            },
            "Estadistica": {
                "vida": 100, "fuerza": 10, "defensa": 10,
                "velocidad": 10, "tipo": "Normal",
            },
        }
        doc["Vitales"].update(kwargs.get("vitales", {}))
        doc["Estadistica"].update(kwargs.get("estadistica", {}))
        return doc

    def test_un_tick_degrada_vitales(self):
        """Un tick reduce hambre, energía y felicidad (al menos la degradación base)."""
        doc = self._make_tapo_doc(vitales={"independencia": 0})  # sin acciones autónomas
        doc_out, _ = aplicar_degradacion(doc, 1)

        assert doc_out["Vitales"]["hambre"]    == 100 + TICK_HAMBRE      # 95
        assert doc_out["Vitales"]["energia"]   == 100 + TICK_ENERGIA     # 97
        assert doc_out["Vitales"]["felicidad"] == 100 + TICK_FELICIDAD   # 96

    def test_vitales_no_bajan_de_cero(self):
        """Los vitales nunca bajan de 0."""
        doc = self._make_tapo_doc(vitales={"hambre": 2, "energia": 1, "felicidad": 1, "independencia": 0})
        doc_out, _ = aplicar_degradacion(doc, 1)

        assert doc_out["Vitales"]["hambre"]    >= 0
        assert doc_out["Vitales"]["energia"]   >= 0
        assert doc_out["Vitales"]["felicidad"] >= 0

    def test_salud_cae_con_hambre_cero(self):
        """La salud baja si el hambre llega a 0."""
        doc = self._make_tapo_doc(vitales={"hambre": 0, "independencia": 0})
        salud_antes = doc["Vitales"]["salud"]
        doc_out, _ = aplicar_degradacion(doc, 1)

        assert doc_out["Vitales"]["salud"] < salud_antes

    def test_salud_cae_con_energia_cero(self):
        """La salud baja si la energía llega a 0."""
        doc = self._make_tapo_doc(vitales={"energia": 0, "independencia": 0})
        salud_antes = doc["Vitales"]["salud"]
        doc_out, _ = aplicar_degradacion(doc, 1)

        assert doc_out["Vitales"]["salud"] < salud_antes

    def test_vida_cae_con_salud_cero(self):
        """La vida baja si la salud llega a 0."""
        doc = self._make_tapo_doc(vitales={"hambre": 0, "energia": 0, "salud": 0, "independencia": 0})
        vida_antes = doc["Estadistica"]["vida"]
        doc_out, _ = aplicar_degradacion(doc, 1)

        assert doc_out["Estadistica"]["vida"] < vida_antes

    def test_no_degrada_si_muerto(self):
        """Si la mascota tiene vida == 0, no se degrada más."""
        doc = self._make_tapo_doc(estadistica={"vida": 0})
        doc_out, _ = aplicar_degradacion(doc, 10)

        assert doc_out["Estadistica"]["vida"] == 0

    def test_degradacion_acumulativa(self):
        """Múltiples ticks degradan acumulativamente (sin acciones autónomas)."""
        doc = self._make_tapo_doc(vitales={"independencia": 0})
        doc_out, _ = aplicar_degradacion(doc, 3)

        assert doc_out["Vitales"]["hambre"]    == 100 + (TICK_HAMBRE * 3)     # 85
        assert doc_out["Vitales"]["energia"]   == 100 + (TICK_ENERGIA * 3)    # 91
        assert doc_out["Vitales"]["felicidad"] == 100 + (TICK_FELICIDAD * 3)  # 88
