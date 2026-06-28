"""
tests/test_sync_service.py
Tests unitarios del SyncService (lógica de negocio).

TODOS estos tests requieren MongoDB ya que sync_upload y resume_state
operan directamente sobre la base de datos.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.services.sync_service import (
    normalizar_friend_list,
    sync_upload,
    resume_state,
    verificar_propietario,
)
from server.config import COL_MASCOTAS, COL_INBOX
from server.tests.conftest import (
    TEST_USER_ID, TEST_TAPO_ID, TEST_TAPO_DOC, requires_mongo,
)


class TestFriendListNormalization:
    """Prueba que la lista de amigos del Tapo se normalice a una lista de ids válida."""

    def test_normaliza_lista_vacia_y_nombres_validos(self):
        assert normalizar_friend_list(None) == []
        assert normalizar_friend_list([]) == []
        assert normalizar_friend_list(["tapo-1", "tapo-2"]) == ["tapo-1", "tapo-2"]

    def test_elimina_duplicados_y_valores_vacios(self):
        assert normalizar_friend_list(["tapo-1", "", "tapo-1", None, "tapo-2"]) == ["tapo-1", "tapo-2"]

    def test_convierte_un_valor_simple_en_lista(self):
        assert normalizar_friend_list("tapo-3") == ["tapo-3"]


@requires_mongo
class TestSyncUpload:
    """Tests de sync_upload — requiere MongoDB."""

    def test_upload_exitoso(self, mongo_test_data):
        """Subir un estado válido retorna True."""
        state = TEST_TAPO_DOC.copy()
        state.pop("_id", None)
        result = sync_upload(TEST_TAPO_ID, state)
        assert result is True

    def test_upload_marca_idle(self, mongo_test_data):
        """El estado subido se marca como IDLE (Estado_Sistema: false)."""
        state = TEST_TAPO_DOC.copy()
        state.pop("_id", None)
        state["Estado_Sistema"] = True

        sync_upload(TEST_TAPO_ID, state)

        doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        assert doc["Estado_Sistema"] is False

    def test_upload_actualiza_last_sync(self, mongo_test_data):
        """sync_upload actualiza el Last_Sync al momento actual."""
        state = TEST_TAPO_DOC.copy()
        state.pop("_id", None)
        before = datetime.now()

        sync_upload(TEST_TAPO_ID, state)

        doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        last_sync = datetime.fromisoformat(doc["Last_Sync"])
        assert last_sync >= before

    def test_upload_preserva_vitales(self, mongo_test_data):
        """Los vitales se guardan correctamente."""
        state = TEST_TAPO_DOC.copy()
        state.pop("_id", None)
        state["Vitales"]["hambre"] = 42

        sync_upload(TEST_TAPO_ID, state)

        doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        assert doc["Vitales"]["hambre"] == 42


@requires_mongo
class TestResumeState:
    """Tests de resume_state — requiere MongoDB."""

    def test_resume_exitoso(self, mongo_test_data):
        """Resume retorna estado y inbox."""
        result = resume_state(TEST_USER_ID)
        assert result is not None
        assert "tapo" in result
        assert "inbox" in result
        assert result["tapo"]["id_mascota"] == TEST_TAPO_ID

    def test_resume_marca_active(self, mongo_test_data):
        """Al hacer resume, el Tapo se marca como ACTIVE."""
        mongo_test_data[COL_MASCOTAS].update_one(
            {"id_mascota": TEST_TAPO_ID},
            {"$set": {"Estado_Sistema": False}}
        )

        result = resume_state(TEST_USER_ID)
        assert result["tapo"]["Estado_Sistema"] is True

    def test_resume_usuario_inexistente(self, mongo_test_data):
        """Resume con usuario que no existe retorna None."""
        result = resume_state("usuario-fantasma")
        assert result is None

    def test_resume_incluye_inbox(self, mongo_test_data):
        """Resume incluye mensajes del Inbox no reclamados."""
        mongo_test_data[COL_INBOX].insert_one({
            "ID_Mensaje":   "msg-test-001",
            "Recipient_ID": TEST_TAPO_ID,
            "Sender_ID":    "otro-tapo",
            "Payload":      {"tipo": "regalo", "item": "comida"},
            "Status":       False,
            "Timestamp":    datetime.now(),
        })

        result = resume_state(TEST_USER_ID)
        assert len(result["inbox"]) >= 1
        assert result["inbox"][0]["ID_Mensaje"] == "msg-test-001"

    def test_resume_no_incluye_reclamados(self, mongo_test_data):
        """Resume NO incluye mensajes ya reclamados (Status: true)."""
        mongo_test_data[COL_INBOX].insert_one({
            "ID_Mensaje":   "msg-claimed",
            "Recipient_ID": TEST_TAPO_ID,
            "Sender_ID":    "otro-tapo",
            "Payload":      {"tipo": "regalo"},
            "Status":       True,
            "Timestamp":    datetime.now(),
        })

        result = resume_state(TEST_USER_ID)
        ids = [m["ID_Mensaje"] for m in result["inbox"]]
        assert "msg-claimed" not in ids


@requires_mongo
class TestVerificarPropietario:
    """Tests de verificación de propiedad — requiere MongoDB."""

    def test_propietario_valido(self, mongo_test_data):
        assert verificar_propietario(TEST_USER_ID, TEST_TAPO_ID) is True

    def test_propietario_invalido(self, mongo_test_data):
        assert verificar_propietario("otro-usuario", TEST_TAPO_ID) is False

    def test_usuario_inexistente(self, mongo_test_data):
        assert verificar_propietario("fantasma", TEST_TAPO_ID) is False
