from __future__ import annotations

import ctypes
import os
import subprocess

#funciones auxiliares para el módulo social

def copy_text_to_clipboard(text: str) -> bool:
    """Copia texto al portapapeles de forma fiable en Windows y con fallback a Tk."""
    text = str(text or "").strip()
    if not text:
        return False

    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    buffer = ctypes.create_unicode_buffer(text)
                    size = (len(buffer.value) + 1) * ctypes.sizeof(ctypes.c_wchar)
                    handle = kernel32.GlobalAlloc(0x0042, size)
                    if handle:
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            ctypes.cdll.msvcrt.memcpy(ptr, ctypes.cast(buffer, ctypes.c_void_p), size)
                            kernel32.GlobalUnlock(handle)
                            user32.SetClipboardData(13, handle)
                            return True
                        kernel32.GlobalFree(handle)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    if os.name == "nt":
        try:
            subprocess.run(["clip"], input=text, text=True, check=True, timeout=5)
            return True
        except Exception:
            pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def apply_local_friend_change(friend_list: list | None, friend_id: str, action: str = "add") -> list:
    """Agrega o quita un amigo de una lista local sin duplicados."""
    cleaned = [str(item or "").strip() for item in (friend_list or []) if str(item or "").strip()]
    friend_id = str(friend_id or "").strip()
    if not friend_id:
        return cleaned

    if action == "remove":
        return [fid for fid in cleaned if fid != friend_id]

    if friend_id not in cleaned:
        cleaned.append(friend_id)
    return cleaned


def get_friend_display_name(friend: object, local_db=None) -> str:
    """Devuelve el nombre amigable para mostrar de un amigo a partir de su ID o datos asociados."""
    if isinstance(friend, dict):
        for key in ("display_name", "tapo_name", "name", "username", "friend_name"):
            value = str(friend.get(key) or "").strip()
            if value:
                return value
        friend_id = str(friend.get("friend_id") or "").strip()
    else:
        friend_id = str(getattr(friend, "friend_id", friend) or "").strip()

    if friend_id and local_db and hasattr(local_db, "cargar_tapo"):
        tapo_doc = local_db.cargar_tapo(friend_id)
        if tapo_doc is not None:
            name = getattr(tapo_doc, "nombre", None) or getattr(tapo_doc, "name", None)
            if name:
                return str(name).strip()

    return friend_id


def get_friend_recommendations(screen) -> list[dict]:
    """Devuelve una lista breve de sugerencias basadas en los amigos de los amigos."""
    if hasattr(screen, "recommendations") and screen.recommendations:
        return screen.recommendations

    current_ids = {str(friend.get("friend_id") or "").strip() for friend in getattr(screen, "friends", []) if friend.get("friend_id")}
    current_ids.add(str(getattr(getattr(screen, "tapo", None), "id_mascota", "") or "").strip())

    recommendations: list[dict] = []
    seen_ids: set[str] = set()
    local_db = getattr(screen, "local_db", None)

    for friend in getattr(screen, "friends", []):
        friend_id = str(friend.get("friend_id") or "").strip()
        if not friend_id:
            continue

        tapo_doc = local_db.cargar_tapo(friend_id) if local_db and hasattr(local_db, "cargar_tapo") else None
        friend_ids = getattr(tapo_doc, "friend_list", []) or [] if tapo_doc else []

        for suggested_id in friend_ids:
            suggested_id = str(suggested_id or "").strip()
            if not suggested_id or suggested_id in current_ids or suggested_id in seen_ids:
                continue

            suggested_tapo = local_db.cargar_tapo(suggested_id) if local_db and hasattr(local_db, "cargar_tapo") else None
            name = getattr(suggested_tapo, "nombre", None) or suggested_id

            seen_ids.add(suggested_id)
            recommendations.append({
                "friend_id": suggested_id,
                "name": name,
            })
            if len(recommendations) >= 4:
                return recommendations

    return recommendations


def resolve_friend_target(
    query: str,
    local_db,
    current_tapo_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resuelve un nombre o ID en el ID real del Tapo a agregar."""
    raw_query = (query or "").strip()
    if not raw_query:
        return None, None

    if hasattr(local_db, "buscar_tapos_por_texto"):
        matches = local_db.buscar_tapos_por_texto(raw_query) or []
        if len(matches) == 1:
            match = matches[0]
            friend_id = match.get("id_mascota") or match.get("friend_id")
            if friend_id and friend_id != current_tapo_id:
                return friend_id, match.get("nombre")
        if len(matches) > 1:
            return None, "multiple"

    return raw_query, None
