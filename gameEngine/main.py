"""
main.py
Punto de entrada de TapoMon — versión consola.
Orquesta el flujo: login / registro → bucle de juego.
"""
from __future__ import annotations
import sys
import os
import time

# Permite importar módulos relativos desde cualquier directorio
sys.path.insert(0, os.path.dirname(__file__))

from db import local_db
from engine import game_engine as ge
from ui import console_ui as ui
from models.tapo import Tapo
from network.sync_client import SyncClient
from p2pEngine.battle_cli import menu_batalla


# ------------------------------------------------------------------ #
#  Cliente de sincronización con el servidor central
# ------------------------------------------------------------------ #
sync_client = SyncClient()


# ------------------------------------------------------------------ #
#  Flujo de autenticación
# ------------------------------------------------------------------ #

def flujo_login() -> tuple | None:
    """Retorna (usuario, tapo) o None si falla."""
    username, password = ui.form_login()
    usuario = local_db.buscar_usuario_por_username(username)

    if usuario is None or not usuario.check_password(password):
        ui.mensaje_error("Usuario o contraseña incorrectos.")
        return None

    # Autenticar con el servidor central (obtiene JWT)
    sync_client.login(username, password)

    # Intentar descargar estado actualizado desde el servidor
    if sync_client.is_connected():
        server_state = sync_client.resume(usuario.id)
        if server_state and server_state.get("tapo"):
            tapo = Tapo.from_dict(server_state["tapo"])
            local_db.guardar_tapo(tapo)
            print("  ☁️  Estado sincronizado desde el servidor.")
            return usuario, tapo

    # Fallback: cargar desde DB local
    tapo = local_db.cargar_tapo(usuario.tapo_id)
    if tapo is None:
        ui.mensaje_error("No se encontró la mascota asociada a este usuario.")
        return None

    return usuario, tapo


def flujo_registro() -> tuple | None:
    """Registra un usuario nuevo y retorna (usuario, tapo)."""
    username, correo, password, nombre_tapo, tipo = ui.form_registro()

    if local_db.buscar_usuario_por_username(username):
        ui.mensaje_error("Ese nombre de usuario ya existe.")
        return None

    usuario, tapo = local_db.registrar_nuevo_usuario(
        username, correo, password, nombre_tapo, tipo
    )

    # Replicar la cuenta en el servidor central para que el sync funcione.
    # Si el servidor no está disponible, la cuenta queda solo en la DB local
    # y el juego continúa en modo offline sin interrupciones.
    sync_client.register(
        username=username,
        correo=correo,
        password=password,
        usuario_id=usuario.id,
        tapo_id=tapo.id_mascota,
    )

    ui.mensaje_ok(f"¡Cuenta creada! Bienvenido, {username}. Tu Tapo '{nombre_tapo}' te espera.")
    return usuario, tapo


def flujo_nueva_mascota(usuario) -> Tapo:
    nombre_tapo, tipo = ui.form_nueva_mascota()
    tapo = local_db.registrar_nueva_mascota(usuario, nombre_tapo, tipo)
    ui.mensaje_ok(f"¡Nueva mascota creada! Tu Tapo '{nombre_tapo}' te espera.")
    return tapo


# ------------------------------------------------------------------ #
#  Bucle principal de juego
# ------------------------------------------------------------------ #

def bucle_juego(usuario, tapo: Tapo) -> None:
    """Loop de juego para un usuario autenticado."""

    # Al volver a conectarse, aplicar degradación idle sin mostrar mensajes
    ge.aplicar_idle(tapo)

    if ge.verificar_muerte(tapo):
        ui.pantalla_muerte(tapo.nombre)
        local_db.guardar_tapo(tapo)
        ui.pausar("Presiona Enter para crear una nueva mascota...")
        tapo = flujo_nueva_mascota(usuario)

    ACCIONES = {
        "1": ge.alimentar,
        "2": ge.jugar,
        "3": ge.curar,
        "4": ge.entrenar_fuerza,
        "5": ge.entrenar_defensa,
        "6": ge.entrenar_velocidad,
        "7": ge.entrenar_resistencia,
    }

    # Acción especial: combate P2P (no es un lambda de ge, se trata aparte)
    ACCION_COMBATE = "9"

    last_msgs: list[str] = []

    def _leer_opcion_realtime() -> str:
        if os.name != "nt":
            return ui.menu_acciones()

        import msvcrt

        validas = set(list(ACCIONES.keys()) + ["0", "8", ACCION_COMBATE])
        ultimo_tick = time.time()

        while True:
            if msvcrt.kbhit():
                tecla = msvcrt.getwch()
                if tecla in validas:
                    return tecla

            ahora = time.time()
            elapsed = ahora - ultimo_tick
            if elapsed >= ge.REALTIME_SECONDS_PER_TICK:
                ticks = int(elapsed // ge.REALTIME_SECONDS_PER_TICK)
                ge.aplicar_realtime_ticks(tapo, ticks)
                ultimo_tick += ticks * ge.REALTIME_SECONDS_PER_TICK

                datos = ge.resumen_estado(tapo)
                ui.pantalla_estado_mascota(datos)
                if last_msgs:
                    ui.mostrar_mensajes(last_msgs)
                ui.menu_acciones_realtime()

            time.sleep(0.1)

    while True:
        # Verificar si la mascota sigue viva
        if ge.verificar_muerte(tapo):
            ui.pantalla_muerte(tapo.nombre)
            local_db.guardar_tapo(tapo)
            ui.pausar("Presiona Enter para crear una nueva mascota...")
            tapo = flujo_nueva_mascota(usuario)
            continue

        # Mostrar estado actual
        datos = ge.resumen_estado(tapo)
        ui.pantalla_estado_mascota(datos)
        if last_msgs:
            ui.mostrar_mensajes(last_msgs)
        if os.name == "nt":
            ui.menu_acciones_realtime()
        opcion = _leer_opcion_realtime()

        if opcion == "0":
            # Cerrar sesión: marcar como IDLE y guardar
            tapo.estado_sistema = False
            local_db.guardar_tapo(tapo)
            local_db.guardar_usuario(usuario)
            # Enviar snapshot al servidor central
            if sync_client.is_connected():
                sync_client.upload_state(tapo)
            ui.mensaje_ok("Sesión cerrada. ¡Tu Tapo te esperará!")
            break

        elif opcion in ACCIONES:
            msgs = ACCIONES[opcion](tapo)
            last_msgs = msgs
            local_db.guardar_tapo(tapo)   # persistir tras cada acción

        elif opcion == ACCION_COMBATE:
            # Entrar al menú de combate P2P
            menu_batalla(tapo)

        elif opcion == "8":
            # Solo refrescar la pantalla
            pass

        else:
            ui.mensaje_error("Opción no válida.")


# ------------------------------------------------------------------ #
#  Menú principal
# ------------------------------------------------------------------ #

def main() -> None:
    while True:
        ui.pantalla_bienvenida()
        opcion = input("  Opción: ").strip()

        if opcion == "0":
            print("\n  ¡Hasta pronto!\n")
            sys.exit(0)

        resultado = None

        if opcion == "1":
            resultado = flujo_login()
        elif opcion == "2":
            resultado = flujo_registro()
        else:
            ui.mensaje_error("Opción no válida.")
            continue

        if resultado:
            usuario, tapo = resultado
            tapo.estado_sistema = True   # marcar como ACTIVE
            bucle_juego(usuario, tapo)


if __name__ == "__main__":
    main()
