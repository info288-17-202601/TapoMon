"""
p2pEngine/p2p_server.py
Host del combate P2P. Escucha en la red local, acepta la conexión
del challenger y coordina los turnos de batalla.

Uso:
    python p2p_server.py  (desde dentro del venv con sys.path configurado)
"""
from __future__ import annotations

import socket
import threading
import sys
import os
import time

# Permite importar módulos del proyecto (models, etc.)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.tapo import Tapo
from p2pEngine.p2p_protocol import (
    Mensaje, MsgType,
    msg_hello_ack, msg_reject, msg_ready,
    msg_attack_roll, msg_defense_roll, msg_damage,
    msg_turn_end, msg_game_over, msg_surrender,
    msg_ping, msg_pong, msg_error,
)
from p2pEngine.combat_engine import (
    calcular_attack_roll, calcular_armor_class, calcular_dano,
    EstadoCombate, TURN_DELAY_SEC,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 55201
BUFFER_SIZE  = 4096
TIMEOUT_SEC  = 60.0


# ------------------------------------------------------------------ #
#  Capa de transporte
# ------------------------------------------------------------------ #

class ConexionP2P:
    """Wrapper sobre socket TCP con envío/recepción de Mensajes."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock   = sock
        self._buffer = b""

    def enviar(self, msg: Mensaje) -> None:
        self._sock.sendall(msg.encode())

    def recibir(self) -> Mensaje:
        """Recibe el siguiente mensaje (bloqueante, separado por '\\n')."""
        while b"\n" not in self._buffer:
            chunk = self._sock.recv(BUFFER_SIZE)
            if not chunk:
                raise ConnectionError("La conexión fue cerrada por el par.")
            self._buffer += chunk

        linea, self._buffer = self._buffer.split(b"\n", 1)
        return Mensaje.decode(linea)

    def cerrar(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------ #
#  Lógica del servidor (host)
# ------------------------------------------------------------------ #

class ServidorCombate:
    """
    Gestiona la sesión de combate desde el lado del host.
    El host es quien acepta la conexión entrante.
    """

    def __init__(
        self,
        tapo_local: Tapo,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        callback_log=None,
    ) -> None:
        self.tapo_local   = tapo_local
        self.host         = host
        self.port         = port
        self._log         = callback_log or print
        self._conn: ConexionP2P | None = None
        self.estado: EstadoCombate | None = None
        self._corriendo   = False

    # ---------------------------------------------------------------- #
    #  Arranque
    # ---------------------------------------------------------------- #

    def iniciar(self) -> None:
        """Abre el socket, espera al challenger y ejecuta el combate."""
        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv_sock.bind((self.host, self.port))
        srv_sock.listen(1)

        ip_local = socket.gethostbyname(socket.gethostname())
        self._log(f"[HOST] Escuchando en {ip_local}:{self.port} — esperando challenger...")

        client_sock, addr = srv_sock.accept()
        srv_sock.close()
        client_sock.settimeout(TIMEOUT_SEC)

        self._log(f"[HOST] Challenger conectado desde {addr[0]}:{addr[1]}")
        self._conn = ConexionP2P(client_sock)
        self._corriendo = True

        try:
            self._fase_handshake()
            if self._corriendo:
                self._bucle_combate()
        except (ConnectionError, TimeoutError) as e:
            self._log(f"[HOST] Conexión perdida: {e}")
        finally:
            if self._conn:
                self._conn.cerrar()

    # ---------------------------------------------------------------- #
    #  Handshake
    # ---------------------------------------------------------------- #

    def _fase_handshake(self) -> None:
        msg = self._conn.recibir()
        if msg.tipo != MsgType.HELLO:
            self._conn.enviar(msg_reject("Se esperaba HELLO"))
            self._corriendo = False
            return

        tapo_rival_dict = msg.payload["tapo"]
        tapo_rival      = Tapo.from_dict(tapo_rival_dict)
        self._log(f"[HOST] Challenger presenta a: {tapo_rival.nombre} ({tapo_rival.estadistica.tipo.value})")

        # Crear estado de combate: el host ataca primero
        self.estado = EstadoCombate(self.tapo_local, tapo_rival)
        self.estado.es_atacante = True

        ack = msg_hello_ack(self.tapo_local.to_dict(), acepta=True)
        self._conn.enviar(ack)
        self._log("[HOST] Enviado HELLO_ACK — esperando READY...")

        msg2 = self._conn.recibir()
        if msg2.tipo != MsgType.READY:
            self._log("[HOST] No se recibió READY, abortando.")
            self._corriendo = False
            return

        self._conn.enviar(msg_ready())
        self._log("[HOST] ¡Combate iniciado!")

    # ---------------------------------------------------------------- #
    #  Bucle de combate
    # ---------------------------------------------------------------- #

    def _bucle_combate(self) -> None:
        estado = self.estado

        while self._corriendo and not estado.batalla_terminada:
            if estado.es_atacante:
                self._turno_atacar()
            else:
                self._turno_defender()

            if not estado.batalla_terminada:
                time.sleep(TURN_DELAY_SEC)
                estado.siguiente_turno()

        # Fin de batalla
        if estado.batalla_terminada:
            ganador = self.tapo_local.nombre if estado.ganador_local else estado.tapo_rival.nombre
            self._conn.enviar(msg_game_over(ganador))
            self._log(f"\nGanador: {ganador}")

    # ---------------------------------------------------------------- #
    #  Turno como atacante
    # ---------------------------------------------------------------- #

    def _turno_atacar(self) -> None:
        estado  = self.estado
        atacante = estado.tapo_local
        defensor = estado.tapo_rival

        self._log(f"\nTurno {estado.turno + 1} — {atacante.nombre} ATACA")

        atk_info = calcular_attack_roll(atacante, defensor)
        self._log(
            f"   D20: {atk_info['tiradas']}  "
            f"+ mod_vel({atk_info['mod_vel']}) "
            f"= {atk_info['resultado']}  "
            f"[{atk_info['ventaja_tipo'] or 'normal'}]"
        )

        msg_atk = msg_attack_roll(
            atk_info["resultado"],
            tiene_ventaja=atk_info["ventaja_tipo"] == "ventaja",
            tiene_desventaja=atk_info["ventaja_tipo"] == "desventaja",
        )
        self._conn.enviar(msg_atk)

        # Esperar la AC del defensor
        resp = self._conn.recibir()
        if resp.tipo == MsgType.SURRENDER:
            self._log(f"   {defensor.nombre} se rindió.")
            estado.hp_rival = 0
            self._corriendo = False
            return
        if resp.tipo != MsgType.DEFENSE_ROLL:
            self._log(f"   Mensaje inesperado: {resp.tipo}")
            return

        ac = resp.payload["armor_class"]
        self._log(f"   AC de {defensor.nombre}: {ac}")

        golpeo = atk_info["resultado"] >= ac
        if golpeo:
            dano_info = calcular_dano(atacante, defensor, atk_info["ventaja_tipo"])
            dano      = dano_info["dano"]
            mult_str  = f" ×{dano_info['multiplicador']}" if dano_info["multiplicador"] != 1.0 else ""
            self._log(
                f"   GOLPE! D6={dano_info['d6']} "
                f"+{dano_info['mod_atk']} -{dano_info['mod_def']}"
                f" = {dano_info['dano_base']}{mult_str} → {dano} daño"
            )
            estado.aplicar_dano_a_rival(dano)
        else:
            dano = 0
            self._log(f"   Fallo. {atk_info['resultado']} < AC {ac}")

        self._conn.enviar(msg_damage(dano, golpeo))

        # Turno finalizado — sincronizar HP
        self._conn.enviar(msg_turn_end(estado.hp_local, estado.hp_rival))
        self._log(f"   HP {atacante.nombre}: {estado.hp_local}  |  HP {defensor.nombre}: {estado.hp_rival}")

    # ---------------------------------------------------------------- #
    #  Turno como defensor
    # ---------------------------------------------------------------- #

    def _turno_defender(self) -> None:
        estado   = self.estado
        atacante = estado.tapo_rival
        defensor = estado.tapo_local

        self._log(f"\nTurno {estado.turno + 1} — {defensor.nombre} DEFIENDE")

        # Esperar el attack roll del rival
        msg = self._conn.recibir()
        if msg.tipo == MsgType.SURRENDER:
            self._log(f"   {atacante.nombre} se rindió.")
            estado.hp_rival = 0
            self._corriendo = False
            return
        if msg.tipo != MsgType.ATTACK_ROLL:
            self._log(f"   Mensaje inesperado: {msg.tipo}")
            return

        resultado_atk = msg.payload["resultado"]
        self._log(f"   {atacante.nombre} tiró: {resultado_atk}")

        ac = calcular_armor_class(defensor)
        self._conn.enviar(msg_defense_roll(ac))
        self._log(f"   AC enviada: {ac}")

        # Esperar resultado del daño
        msg_dmg = self._conn.recibir()
        if msg_dmg.tipo != MsgType.DAMAGE:
            return

        golpeo = msg_dmg.payload["golpeo"]
        dano   = msg_dmg.payload["dano"]

        if golpeo:
            estado.aplicar_dano_a_local(dano)
            self._log(f"   Recibimos {dano} de daño.")
        else:
            self._log(f"   {defensor.nombre} esquivó el ataque.")

        # Recibir fin de turno
        msg_te = self._conn.recibir()
        if msg_te.tipo == MsgType.TURN_END:
            self._log(
                f"   HP {defensor.nombre}: {estado.hp_local}  "
                f"|  HP {atacante.nombre}: {estado.hp_rival}"
            )

    def rendirse(self) -> None:
        """Permite al host rendirse en cualquier momento."""
        if self._conn:
            self._conn.enviar(msg_surrender())
        self._corriendo = False
