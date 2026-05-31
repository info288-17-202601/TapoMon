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
 
        self._tab    = "login"          # "login" | "register"
        self._time   = 0.0
        self._toast: Toast | None = None
 
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
 
    # ---------------------------------------------------------------- #
    #  Lógica de autenticación (conecta al backend real)
    # ---------------------------------------------------------------- #
 
    def _do_login(self):
        username = self.tf_user.text.strip()
        password = self.tf_pass.text.strip()
        if not username or not password:
            self._show_toast("Completa todos los campos", ok=False)
            return
        try:
            self._show_toast("Autenticando con servidor central...", ok=True)
            auth_data = self.sync_client.login(username, password)
            if not auth_data:
                self._show_toast("Credenciales incorrectas o el servidor no está disponible", ok=False)
                return

            usuario_id = auth_data["usuario_id"]
            correo = auth_data["correo"]
            tapo_id = auth_data["tapo_id"]

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
            from models.tapo import TipoTapo, Vitales, Estadistica
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

            tipo_enum = TipoTapo(self._tipo_sel) if hasattr(TipoTapo, self._tipo_sel) else TipoTapo.NORMAL
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
        panel_h = 340 if self._tab == "login" else 400
        draw_rounded_rect(surf, pygame.Rect(panel_x, 195, panel_w, panel_h), C_BG2, radius=14,
                          border=1, border_color=C_BORDER)
 
        # Tabs
        self.tab_login_btn.draw(surf, fonts["small"])
        self.tab_reg_btn.draw(surf, fonts["small"])
 
        if self._tab == "login":
            self._draw_login(surf, fonts)
        else:
            self._draw_register(surf, fonts)
 
        # Toast
        if self._toast:
            self._toast.draw(surf, fonts["label"])
 
    def _draw_login(self, surf, fonts):
        self.tf_user.draw(surf, fonts["label"])
        self.tf_pass.draw(surf, fonts["label"])
        self.btn_login.draw(surf, fonts["label"])
 
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