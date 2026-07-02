"""
ui/console_ui.py
Interfaz de usuario en consola para TapoMon.
Toda la interacción ocurre mediante texto en la terminal.
"""
from __future__ import annotations
import os
import sys
from models.tapo import TipoTapo
from engine.game_engine import resumen_estado


# ------------------------------------------------------------------ #
#  Helpers de pantalla
# ------------------------------------------------------------------ #

def limpiar() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def separador(char: str = "─", ancho: int = 50) -> None:
    print(char * ancho)


def titulo(texto: str) -> None:
    limpiar()
    separador("═")
    print(f"  🐾  TapoMon  —  {texto}")
    separador("═")
    print()


def pausar(mensaje: str = "Presiona Enter para continuar...") -> None:
    input(f"\n{mensaje}")


def mostrar_mensajes(msgs: list[str]) -> None:
    for m in msgs:
        print(f"  {m}")


# ------------------------------------------------------------------ #
#  Barra de progreso ASCII
# ------------------------------------------------------------------ #

def barra(valor: int, maximo: int = 100, largo: int = 20) -> str:
    lleno = int((valor / maximo) * largo)
    return f"[{'█' * lleno}{'░' * (largo - lleno)}] {valor}/{maximo}"


# ------------------------------------------------------------------ #
#  Pantallas
# ------------------------------------------------------------------ #

BANNER = r"""
  ___________    ____  ____  __  ___            
 |_   _/ _  |  |  _ \/ __ \|  \/  |           
   | || (_| |  | |_) | |  | | \  / | ___  _ __ 
   | | \__,_|  |  __/| |  | | |\/| |/ _ \| '_ \
  _| |_       | |   | |__| | |  | | (_) | | | |
 |_____|      |_|    \____/|_|  |_|\___/|_| |_|
"""


def pantalla_bienvenida() -> None:
    limpiar()
    separador("═")
    print(BANNER)
    separador("═")
    print()
    print("  Bienvenido a TapoMon — tu mascota virtual distribuida")
    print()
    print("  [1] Iniciar sesión")
    print("  [2] Registrarse")
    print("  [3] ¿Olvidaste tu contraseña?")
    print("  [0] Salir")
    print()


def pantalla_estado_mascota(tapo_data: dict) -> None:
    titulo(f"Mi Tapo: {tapo_data['nombre']}  [{tapo_data['tipo']}]")

    print(f"    Vida:      {barra(tapo_data['vida'])}")
    print(f"    Hambre:   {barra(tapo_data['hambre'])}")
    print(f"    Energía:  {barra(tapo_data['energia'])}")
    print(f"    Felicid.: {barra(tapo_data['felicidad'])}")
    print(f"    Salud:    {barra(tapo_data['salud'])}")
    print()
    print("    Estadísticas")
    print(f"    Fuerza:    {tapo_data['fuerza']}")
    print(f"    Defensa:   {tapo_data['defensa']}")
    print(f"    Velocidad: {tapo_data['velocidad']}")
    print()
    separador()
    print(f"  Estado: {tapo_data['estado']}   Última sync: {tapo_data['last_sync']}")
    separador()


def menu_acciones() -> str:
    print()
    print("  ¿Qué quieres hacer?")
    print()
    print("  [1] 🍖  Alimentar")
    print("  [2] 🎮  Jugar")
    print("  [3] 💊  Curar")
    print("  [4] 🏋️  Entrenar fuerza")
    print("  [5] 🛡️  Entrenar defensa")
    print("  [6] ⚡  Entrenar velocidad")
    print("  [7] 💪  Entrenar resistencia")
    print("  [8] 🔄  Actualizar estado")
    print("  [9] ⚔️  Batalla P2P")
    print("  [0] 🚪  Cerrar sesión")
    print()
    return input("  Opción: ").strip()


def menu_acciones_realtime() -> None:
    print()
    print("  ¿Qué quieres hacer?")
    print()
    print("  [1] 🍖  Alimentar")
    print("  [2] 🎮  Jugar")
    print("  [3] 💊  Curar")
    print("  [4] 🏋️  Entrenar fuerza")
    print("  [5] 🛡️  Entrenar defensa")
    print("  [6] ⚡  Entrenar velocidad")
    print("  [7] 💪  Entrenar resistencia")
    print("  [8] 🔄  Actualizar estado")
    print("  [9] ⚔️  Batalla P2P")
    print("  [0] 🚪  Cerrar sesión")
    print()
    print("  Presiona un numero para elegir una opcion...")


def pantalla_muerte(nombre: str) -> None:
    titulo(f"💀 {nombre} ha muerto")
    print("  Tu mascota llegó a 0 puntos de vida.")
    print("  Deberás crear una nueva mascota para continuar.")
    print()


# ------------------------------------------------------------------ #
#  Formularios
# ------------------------------------------------------------------ #

def form_login() -> tuple[str, str]:
    titulo("Iniciar sesión")
    username = input("  Usuario: ").strip()
    password = input("  Contraseña: ").strip()
    return username, password


def form_registro() -> tuple[str, str, str, str, TipoTapo]:
    titulo("Crear cuenta")
    username   = input("  Nombre de usuario: ").strip()
    correo     = input("  Correo electrónico: ").strip()
    password   = input("  Contraseña: ").strip()
    nombre_tapo= input("  Nombre de tu Tapo: ").strip()

    print()
    print("  Elige el tipo de tu Tapo:")
    tipos = list(TipoTapo)
    for i, t in enumerate(tipos, 1):
        print(f"    [{i}] {t.value}")
    print()

    while True:
        try:
            idx = int(input("  Opción: ").strip()) - 1
            tipo = tipos[idx]
            break
        except (ValueError, IndexError):
            print("  Opción inválida, intenta de nuevo.")

    return username, correo, password, nombre_tapo, tipo


def form_forgot_password() -> str:
    titulo("🔑 Recuperar contraseña")
    print("  Ingresa el correo electrónico asociado a tu cuenta.")
    print("  Recibirás un enlace para restablecer tu contraseña.")
    print()
    correo = input("  Correo electrónico: ").strip()
    return correo


def form_2fa_code(correo_hint: str = "") -> str:
    titulo("Verificación en dos pasos")
    if correo_hint:
        print(f"  Se envió un código de 6 dígitos a: {correo_hint}")
    print("  Revisa tu correo e ingresa el código:")
    print()
    codigo = input("  Código: ").strip()
    return codigo


def form_nueva_mascota() -> tuple[str, TipoTapo]:
    titulo("Nueva mascota")
    nombre_tapo = input("  Nombre de tu nuevo Tapo: ").strip()

    print()
    print("  Elige el tipo de tu Tapo:")
    tipos = list(TipoTapo)
    for i, t in enumerate(tipos, 1):
        print(f"    [{i}] {t.value}")
    print()

    while True:
        try:
            idx = int(input("  Opción: ").strip()) - 1
            tipo = tipos[idx]
            break
        except (ValueError, IndexError):
            print("  Opción inválida, intenta de nuevo.")

    return nombre_tapo, tipo


def mensaje_error(texto: str) -> None:
    print(f"\n  ❌  {texto}")
    pausar()


def mensaje_ok(texto: str) -> None:
    print(f"\n  ✅  {texto}")
    pausar()
