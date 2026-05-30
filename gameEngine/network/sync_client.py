"""
network/sync_client.py
Cliente HTTP que se comunica con el SyncService del servidor central.

Justificación:
    Este módulo encapsula toda la comunicación HTTP con el servidor.
    El game engine y main.py solo llaman a métodos simples
    (login, upload_state, resume) sin preocuparse por HTTP, headers,
    tokens JWT, o manejo de errores de red.

    Usa 'requests' (síncrono) porque el cliente de consola no es async.
    Si se migra a un cliente async (GUI), se cambiaría a httpx.

    Maneja gracefully los errores de conexión: si el servidor no está
    disponible, el juego sigue funcionando solo con la DB local.
"""
from __future__ import annotations

import requests

from network.config import SERVER_URL, REQUEST_TIMEOUT


class SyncClient:
    """
    Cliente para comunicarse con el SyncService del servidor central.
    
    Flujo típico:
        1. client.login(username, password)  → obtiene JWT
        2. client.upload_state(tapo)         → sube snapshot al desconectarse
        3. client.resume(usuario_id)         → descarga estado al reconectarse
    """

    def __init__(self, server_url: str | None = None):
        self.base_url = server_url or SERVER_URL
        self._token: str | None = None
        self._usuario_id: str | None = None

    @property
    def _headers(self) -> dict:
        """Headers con JWT para requests autenticados."""
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    # ------------------------------------------------------------------ #
    #  Autenticación
    # ------------------------------------------------------------------ #

    def login(self, username: str, password: str) -> bool:
        """
        Autentica con el servidor y guarda el JWT.
        
        Returns:
            True si el login fue exitoso, False si falló
            (credenciales inválidas o servidor no disponible).
        """
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                usuario_id = data.get("usuario_id")
                if not token or not usuario_id:
                    print("  ⚠️  Respuesta inesperada del servidor al hacer login.")
                    return False
                self._token = token
                self._usuario_id = usuario_id
                return True
            return False
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Continuando en modo offline.")
            return False
        except Exception as e:
            print(f"  ⚠️  Error de conexión: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  SyncService
    # ------------------------------------------------------------------ #

    def register(self, username: str, correo: str, password: str,
                 usuario_id: str, tapo_id: str) -> bool:
        """
        Registra una cuenta nueva en el servidor.

        Debe llamarse justo después de crear el usuario en la DB local,
        pasando los mismos UUIDs para que ambas bases de datos sean
        consistentes desde el primer momento.

        Args:
            username:   Nombre de usuario.
            correo:     Correo electrónico.
            password:   Contraseña en texto plano.
            usuario_id: UUID del usuario generado localmente.
            tapo_id:    UUID de la mascota generado localmente.

        Returns:
            True si el registro fue exitoso (o ya existía),
            False si el servidor no está disponible.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/auth/register",
                json={
                    "username":   username,
                    "correo":     correo,
                    "password":   password,
                    "usuario_id": usuario_id,
                    "tapo_id":    tapo_id,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 201:
                data = resp.json()
                token = data.get("access_token")
                uid   = data.get("usuario_id")
                if token and uid:
                    self._token = token
                    self._usuario_id = uid
                return True
            if resp.status_code == 409:
                # El usuario ya existe en el servidor. Esto ocurre normalmente
                # cuando el cliente y el servidor comparten la misma instancia
                # de MongoDB: local_db ya escribió el usuario antes de que
                # llegáramos aquí. Hacemos login para obtener el JWT.
                return self.login(username, password)
            print(f"  ⚠️  Error al registrar en el servidor: {resp.status_code}")
            return False
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Cuenta creada solo localmente.")
            return False
        except Exception as e:
            print(f"  ⚠️  Error al registrar en el servidor: {e}")
            return False

    def upload_state(self, tapo) -> bool:
        """
        sync_upload: Envía el snapshot del Tapo al servidor.
        
        Se llama cuando el usuario cierra sesión. El Tapo queda
        registrado como IDLE en el servidor y la simulación IDLE
        empezará a degradar su estado.
        
        Args:
            tapo: Instancia de Tapo (usa tapo.to_dict() para serializar).
        
        Returns:
            True si se subió correctamente, False si falló.
        """
        if not self._token:
            return False

        try:
            tapo_dict = tapo.to_dict()
            resp = requests.post(
                f"{self.base_url}/sync/upload",
                json=tapo_dict,
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ☁️  {data.get('message', 'Sincronizado.')}")
                return True
            else:
                print(f"  ⚠️  Error al sincronizar: {resp.status_code}")
                return False
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Estado guardado solo localmente.")
            return False
        except Exception as e:
            print(f"  ⚠️  Error de sincronización: {e}")
            return False

    def resume(self, usuario_id: str) -> dict | None:
        """
        resume_state: Descarga el estado actualizado del Tapo + inbox.
        
        Se llama cuando el usuario inicia sesión. El servidor devuelve
        el estado post-simulación IDLE y los mensajes pendientes.
        
        Args:
            usuario_id: ID del usuario autenticado.
        
        Returns:
            dict con {tapo: {...}, inbox: [...]} o None si falló.
        """
        if not self._token:
            return None

        try:
            resp = requests.get(
                f"{self.base_url}/sync/resume/{usuario_id}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Usando estado local.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al recuperar estado: {e}")
            return None

    def is_connected(self) -> bool:
        """Verifica si hay un token JWT activo."""
        return self._token is not None

    @property
    def usuario_id(self) -> str | None:
        return self._usuario_id
