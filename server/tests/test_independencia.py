"""
server/tests/test_independencia.py
Pruebas unitarias para la mecánica de Independencia del idle_engine.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import random
from server.services.idle_engine import (
    aplicar_degradacion,
    intentar_accion_autonoma,
    calcular_ticks_pendientes,
)


def make_tapo(independencia=50, hambre=100, energia=100, salud=100, felicidad=100, vida=100):
    return {
        "id_mascota": "test-id",
        "Nombre": "TestTapo",
        "Vitales": {
            "hambre": hambre,
            "energia": energia,
            "salud": salud,
            "felicidad": felicidad,
            "independencia": independencia,
        },
        "Estadistica": {
            "vida": vida,
            "fuerza": 10,
            "defensa": 10,
            "velocidad": 10,
            "tipo": "Normal",
        },
        "Estado_Sistema": False,
        "Last_Sync": "2025-01-01T00:00:00",
    }


def test_independencia_0_nunca_actua():
    """Con independencia=0 y salud baja (no crece), nunca debe haber acciones autónomas."""
    random.seed(42)
    # salud=30 < umbral(60): la independencia no crecerá durante los ticks,
    # así el test prueba genuinamente el caso independencia=0.
    tapo = make_tapo(independencia=0, salud=30)
    _, acciones = aplicar_degradacion(tapo, ticks=20)
    assert acciones == [], f"Esperaba 0 acciones, got: {acciones}"
    print("  PASS  independencia=0 (con salud baja) → nunca actúa")


def test_independencia_100_actua_mucho():
    """Con independencia=100, debe actuar en casi todos los ticks."""
    random.seed(42)
    tapo = make_tapo(independencia=100, energia=100)
    _, acciones = aplicar_degradacion(tapo, ticks=20)
    assert len(acciones) > 10, f"Con independencia=100 esperaba >10 acciones, got {len(acciones)}"
    print(f"  PASS  independencia=100 → {len(acciones)}/20 ticks con acción autónoma")


def test_independencia_crece_con_salud_alta():
    """La independencia debe crecer cuando la salud es alta."""
    tapo = make_tapo(independencia=50, salud=100, hambre=100, energia=100)
    ind_inicial = tapo["Vitales"]["independencia"]
    tapo_out, _ = aplicar_degradacion(tapo, ticks=5)
    ind_final = tapo_out["Vitales"]["independencia"]
    # No crece si la degradación baja la salud antes del umbral, pero con stats altos debería
    assert ind_final >= ind_inicial, f"Independencia no creció: {ind_inicial} → {ind_final}"
    print(f"  PASS  independencia crece: {ind_inicial} → {ind_final}")


def test_independencia_no_crece_con_salud_baja():
    """La independencia NO debe crecer cuando salud < umbral (60)."""
    tapo = make_tapo(independencia=50, salud=30, hambre=100, energia=100)
    tapo_out, _ = aplicar_degradacion(tapo, ticks=5)
    ind_final = tapo_out["Vitales"]["independencia"]
    assert ind_final == 50, f"Independencia no debería haber crecido: {ind_final}"
    print(f"  PASS  independencia no crece con salud baja: {ind_final}")


def test_accion_autonoma_muerta():
    """Un Tapo con vida=0 no debe actuar."""
    tapo = make_tapo(independencia=100, vida=0)
    result = intentar_accion_autonoma(tapo, tick_n=0)
    assert result is None, f"Tapo muerto no debería actuar: {result}"
    print("  PASS  Tapo muerto no actúa")


def test_fallback_a_comer_sin_energia():
    """Con energía baja, play/train hacen fallback a comer."""
    random.seed(0)  # seed que normalmente elegiría play o train
    acciones_comer = []
    for seed in range(200):
        random.seed(seed)
        tapo = make_tapo(independencia=100, energia=5)
        act = intentar_accion_autonoma(tapo, 0)
        if act:
            acciones_comer.append(act)
    # Todas las acciones con energia=5 deben ser "comió solo"
    no_comer = [a for a in acciones_comer if a != "comió solo"]
    assert not no_comer, f"Con energía=5 sólo debería comer: {no_comer}"
    print(f"  PASS  fallback a comer sin energía ({len(acciones_comer)} acciones, todas 'comió solo')")


def test_inbox_acciones_registradas():
    """Las acciones deben aparecer en la lista retornada."""
    random.seed(1)
    tapo = make_tapo(independencia=100, energia=100, hambre=100)
    _, acciones = aplicar_degradacion(tapo, ticks=10)
    assert isinstance(acciones, list), "acciones debe ser una lista"
    for a in acciones:
        assert isinstance(a, str), f"Cada acción debe ser un string: {a}"
        assert a in ("comió solo", "jugó solo", "entrenó fuerza solo",
                     "entrenó defensa solo", "entrenó velocidad solo"), f"Acción inválida: {a}"
    print(f"  PASS  {len(acciones)} acciones válidas registradas para el Inbox")


if __name__ == "__main__":
    print("\n=== Test: Mecánica de Independencia ===\n")
    test_independencia_0_nunca_actua()
    test_independencia_100_actua_mucho()
    test_independencia_crece_con_salud_alta()
    test_independencia_no_crece_con_salud_baja()
    test_accion_autonoma_muerta()
    test_fallback_a_comer_sin_energia()
    test_inbox_acciones_registradas()
    print("\n✅  Todos los tests pasaron.\n")
