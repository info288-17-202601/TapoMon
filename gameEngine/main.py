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
from ui.console_ui import form_forgot_password
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

    # Paso 1: validar credenciales → recibir challenge 2FA
    print("  ☁️  Verificando credenciales...")
    challenge = sync_client.login(username, password)

    if not challenge:
        ui.mensaje_error("Credenciales incorrectas o el servidor no está disponible.")
        return None

    session_id  = challenge["session_id"]
    correo_hint = challenge["correo_hint"]

    # Paso 2: pedir el código al usuario y verificarlo
    codigo = ui.form_2fa_code(correo_hint)
    print("  ☁️  Verificando código 2FA...")
    auth_data = sync_client.verify_2fa(session_id, codigo)

    if not auth_data:
        ui.mensaje_error("Código incorrecto o expirado. Vuelve a intentarlo.")
        return None

    usuario_id = auth_data["usuario_id"]
    correo     = auth_data["correo"]
    tapo_id    = auth_data["tapo_id"]

    # Descargar estado actualizado desde el servidor
    server_state = sync_client.resume(usuario_id)
    if not server_state or not server_state.get("tapo"):
        ui.mensaje_error("No se pudo obtener el estado de la mascota desde el servidor.")
        return None

    from models.usuario import Usuario
    usuario = Usuario(id=usuario_id, username=username, correo=correo, tapo_id=tapo_id)
    usuario.set_password(password)

    tapo = Tapo.from_dict(server_state["tapo"])

    # Upsert a DB local: permite loguearse desde otra máquina sin problemas
    local_db.guardar_usuario(usuario)
    local_db.guardar_tapo(tapo)
    local_db._crear_indices()

    print("  ☁️  Perfil y estado sincronizados desde el servidor.")
    return usuario, tapo


def flujo_registro() -> tuple | None:
    """Registra un usuario nuevo y retorna (usuario, tapo)."""
    username, correo, password, nombre_tapo, tipo = ui.form_registro()

    import uuid
    from models.tapo import TipoTapo
    usuario_id = str(uuid.uuid4())
    tapo_id = str(uuid.uuid4())

    print("  ☁️  Registrando cuenta en el servidor central...")
    auth_data = sync_client.register(
        username=username,
        correo=correo,
        password=password,
        usuario_id=usuario_id,
        tapo_id=tapo_id,
    )

    if not auth_data:
        ui.mensaje_error("Error al registrar. El usuario ya existe o el servidor no está disponible.")
        return None

    # Si el servidor acepta, creamos los objetos localmente
    from models.usuario import Usuario
    from models.tapo import Vitales, Estadistica
    
    usuario = Usuario(id=usuario_id, username=username, correo=correo, tapo_id=tapo_id)
    usuario.set_password(password)

    tipo_enum = TipoTapo(tipo) if hasattr(TipoTapo, tipo) else TipoTapo.NORMAL
    tapo = Tapo(
        id_mascota=tapo_id,
        nombre=nombre_tapo,
        vitales=Vitales(),
        estadistica=Estadistica(tipo=tipo_enum),
    )

    local_db.guardar_usuario(usuario)
    local_db.guardar_tapo(tapo)
    local_db._crear_indices()

    # Subir el estado inicial
    sync_client.upload_state(tapo)

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


def flujo_forgot_password() -> None:
    """Flujo de recuperación de contraseña por consola."""
    correo = form_forgot_password()
    if not correo:
        ui.mensaje_error("Correo no ingresado.")
        return

    print("  ☁️  Enviando solicitud al servidor...")
    ok = sync_client.forgot_password(correo)
    if ok:
        ui.mensaje_ok(
            "Si el correo está registrado, recibirás un enlace de recuperación.\n"
            "  Revisa tu bandeja de entrada (y la carpeta de spam)."
        )
    else:
        ui.mensaje_error("No se pudo conectar con el servidor. Inténtalo más tarde.")


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
        elif opcion == "3":
            flujo_forgot_password()
            continue
        else:
            ui.mensaje_error("Opción no válida.")
            continue

        if resultado:
            usuario, tapo = resultado
            tapo.estado_sistema = True   # marcar como ACTIVE
            bucle_juego(usuario, tapo)


if __name__ == "__main__":
    main()
