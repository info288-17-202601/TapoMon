"""
p2pEngine/p2p_client.py
Challenger del combate P2P. Se conecta al host en la red local
y ejecuta el combate desde el lado del atacante secundario.

Uso:
    python p2p_client.py  (desde dentro del venv con sys.path configurado)
"""
from __future__ import annotations

import socket
import sys
import os
import time

# Permite importar módulos del proyecto (models, etc.)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.tapo import Tapo
from p2pEngine.p2p_protocol import (
    Mensaje, MsgType,
    msg_hello, msg_ready,
    msg_attack_roll, msg_defense_roll, msg_damage,
    msg_turn_end, msg_surrender,
)
from p2pEngine.combat_engine import (
    calcular_attack_roll, calcular_armor_class, calcular_dano,
    EstadoCombate, TURN_DELAY_SEC,
)
from p2pEngine.p2p_server import ConexionP2P   # reutilizamos la clase de transporte

DEFAULT_PORT = 55201
TIMEOUT_SEC  = 60.0


class ClienteCombate:
    """
    Gestiona la sesión de combate desde el lado del challenger.
    El challenger es quien inicia la conexión.
    """

    def __init__(
        self,
        tapo_local: Tapo,
        host_ip: str,
        port: int = DEFAULT_PORT,
        callback_log=None,
    ) -> None:
        self.tapo_local   = tapo_local
        self.host_ip      = host_ip
        self.port         = port
        self._log         = callback_log or print
        self._conn: ConexionP2P | None = None
        self.estado: EstadoCombate | None = None
        self._corriendo   = False

    # ---------------------------------------------------------------- #
    #  Arranque
    # ---------------------------------------------------------------- #

    def conectar(self) -> None:
        """Se conecta al host, realiza el handshake y ejecuta el combate."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_SEC)
        self._log(f"[CLIENT] Conectando a {self.host_ip}:{self.port}...")
        sock.connect((self.host_ip, self.port))
        self._log(f"[CLIENT] Conectado al host.")
        self._conn = ConexionP2P(sock)
        self._corriendo = True

        try:
            self._fase_handshake()
            if self._corriendo:
                self._bucle_combate()
        except (ConnectionError, TimeoutError) as e:
            self._log(f"[CLIENT] Conexión perdida: {e}")
        finally:
            if self._conn:
                self._conn.cerrar()

    # ---------------------------------------------------------------- #
    #  Handshake
    # ---------------------------------------------------------------- #

    def _fase_handshake(self) -> None:
        self._conn.enviar(msg_hello(self.tapo_local.to_dict()))
        self._log(f"[CLIENT] HELLO enviado con {self.tapo_local.nombre}")

        resp = self._conn.recibir()
        if resp.tipo == MsgType.REJECT:
            self._log(f"[CLIENT] El host rechazó el combate: {resp.payload.get('razon', '')}")
            self._corriendo = False
            return

        if resp.tipo != MsgType.HELLO_ACK:
            self._log(f"[CLIENT] Respuesta inesperada: {resp.tipo}")
            self._corriendo = False
            return

        if not resp.payload.get("acepta", False):
            self._log("[CLIENT] El host rechazó el combate.")
            self._corriendo = False
            return

        tapo_host = Tapo.from_dict(resp.payload["tapo"])
        self._log(f"[CLIENT] Host presenta a: {tapo_host.nombre} ({tapo_host.estadistica.tipo.value})")

        # Crear estado de combate: el challenger defiende primero (host ataca primero)
        self.estado = EstadoCombate(self.tapo_local, tapo_host)
        self.estado.es_atacante = False

        self._conn.enviar(msg_ready())
        self._log("[CLIENT] READY enviado — esperando READY del host...")

        resp2 = self._conn.recibir()
        if resp2.tipo != MsgType.READY:
            self._log("[CLIENT] No se recibió READY del host.")
            self._corriendo = False
            return

        self._log("[CLIENT] ¡Combate iniciado!")

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

        # Escuchar GAME_OVER del host si no terminamos localmente
        if not estado.batalla_terminada:
            try:
                msg = self._conn.recibir()
                if msg.tipo == MsgType.GAME_OVER:
                    ganador = msg.payload.get("ganador", "?")
                    self._log(f"\nGanador: {ganador}")
            except Exception:
                pass
        else:
            ganador = self.tapo_local.nombre if estado.ganador_local else estado.tapo_rival.nombre
            self._log(f"\nGanador: {ganador}")

    # ---------------------------------------------------------------- #
    #  Turno como atacante
    # ---------------------------------------------------------------- #

    def _turno_atacar(self) -> None:
        estado   = self.estado
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

        self._conn.enviar(msg_attack_roll(
            atk_info["resultado"],
            tiene_ventaja=atk_info["ventaja_tipo"] == "ventaja",
            tiene_desventaja=atk_info["ventaja_tipo"] == "desventaja",
        ))

        # Esperar AC del defensor
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

        msg = self._conn.recibir()
        if msg.tipo == MsgType.SURRENDER:
            self._log(f"   {atacante.nombre} se rindió.")
            estado.hp_rival = 0
            self._corriendo = False
            return
        if msg.tipo == MsgType.GAME_OVER:
            ganador = msg.payload.get("ganador", "?")
            self._log(f"\nGanador: {ganador}")
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

        # Esperar daño
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
        """Permite al challenger rendirse en cualquier momento."""
        if self._conn:
            self._conn.enviar(msg_surrender())
        self._corriendo = False
