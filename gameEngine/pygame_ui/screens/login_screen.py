"""
pygame_ui/screens/login_screen.py
Pantalla de bienvenida, login y registro.
"""
from __future__ import annotations
import math
import pygame
from pygame_ui.screen_manager import Screen
from pygame_ui.widgets import Button, TextField, Toast, draw_rounded_rect, draw_glowing_rect
from pygame_ui.constants import *
 
 
class LoginScreen(Screen):
    """
    Pantalla de inicio con dos pestañas: LOGIN y REGISTRO.
    Llama a local_db y sync_client para autenticar.
    """
 
    def __init__(self, manager, local_db, sync_client, on_success):
        super().__init__(manager)
        self.local_db    = local_db
        self.sync_client = sync_client
        self.on_success  = on_success   # callback(usuario, tapo)
 
        self._tab    = "login"          # "login" | "register" | "forgot" | "code"
        self._time   = 0.0
        self._toast: Toast | None = None
        self._session_id:   str = ""    # 2FA: ID de sesión del challenge
        self._correo_hint:  str = ""    # 2FA: correo parcialmente oculto
        self._login_user:   str = ""    # guardado para el mensaje de bienvenida
        self._login_pass:   str = ""    # guardado para crear usuario local
 
        self._build_widgets()
 
    # ---------------------------------------------------------------- #
    #  Construcción de widgets
    # ---------------------------------------------------------------- #
 
    def _build_widgets(self):
        cx = SCREEN_W // 2
        panel_x = cx - 180
        panel_w = 360
 
        # ── Login ────────────────────────────────────────────────────
        self.tf_user  = TextField(panel_x, 280, panel_w, 44, placeholder="Usuario")
        self.tf_pass  = TextField(panel_x, 340, panel_w, 44, placeholder="Contraseña", password=True)
 
        self.btn_login = Button(
            panel_x, 410, panel_w, BTN_H,
            text="Iniciar sesión",
            callback=self._do_login,
            accent_color=C_ACCENT,
        )
 
        # ── Registro ─────────────────────────────────────────────────
        self.tf_reg_user   = TextField(panel_x, 250, panel_w, 40, placeholder="Nombre de usuario")
        self.tf_reg_email  = TextField(panel_x, 298, panel_w, 40, placeholder="Correo electrónico")
        self.tf_reg_pass   = TextField(panel_x, 346, panel_w, 40, placeholder="Contraseña", password=True)
        self.tf_reg_tapo   = TextField(panel_x, 394, panel_w, 40, placeholder="Nombre de tu Tapo")
 
        self._tipos = ["Fuego", "Agua", "Planta", "Luz", "Oscuridad", "Normal"]
        self._tipo_sel = "Normal"
        self._tipo_btns = []
        tipo_w = panel_w // len(self._tipos) - 4
        for i, t in enumerate(self._tipos):
            x = panel_x + i * (tipo_w + 4)
            self._tipo_btns.append(
                Button(x, 456, tipo_w, 30, text=t[:3],
                       callback=lambda tt=t: setattr(self, "_tipo_sel", tt),
                       accent_color=TYPE_COLORS.get(t, C_ACCENT))
            )
 
        self.btn_register = Button(
            panel_x, 494, panel_w, BTN_H,
            text="Crear cuenta",
            callback=self._do_register,
            accent_color=C_ACCENT,
        )
 
        # ── Pestañas ─────────────────────────────────────────────────
        self.tab_login_btn = Button(cx - 120, 210, 110, 36, text="Login",
                                    callback=lambda: self._switch_tab("login"))
        self.tab_reg_btn   = Button(cx + 10,  210, 110, 36, text="Registro",
                                    callback=lambda: self._switch_tab("register"))
 
        # ── ¿Olvidaste tu contraseña? ────────────────────────────────
        self.tf_forgot_email = TextField(panel_x, 305, panel_w, 44, placeholder="Tu correo electrónico")
        self.btn_forgot_send = Button(
            panel_x, 367, panel_w, BTN_H,
            text="Enviar enlace de recuperación",
            callback=self._do_forgot_password,
            accent_color=(90, 60, 200),
        )
        self.btn_back_to_login = Button(
            panel_x, 367 + BTN_H + 10, panel_w, 34,
            text="← Volver al login",
            callback=lambda: self._switch_tab("login"),
        )

        # ── 2FA: Entrada de código ─────────────────────────────────
        self.tf_2fa_code = TextField(panel_x, 315, panel_w, 52,
                                     placeholder="Código de 6 dígitos")
        self.btn_2fa_verify = Button(
            panel_x, 385, panel_w, BTN_H,
            text="✅  Verificar código",
            callback=self._do_verify_2fa,
            accent_color=(50, 180, 100),
        )
        self.btn_2fa_back = Button(
            panel_x, 385 + BTN_H + 10, panel_w, 34,
            text="← Volver al login",
            callback=lambda: self._switch_tab("login"),
        )

    # ---------------------------------------------------------------- #
    #  Lógica de autenticación (conecta al backend real)
    # ---------------------------------------------------------------- #
 
    def _do_forgot_password(self):
        correo = self.tf_forgot_email.text.strip()
        if not correo:
            self._show_toast("Ingresa tu correo electrónico", ok=False)
            return
        try:
            self._show_toast("Enviando enlace de recuperación...", ok=True)
            ok = self.sync_client.forgot_password(correo)
            if ok:
                self._show_toast("Si el correo está registrado, recibirás un enlace en breve ✉️", ok=True)
                self.tf_forgot_email.text = ""
            else:
                self._show_toast("Error de conexión con el servidor", ok=False)
        except Exception as e:
            self._show_toast(f"Error: {e}", ok=False)
 
    def _do_login(self):
        username = self.tf_user.text.strip()
        password = self.tf_pass.text.strip()
        if not username or not password:
            self._show_toast("Completa todos los campos", ok=False)
            return
        try:
            self._show_toast("Verificando credenciales...", ok=True)
            challenge = self.sync_client.login(username, password)
            if not challenge:
                self._show_toast("Credenciales incorrectas o servidor no disponible", ok=False)
                return

            # Guardar datos para usarlos en el paso 2
            self._session_id  = challenge["session_id"]
            self._correo_hint = challenge["correo_hint"]
            self._login_user  = username
            self._login_pass  = password

            self.tf_2fa_code.text = ""
            self._switch_tab("code")
            self._show_toast(f"Código enviado a {self._correo_hint} ✉️", ok=True)
        except Exception as e:
            self._show_toast(f"Error: {e}", ok=False)

    def _do_verify_2fa(self):
        codigo = self.tf_2fa_code.text.strip()
        if len(codigo) != 6 or not codigo.isdigit():
            self._show_toast("Ingresa el código de 6 dígitos numéricos", ok=False)
            return
        try:
            self._show_toast("Verificando código...", ok=True)
            auth_data = self.sync_client.verify_2fa(self._session_id, codigo)
            if not auth_data:
                self._show_toast("Código incorrecto o expirado. Inténtalo de nuevo.", ok=False)
                return

            usuario_id = auth_data["usuario_id"]
            correo     = auth_data["correo"]
            tapo_id    = auth_data["tapo_id"]
            username   = self._login_user
            password   = self._login_pass

            server_state = self.sync_client.resume(usuario_id)
            if not server_state or not server_state.get("tapo"):
                self._show_toast("No se pudo obtener el estado desde el servidor", ok=False)
                return

            from models.usuario import Usuario
            from models.tapo import Tapo
            usuario = Usuario(id=usuario_id, username=username, correo=correo, tapo_id=tapo_id)
            usuario.set_password(password)

            tapo = Tapo.from_dict(server_state["tapo"])

            self.local_db.guardar_usuario(usuario)
            self.local_db.guardar_tapo(tapo)
            self.local_db._crear_indices()

            self._show_toast(f"¡Bienvenido, {username}!", ok=True)
            pygame.time.delay(800)
            self.on_success(usuario, tapo)
        except Exception as e:
            self._show_toast(f"Error: {e}", ok=False)

    def _do_register(self):
        username = self.tf_reg_user.text.strip()
        correo   = self.tf_reg_email.text.strip()
        password = self.tf_reg_pass.text.strip()
        nombre   = self.tf_reg_tapo.text.strip()
        if not all([username, correo, password, nombre]):
            self._show_toast("Completa todos los campos", ok=False)
            return
        try:
            import uuid
            from models.tapo import TipoTapo, Vitales, Estadistica, Tapo        
            from models.usuario import Usuario

            usuario_id = str(uuid.uuid4())
            tapo_id = str(uuid.uuid4())

            self._show_toast("Registrando en servidor central...", ok=True)
            auth_data = self.sync_client.register(
                username=username,
                correo=correo,
                password=password,
                usuario_id=usuario_id,
                tapo_id=tapo_id,
            )

            if not auth_data:
                self._show_toast("Error al registrar o el servidor no está disponible", ok=False)
                return

            usuario = Usuario(id=usuario_id, username=username, correo=correo, tapo_id=tapo_id)
            usuario.set_password(password)

            try:
                tipo_enum = TipoTapo(self._tipo_sel)
            except ValueError:
                tipo_enum = TipoTapo.NORMAL
            tapo = Tapo(
                id_mascota=tapo_id,
                nombre=nombre,
                vitales=Vitales(),
                estadistica=Estadistica(tipo=tipo_enum),
            )

            self.local_db.guardar_usuario(usuario)
            self.local_db.guardar_tapo(tapo)
            self.local_db._crear_indices()

            self.sync_client.upload_state(tapo)

            self._show_toast(f"¡Cuenta creada! Bienvenido, {username}!", ok=True)
            pygame.time.delay(900)
            self.on_success(usuario, tapo)
        except Exception as e:
            self._show_toast(f"Error: {e}", ok=False)
 
    def _switch_tab(self, tab: str):
        self._tab = tab
        # Limpiar campo de forgot al entrar
        if tab == "forgot":
            self.tf_forgot_email.text = ""
 
    def _show_toast(self, msg: str, ok: bool = True):
        self._toast = Toast(msg, ok=ok)
 
    # ---------------------------------------------------------------- #
    #  Eventos
    # ---------------------------------------------------------------- #
 
    def handle_event(self, event: pygame.event.Event):
        if self._tab == "login":
            for w in [self.tf_user, self.tf_pass,
                    self.btn_login, self.tab_login_btn, self.tab_reg_btn]:
                w.handle_event(event)
        elif self._tab == "forgot":
            for w in [self.tf_forgot_email, self.btn_forgot_send,
                      self.btn_back_to_login]:
                w.handle_event(event)
        elif self._tab == "code":
            for w in [self.tf_2fa_code, self.btn_2fa_verify, self.btn_2fa_back]:
                w.handle_event(event)
        else:
            for w in [self.tf_reg_user, self.tf_reg_email, self.tf_reg_pass,
                    self.tf_reg_tapo, self.btn_register,
                    self.tab_login_btn, self.tab_reg_btn]:
                w.handle_event(event)
            for b in self._tipo_btns:
                b.handle_event(event)
 
    # ---------------------------------------------------------------- #
    #  Update
    # ---------------------------------------------------------------- #
 
    def update(self, dt: float):
        self._time += dt
        if self._toast:
            self._toast.update(dt)
            if not self._toast.alive:
                self._toast = None
 
        if self._tab == "login":
            for w in [self.tf_user, self.tf_pass, self.btn_login,
                    self.tab_login_btn, self.tab_reg_btn]:
                w.update(dt)
        elif self._tab == "forgot":
            for w in [self.tf_forgot_email, self.btn_forgot_send,
                      self.btn_back_to_login]:
                w.update(dt)
        elif self._tab == "code":
            for w in [self.tf_2fa_code, self.btn_2fa_verify, self.btn_2fa_back]:
                w.update(dt)
        else:
            for w in [self.tf_reg_user, self.tf_reg_email, self.tf_reg_pass,
                    self.tf_reg_tapo, self.btn_register,
                    self.tab_login_btn, self.tab_reg_btn]:
                w.update(dt)
            for b in self._tipo_btns:
                b.update(dt)
 
    # ---------------------------------------------------------------- #
    #  Draw
    # ---------------------------------------------------------------- #
 
    def draw(self, surf: pygame.Surface):
        fonts = self.manager.fonts
        cx    = SCREEN_W // 2
 
        # Fondo con grid puntilleado
        _draw_grid(surf, self._time)
 
        # Logo
        title = fonts["title"].render("TapoMon", True, C_ACCENT)
        sub   = fonts["label"].render("Tu mascota virtual distribuida", True, C_GRAY)
        surf.blit(title, (cx - title.get_width() // 2, 80))
        surf.blit(sub,   (cx - sub.get_width()   // 2, 130))
 
        # Línea decorativa bajo el logo
        pygame.draw.line(surf, C_ACCENT_DIM, (cx - 100, 165), (cx + 100, 165), 1)
 
        # Panel con fondo
        panel_x, panel_w = cx - 200, 400
        if self._tab == "forgot":
            panel_h = 270
        elif self._tab == "code":
            panel_h = 310
        elif self._tab == "login":
            panel_h = 340
        else:
            panel_h = 400
        draw_rounded_rect(surf, pygame.Rect(panel_x, 195, panel_w, panel_h), C_BG2, radius=14,
                          border=1, border_color=C_BORDER)
 
        # Tabs (solo en login / registro)
        if self._tab not in ("forgot", "code"):
            self.tab_login_btn.draw(surf, fonts["small"])
            self.tab_reg_btn.draw(surf, fonts["small"])
 
        if self._tab == "login":
            self._draw_login(surf, fonts)
        elif self._tab == "forgot":
            self._draw_forgot(surf, fonts)
        elif self._tab == "code":
            self._draw_code(surf, fonts)
        else:
            self._draw_register(surf, fonts)
 
        # Toast
        if self._toast:
            self._toast.draw(surf, fonts["label"])
 
    def _draw_login(self, surf, fonts):
        cx = SCREEN_W // 2
        self.tf_user.draw(surf, fonts["label"])
        self.tf_pass.draw(surf, fonts["label"])
        self.btn_login.draw(surf, fonts["label"])
 
        # Link "¿Olvidaste tu contraseña?"
        lbl = fonts["small"].render("¿Olvidaste tu contraseña?", True, (100, 100, 200))
        lbl_rect = lbl.get_rect(center=(cx, 462))
        surf.blit(lbl, lbl_rect)
        # Detectar hover manualmente para efecto visual (no es un Button)
        mx, my = pygame.mouse.get_pos()
        if lbl_rect.collidepoint(mx, my):
            pygame.draw.line(surf, (130, 130, 220),
                             (lbl_rect.left, lbl_rect.bottom + 1),
                             (lbl_rect.right, lbl_rect.bottom + 1), 1)
            if pygame.mouse.get_pressed()[0]:
                self._switch_tab("forgot")
 
    def _draw_forgot(self, surf, fonts):
        cx = SCREEN_W // 2
        # Título
        title = fonts["label"].render("🔑  Recuperar contraseña", True, (200, 190, 255))
        surf.blit(title, (cx - title.get_width() // 2, 220))
 
        hint = fonts["small"].render("Escribe tu correo y te enviaremos un enlace.", True, (100, 100, 130))
        surf.blit(hint, (cx - hint.get_width() // 2, 248))
 
        self.tf_forgot_email.draw(surf, fonts["label"])
        self.btn_forgot_send.draw(surf, fonts["small"])
        self.btn_back_to_login.draw(surf, fonts["small"])
 
    def _draw_register(self, surf, fonts):
        self.tf_reg_user.draw(surf, fonts["small"])
        self.tf_reg_email.draw(surf, fonts["small"])
        self.tf_reg_pass.draw(surf, fonts["small"])
        self.tf_reg_tapo.draw(surf, fonts["small"])
 
        # Selector de tipo
        cx = SCREEN_W // 2
        lbl = fonts["small"].render("Tipo de Tapo:", True, C_GRAY_LIGHT)
        surf.blit(lbl, (cx - 180, 438))
        for i, (btn, t) in enumerate(zip(self._tipo_btns, self._tipos)):
            is_sel = t == self._tipo_sel
            if is_sel:
                col = TYPE_COLORS.get(t, C_ACCENT)
                draw_glowing_rect(surf, btn.rect, C_BG3, col, glow_width=2)
            btn.draw(surf, fonts["small"])
 
        self.btn_register.draw(surf, fonts["label"])

    def _draw_code(self, surf, fonts):
        """Pantalla de verificación 2FA."""
        cx = SCREEN_W // 2

        # Título
        title = fonts["label"].render("🛡️  Verificación en dos pasos", True, (130, 200, 255))
        surf.blit(title, (cx - title.get_width() // 2, 215))

        # Correo hint
        hint1 = fonts["small"].render("Código enviado a:", True, (100, 110, 140))
        surf.blit(hint1, (cx - hint1.get_width() // 2, 248))
        hint2 = fonts["small"].render(self._correo_hint or "tu correo", True, (160, 170, 220))
        surf.blit(hint2, (cx - hint2.get_width() // 2, 265))

        self.tf_2fa_code.draw(surf, fonts["label"])
        self.btn_2fa_verify.draw(surf, fonts["small"])
        self.btn_2fa_back.draw(surf, fonts["small"])
 
 
# ──────────────────────────────────────────────────────────────────── #
#  Fondo decorativo
# ──────────────────────────────────────────────────────────────────── #
 
def _draw_grid(surf: pygame.Surface, t: float):
    """Grid puntilleado animado como fondo."""
    spacing = 40
    offset  = int(t * 20) % spacing
    for x in range(-spacing + offset, SCREEN_W + spacing, spacing):
        for y in range(-spacing + offset, SCREEN_H + spacing, spacing):
            pygame.draw.circle(surf, C_BORDER, (x, y), 1)