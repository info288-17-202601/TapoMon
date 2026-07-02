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
from network import session_manager


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

    def login(self, username: str, password: str) -> dict | None:
        """
        Paso 1 del login con 2FA: valida credenciales.

        Con 2FA activo el servidor NO retorna el JWT directamente.
        Retorna un challenge: {requires_2fa, session_id, correo_hint}
        que el cliente debe usar para solicitar el código al usuario
        y luego llamar a verify_2fa().

        Returns:
            Dict {requires_2fa, session_id, correo_hint} si las credenciales
            son válidas, None si fallaron o el servidor no está disponible.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("requires_2fa"):
                    return data   # {requires_2fa, session_id, correo_hint}
                print("  ⚠️  Respuesta inesperada del servidor al hacer login.")
                return None
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Verifique su conexión.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error de conexión: {e}")
            return None

    def verify_2fa(self, session_id: str, codigo: str) -> dict | None:
        """
        Paso 2 del login con 2FA: verifica el código de 6 dígitos.

        Si el código es correcto, el servidor retorna el JWT y los datos
        del usuario. Guarda el token internamente para llamadas futuras.

        Args:
            session_id: ID de sesión retornado por login().
            codigo:     Código de 6 dígitos que el usuario ingresó.

        Returns:
            Dict completo del usuario (access_token, usuario_id, etc.) o None.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/auth/verify-2fa",
                json={"session_id": session_id, "codigo": codigo},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                token      = data.get("access_token")
                usuario_id = data.get("usuario_id")
                if not token or not usuario_id:
                    print("  ⚠️  Respuesta inesperada al verificar 2FA.")
                    return None
                self._token      = token
                self._usuario_id = usuario_id
                # Guardar sesión para persistencia entre reinicios
                session_manager.save_session(data)
                return data
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al verificar 2FA: {e}")
            return None

    def restore_session(self) -> dict | None:
        """
        Intenta restaurar una sesión guardada desde disco.

        Si existe una sesión válida (JWT no expirado), carga el token
        en memoria y retorna los datos del usuario para que el juego
        pueda arrancar sin pasar por el login.

        Returns:
            Dict con {usuario_id, username, correo, tapo_id, access_token}
            o None si no hay sesión válida.
        """
        data = session_manager.load_session()
        if data:
            self._token      = data.get("access_token")
            self._usuario_id = data.get("usuario_id")
        return data

    def logout_session(self) -> None:
        """
        Cierra la sesión y borra el archivo local.
        Solo llamar cuando el usuario elige salir explícitamente.
        """
        session_manager.clear_session()
        self._token      = None
        self._usuario_id = None

    # ------------------------------------------------------------------ #
    #  SyncService
    # ------------------------------------------------------------------ #

    def register(
        self,
        username: str,
        correo: str,
        password: str,
        usuario_id: str,
        tapo_id: str,
    ) -> dict | None:
        """
        Registra una cuenta nueva en el servidor.
        
        Returns:
            Dict con los datos del usuario si el registro fue exitoso,
            None si falló o el servidor no está disponible.
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
                return data
            if resp.status_code == 409:
                # El usuario ya existe en el servidor — le decimos al cliente
                # que haga login manual (no podemos hacer login automático
                # porque ahora requiere 2FA y un correo real).
                print("  ⚠️  Usuario ya existe en el servidor. Inicia sesión manualmente.")
                return None
            print(f"  ⚠️  Error al registrar en el servidor: {resp.status_code}")
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. Cuenta creada solo localmente.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al registrar en el servidor: {e}")
            return None

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

    def get_social_state(self) -> dict | None:
        """Obtiene la vista social del Tapo autenticado."""
        if not self._token:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/social/friends",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. No se pudo cargar el estado social.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al cargar estado social: {e}")
            return None

    def add_friend(self, friend_id: str) -> dict | None:
        """Agrega un amigo al Tapo autenticado."""
        if not self._token:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/social/friends",
                json={"friend_id": friend_id},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. No se pudo agregar el amigo.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al agregar amigo: {e}")
            return None

    def remove_friend(self, friend_id: str) -> dict | None:
        """Quita un amigo del Tapo autenticado."""
        if not self._token:
            return None
        try:
            resp = requests.delete(
                f"{self.base_url}/social/friends/{friend_id}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. No se pudo quitar el amigo.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al quitar amigo: {e}")
            return None

    def send_gift(self, friend_id: str, gift_type: str = "comida") -> dict | None:
        """Envía un regalo a un amigo del Tapo autenticado."""
        if not self._token:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/social/gift",
                json={"friend_id": friend_id, "gift_type": gift_type},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. No se pudo enviar el regalo.")
            return None
        except Exception as e:
            print(f"  ⚠️  Error al enviar regalo: {e}")
            return None

    def is_connected(self) -> bool:
        """Verifica si hay un token JWT activo."""
        return self._token is not None

    @property
    def usuario_id(self) -> str | None:
        return self._usuario_id

    def forgot_password(self, correo: str) -> bool:
        """
        Solicita el envío de un correo de recuperación de contraseña.

        Args:
            correo: Correo electrónico del usuario que olvidó su contraseña.

        Returns:
            True si la solicitud llegó al servidor (independiente de si el
            correo existe), False si hubo un error de conexión.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/auth/forgot-password",
                json={"correo": correo},
                timeout=REQUEST_TIMEOUT,
            )
            return resp.status_code == 200
        except requests.ConnectionError:
            print("  ⚠️  Servidor no disponible. No se pudo enviar el correo.")
            return False
        except Exception as e:
            print(f"  ⚠️  Error al solicitar reset: {e}")
            return False
