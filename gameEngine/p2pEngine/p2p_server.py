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
import queue
import asyncio
import json
import requests
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

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
    """Wrapper sobre WebRTC (aiortc) con envío/recepción de Mensajes en cola."""

    def __init__(self, puerto_local: int, host_ip: str | None = None, port: int | None = None, mode: str = "host") -> None:
        self.puerto_local = puerto_local
        self.host_ip = host_ip
        self.port = port
        self.mode = mode
        
        self._queue = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self.pc = None
        self.channel = None
        self._conn_established = threading.Event()
        self.signaling_server = None
        
        asyncio.run_coroutine_threadsafe(self._init_webrtc(), self.loop)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_webrtc(self) -> None:
        config = RTCConfiguration(
            iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
        )
        self.pc = RTCPeerConnection(configuration=config)
        
        if self.mode == "host":
            @self.pc.on("datachannel")
            def on_datachannel(channel):
                self.channel = channel
                self._setup_channel(channel)
            
            # Levantar servidor HTTP de señalización local
            self.signaling_server = await asyncio.start_server(
                self._handle_signaling, '0.0.0.0', self.puerto_local
            )
        else:
            self.channel = self.pc.createDataChannel("combat")
            self._setup_channel(self.channel)
            await self._connect_as_client()

    def _setup_channel(self, channel) -> None:
        if channel.readyState == "open":
            self._conn_established.set()

        @channel.on("open")
        def on_open():
            self._conn_established.set()
            
        @channel.on("message")
        def on_message(message):
            try:
                data = json.loads(message)
                self._queue.put((data["tipo"], data["payload"]))
            except Exception as e:
                print(f"Error al decodificar mensaje WebRTC: {e}")
            
        @channel.on("close")
        def on_close():
            self._conn_established.clear()

    async def _handle_signaling(self, reader, writer) -> None:
        try:
            data_req = b""
            while b"\r\n\r\n" not in data_req:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                data_req += chunk
            
            if not data_req:
                return
                
            header_part, body_part = data_req.split(b"\r\n\r\n", 1)
            
            content_length = 0
            for line in header_part.decode('utf-8', errors='ignore').split("\r\n"):
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break
            
            while len(body_part) < content_length:
                body_part += await reader.read(4096)
            
            body_json = json.loads(body_part.decode('utf-8'))
            offer = RTCSessionDescription(sdp=body_json["sdp"], type=body_json["type"])
            await self.pc.setRemoteDescription(offer)
            
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            
            while self.pc.iceGatheringState != 'complete':
                await asyncio.sleep(0.01)
            
            res_body = json.dumps({
                "sdp": self.pc.localDescription.sdp,
                "type": self.pc.localDescription.type
            }).encode('utf-8')
            
            res = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(res_body)).encode('utf-8') + b"\r\n"
                b"Connection: close\r\n\r\n" + res_body
            )
            writer.write(res)
            await writer.drain()
        except Exception as e:
            print(f"Error en señalización Host WebRTC: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            
            if self.signaling_server:
                self.signaling_server.close()

    async def _connect_as_client(self) -> None:
        try:
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            
            while self.pc.iceGatheringState != 'complete':
                await asyncio.sleep(0.01)
                
            payload = {
                "sdp": self.pc.localDescription.sdp,
                "type": self.pc.localDescription.type
            }
            
            def do_post():
                url = f"http://{self.host_ip}:{self.port}/offer"
                return requests.post(url, json=payload, timeout=10)
                
            resp = await self.loop.run_in_executor(None, do_post)
            
            if resp.status_code == 200:
                answer_json = resp.json()
                answer = RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"])
                await self.pc.setRemoteDescription(answer)
            else:
                raise ConnectionError(f"Servidor de señalización respondió con código {resp.status_code}")
        except Exception as e:
            print(f"Error al conectar como cliente WebRTC: {e}")

    def enviar(self, msg: Mensaje) -> None:
        """Envía el mensaje a través del canal de datos WebRTC."""
        if not self._conn_established.wait(timeout=15.0):
            raise ConnectionError("No se pudo establecer la conexión WebRTC P2P (timeout).")
            
        payload_str = json.dumps({
            "tipo": str(msg.tipo.value) if hasattr(msg.tipo, "value") else str(msg.tipo),
            "payload": msg.payload
        })
        
        asyncio.run_coroutine_threadsafe(self._send_on_channel(payload_str), self.loop)

    async def _send_on_channel(self, payload_str: str) -> None:
        if self.channel and self.channel.readyState == "open":
            self.channel.send(payload_str)

    def recibir(self) -> Mensaje:
        """Retorna el siguiente mensaje de la cola (bloqueante)."""
        try:
            tipo_str, payload = self._queue.get(timeout=60.0)
            return Mensaje(MsgType(tipo_str), payload)
        except queue.Empty:
            raise TimeoutError("Tiempo de espera agotado esperando acción del rival.")

    def cerrar(self) -> None:
        """Detiene el peer connection, cierra el canal y finaliza el loop."""
        asyncio.run_coroutine_threadsafe(self._close_webrtc(), self.loop)
        time.sleep(0.5)
        self.loop.call_soon_threadsafe(self.loop.stop)

    async def _close_webrtc(self) -> None:
        if self.channel:
            try:
                self.channel.close()
            except Exception:
                pass
        if self.pc:
            try:
                await self.pc.close()
            except Exception:
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
        """Inicia el servidor WebRTC local, recibe el HELLO y ejecuta el combate."""
        try:
            ip_local = socket.gethostbyname(socket.gethostname())
            self._log(f"[HOST] Servidor WebRTC iniciado en {ip_local}:{self.port} — esperando challenger...")
        except Exception:
            self._log(f"[HOST] Servidor WebRTC iniciado en puerto {self.port} — esperando challenger...")

        self._conn = ConexionP2P(puerto_local=self.port, mode="host")
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
