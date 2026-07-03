"""
pygame_ui/screens/social_screen.py
Pantalla social para gestionar amigos y regalos del Tapo.
"""
from __future__ import annotations

import pygame

from pygame_ui.constants import *
from pygame_ui.screen_manager import Screen
from pygame_ui.screens.social_logic import (
    apply_local_friend_change,
    copy_text_to_clipboard,
    get_friend_display_name,
    get_friend_recommendations,
    resolve_friend_target,
)
from pygame_ui.widgets import Button, TextField, Toast, draw_rounded_rect


class SocialScreen(Screen):
    """Pantalla visual para agregar, quitar y regalar a amigos."""

    def __init__(self, manager, usuario, tapo, sync_client, local_db):
        super().__init__(manager)

        self.usuario = usuario
        self.tapo = tapo
        self.sync_client = sync_client
        self.local_db = local_db

        self._toast: Toast | None = None

        self.friends: list[dict] = []
        self.recommendations: list[dict] = []
        self.selected_friend_id: str | None = None

        self._build_widgets()
        self._refresh_social_state()

    def _build_widgets(self) -> None:

        self.btn_back = Button(
            24,
            SCREEN_H - 48,
            100,
            34,
            text="Volver",
            callback=self._go_back,
            color=C_BG3,
            hover_color=C_BG2,
            text_color=C_GRAY,
            accent_color=C_BORDER,
        )

        self.btn_refresh = Button(
            140,
            SCREEN_H - 48,
            110,
            34,
            text="Actualizar",
            callback=lambda: self._refresh_social_state(show_error=False),
            color=C_BG3,
            hover_color=C_BG2,
            text_color=C_WHITE,
            accent_color=C_ACCENT,
        )

        # -------- Columna derecha --------

        self.tf_friend = TextField(
            430,
            165,
            190,
            38,
            placeholder="Nombre o ID",
        )

        self.tf_gift = TextField(
            430,
            265,
            190,
            38,
            placeholder="Tipo de regalo",
        )

        self.btn_add = Button(
            635,
            165,
            95,
            38,
            text="Agregar",
            callback=self._add_friend,
        )

        self.btn_remove = Button(
            635,
            215,
            95,
            38,
            text="Quitar",
            callback=self._remove_friend,
        )

        self.btn_gift = Button(
            635,
            265,
            95,
            38,
            text="Regalar",
            callback=self._send_gift,
        )

        self.btn_copy_id = Button(
            635,
            100,
            95,
            38,
            text="Copiar ID",
            callback=self._copy_own_id,
        )

        self.friend_buttons: list[Button] = []

    def _show_toast(self, msg: str, ok: bool = True) -> None:
        self._toast = Toast(msg, ok=ok)

    def _get_local_friends(self) -> list[dict]:
        friend_ids = getattr(self.tapo, "friend_list", None) or []
        if not isinstance(friend_ids, list):
            friend_ids = [friend_ids]

        normalized: list[dict] = []
        for friend_id in friend_ids:
            friend_id = str(friend_id or "").strip()
            if friend_id:
                normalized.append({"friend_id": friend_id})

        return normalized

    def _persist_local_friend_state(self, friend_ids: list[str]) -> None:
        self.tapo.friend_list = friend_ids
        self.local_db.guardar_tapo(self.tapo)
        self._apply_friend_state(
            [{"friend_id": friend_id} for friend_id in friend_ids],
            source="local",
        )

    def _apply_friend_state(self, friends: list[dict], source: str) -> None:
        self.friends = []
        seen_ids: set[str] = set()

        for friend in friends:
            if isinstance(friend, dict):
                friend_id = str(friend.get("friend_id") or "").strip()
            else:
                friend_id = str(friend or "").strip()

            if not friend_id or friend_id in seen_ids:
                continue

            seen_ids.add(friend_id)
            if isinstance(friend, dict):
                row = dict(friend)
                row.setdefault("friend_id", friend_id)
            else:
                row = {"friend_id": friend_id}
            row["display_name"] = get_friend_display_name(row, self.local_db)
            self.friends.append(row)

        self.tapo.friend_list = [f["friend_id"] for f in self.friends]
        self.local_db.guardar_tapo(self.tapo)

        if self.selected_friend_id not in {f["friend_id"] for f in self.friends}:
            self.selected_friend_id = (
                self.friends[0]["friend_id"] if self.friends else None
            )

        if source == "server":
            self._show_toast("Estado social actualizado.")

    def _refresh_social_state(self, show_error: bool = False) -> None:

        if not self.sync_client.is_connected():
            local_friends = self._get_local_friends()
            if local_friends:
                self._apply_friend_state(local_friends, source="local")
                return

            if show_error:
                self._show_toast(
                    "No hay sesión activa con el servidor.",
                    ok=False,
                )
            return

        data = self.sync_client.get_social_state()

        if data and data.get("success"):
            self.recommendations = data.get("recommendations", [])
            self._apply_friend_state(data.get("friends", []), source="server")
            return

        local_friends = self._get_local_friends()
        if local_friends:
            self._apply_friend_state(local_friends, source="local")
            return

        if show_error:
            self._show_toast(
                "No se pudo cargar el estado social.",
                ok=False,
            )

    def _copy_own_id(self) -> None:
        tapo_id = getattr(self.tapo, "id_mascota", "") or ""
        if not tapo_id:
            self._show_toast("No hay un ID de Tapo disponible.", ok=False)
            return

        if copy_text_to_clipboard(tapo_id):
            self._show_toast("ID del Tapo copiado.")
        else:
            self._show_toast("No se pudo copiar al portapapeles.", ok=False)

    def _add_friend(self) -> None:

        friend_id = self.tf_friend.text.strip()

        if not friend_id:
            self._show_toast(
                "Ingresa un nombre o ID de amigo.",
                ok=False,
            )
            return

        resolved_friend_id, lookup_state = resolve_friend_target(
            friend_id,
            self.local_db,
            getattr(self.tapo, "id_mascota", None),
        )

        if not resolved_friend_id:
            if lookup_state == "multiple":
                self._show_toast(
                    "Hay varias coincidencias. Usa un nombre más específico.",
                    ok=False,
                )
            else:
                self._show_toast(
                    "No se encontró un Tapo con ese nombre. Prueba con el ID o un nombre más exacto.",
                    ok=False,
                )
            return

        if self.sync_client.is_connected():
            result = self.sync_client.add_friend(resolved_friend_id)

            if result and result.get("success"):
                self.tf_friend.text = ""
                self.selected_friend_id = resolved_friend_id
                self._refresh_social_state()
                return
            
            # Si el servidor falló o no dio respuesta exitosa, mostramos la razón
            msg = result.get("message") if (result and isinstance(result, dict)) else "No se pudo agregar al amigo en el servidor."
            self._show_toast(msg, ok=False)
            return

        current_ids = [f["friend_id"] for f in self.friends] if self.friends else list(getattr(self.tapo, "friend_list", []) or [])
        updated_ids = apply_local_friend_change(current_ids, resolved_friend_id, action="add")
        self._persist_local_friend_state(updated_ids)

        self.tf_friend.text = ""
        self.selected_friend_id = resolved_friend_id
        self._show_toast("Amigo agregado localmente.")

    def _remove_friend(self) -> None:

        friend_id = (
            self.selected_friend_id
            or self.tf_friend.text.strip()
        )

        if not friend_id:

            self._show_toast(
                "Selecciona o ingresa un amigo para quitar.",
                ok=False,
            )
            return

        result = self.sync_client.remove_friend(friend_id)

        if result and result.get("success"):
            self.tf_friend.text = ""
            self.selected_friend_id = None
            self._refresh_social_state()
            return

        current_ids = [f["friend_id"] for f in self.friends] if self.friends else list(getattr(self.tapo, "friend_list", []) or [])
        updated_ids = apply_local_friend_change(current_ids, friend_id, action="remove")
        self._persist_local_friend_state(updated_ids)

        self.tf_friend.text = ""
        self.selected_friend_id = None
        self._show_toast("Amigo quitado.")

    def _send_gift(self) -> None:

        friend_id = (
            self.selected_friend_id
            or self.tf_friend.text.strip()
        )

        gift_type = self.tf_gift.text.strip() or "comida"

        if not friend_id:

            self._show_toast(
                "Selecciona o ingresa un amigo antes de regalar.",
                ok=False,
            )
            return

        result = self.sync_client.send_gift(
            friend_id,
            gift_type=gift_type,
        )

        if result and result.get("success"):
            self._show_toast("Regalo enviado.")
            return

        self.tapo.gift_cooldowns = list(getattr(self.tapo, "gift_cooldowns", []) or [])
        self.tapo.gift_cooldowns = [
            entry for entry in self.tapo.gift_cooldowns if entry.get("friend_id") != friend_id
        ]
        self.tapo.gift_cooldowns.append({
            "friend_id": friend_id,
            "last_gift_timestamp": pygame.time.get_ticks(),
        })
        self.local_db.guardar_tapo(self.tapo)
        self._show_toast("Regalo registrado.")

    def _go_back(self) -> None:
        self.manager.pop()

    def handle_event(self, event: pygame.event.Event) -> None:

        self.tf_friend.handle_event(event)
        self.tf_gift.handle_event(event)

        self.btn_back.handle_event(event)
        self.btn_refresh.handle_event(event)

        self.btn_add.handle_event(event)
        self.btn_remove.handle_event(event)
        self.btn_gift.handle_event(event)
        self.btn_copy_id.handle_event(event)

        for btn in self.friend_buttons:
            btn.handle_event(event)

    def update(self, dt: float) -> None:

        self.tf_friend.update(dt)
        self.tf_gift.update(dt)

        self.btn_back.update(dt)
        self.btn_refresh.update(dt)

        self.btn_add.update(dt)
        self.btn_remove.update(dt)
        self.btn_gift.update(dt)
        self.btn_copy_id.update(dt)

        for btn in self.friend_buttons:
            btn.update(dt)

        if self._toast:

            self._toast.update(dt)

            if not self._toast.alive:
                self._toast = None

    def draw(self, surf: pygame.Surface) -> None:

        fonts = self.manager.fonts
        surf.fill(C_BG)

        # --------------------------------------------------------
        # Título
        # --------------------------------------------------------

        title = fonts["title"].render(
            "Social",
            True,
            C_ACCENT,
        )
        surf.blit(title, (40, 24))

        subtitle = fonts["small"].render(
            "Gestiona tus amigos y envía regalos",
            True,
            C_GRAY_LIGHT,
        )
        surf.blit(subtitle, (40, 70))

        # --------------------------------------------------------
        # Panel principal
        # --------------------------------------------------------

        panel = pygame.Rect(30, 90, 720, 420)

        draw_rounded_rect(
            surf,
            panel,
            C_BG2,
            radius=14,
            border=1,
            border_color=C_BORDER,
        )

        # Línea divisoria
        pygame.draw.line(
            surf,
            C_BORDER,
            (390, 110),
            (390, 490),
            2,
        )

        # ========================================================
        # COLUMNA IZQUIERDA
        # ========================================================

        left_title = fonts["small"].render(
            "Amigos actuales",
            True,
            C_WHITE,
        )
        surf.blit(left_title, (50, 110))

        self.friend_buttons = []

        start_y = 145

        if self.friends:

            for idx, friend in enumerate(self.friends):

                friend_id = friend.get("friend_id", "")

                name = friend.get("display_name") or get_friend_display_name(friend, self.local_db)
                if not name:
                    name = friend_id

                # Restringir longitud del texto
                if len(name) > 20:
                    name = name[:17] + "..."

                text = f"{name}"

                btn = Button(
                    50,
                    start_y + idx * 36,
                    320,
                    30,
                    text=text,
                    callback=lambda fid=friend_id: self._select_friend(fid),
                    color=(
                        C_ACCENT
                        if friend_id == self.selected_friend_id
                        else C_BG3
                    ),
                    hover_color=C_BG2,
                    text_color=C_WHITE,
                    accent_color=C_ACCENT,
                )

                self.friend_buttons.append(btn)
                btn.draw(surf, fonts["small"])

        else:

            empty = fonts["small"].render(
                "Aún no tienes amigos agregados.",
                True,
                C_GRAY,
            )

            surf.blit(empty, (50, 160))

        hint = fonts["small"].render(
            "Selecciona un amigo para quitar o regalar.",
            True,
            C_GRAY_LIGHT,
        )

        surf.blit(hint, (50, 470))

        # ========================================================
        # COLUMNA DERECHA
        # ========================================================

        right_title = fonts["small"].render(
            "Gestionar amigos",
            True,
            C_WHITE,
        )

        surf.blit(right_title, (430, 110))

        label_id = fonts["small"].render(
            "ID del amigo",
            True,
            C_GRAY_LIGHT,
        )

        surf.blit(label_id, (430, 145))

        self.tf_friend.draw(
            surf,
            fonts["small"],
        )

        self.btn_add.draw(
            surf,
            fonts["small"],
        )

        self.btn_remove.draw(
            surf,
            fonts["small"],
        )

        label_gift = fonts["small"].render(
            "Tipo de regalo",
            True,
            C_GRAY_LIGHT,
        )

        surf.blit(label_gift, (430, 245))

        self.tf_gift.draw(
            surf,
            fonts["small"],
        )

        self.btn_gift.draw(
            surf,
            fonts["small"],
        )

        self.btn_copy_id.draw(
            surf,
            fonts["small"],
        )

        # --------------------------------------------------------
        # Información del amigo seleccionado
        # --------------------------------------------------------

        if self.selected_friend_id:

            info = fonts["small"].render(
                "Seleccionado:",
                True,
                C_ACCENT,
            )

            surf.blit(info, (430, 330))

            info2 = fonts["small"].render(
                self.selected_friend_id,
                True,
                C_WHITE,
            )

            surf.blit(info2, (430, 355))

        recommendations = get_friend_recommendations(self)
        rec_title = fonts["small"].render(
            "Recomendaciones:",
            True,
            C_ACCENT,
        )
        surf.blit(rec_title, (430, 390))

        if recommendations:
            for idx, rec in enumerate(recommendations):
                label = fonts["small"].render(
                    f"• {rec['name']}",
                    True,
                    C_GRAY_LIGHT,
                )
                surf.blit(label, (430, 410 + idx * 18))
        else:
            empty = fonts["small"].render(
                "Sin recomendaciones aún",
                True,
                C_GRAY,
            )
            surf.blit(empty, (430, 410))

        # --------------------------------------------------------
        # Botones inferiores
        # --------------------------------------------------------

        self.btn_back.draw(
            surf,
            fonts["small"],
        )

        self.btn_refresh.draw(
            surf,
            fonts["small"],
        )

        # --------------------------------------------------------
        # Toast
        # --------------------------------------------------------

        if self._toast:
            self._toast.draw(
                surf,
                fonts["label"],
            )

    def _select_friend(self, friend_id: str) -> None:

        self.selected_friend_id = friend_id
        display_name = get_friend_display_name({"friend_id": friend_id}, self.local_db)
        self.tf_friend.text = display_name

        self._show_toast(
            f"Amigo seleccionado: {display_name}"
        )