from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.config import COL_INBOX, COL_MASCOTAS, COL_USUARIOS
from server.services.social_service import add_friend, get_social_state, remove_friend, send_gift
from server.tests.conftest import TEST_TAPO_ID, TEST_USER_ID, requires_mongo


@requires_mongo
class TestSocialService:
    def test_agregar_y_quitar_amigo(self, mongo_test_data):
        friend_tapo_id = "friend-tapo-001"
        mongo_test_data[COL_MASCOTAS].insert_one({
            "id_mascota": friend_tapo_id,
            "Nombre": "Amigo",
            "Vitales": {},
            "Estadistica": {},
            "Estado_Sistema": False,
            "Last_Sync": "2026-01-01T00:00:00",
            "Friend_List": [],
            "Gift_Cooldowns": [],
        })
        mongo_test_data[COL_USUARIOS].insert_one({
            "Id": "friend-user-001",
            "Username": "amigo",
            "Correo": "amigo@tapomon.cl",
            "Password": "hash",
            "Tapo_ID": friend_tapo_id,
        })

        added = add_friend(TEST_USER_ID, friend_tapo_id)
        assert added["success"] is True

        tapo_doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        assert friend_tapo_id in tapo_doc["Friend_List"]

        social_state = get_social_state(TEST_USER_ID)
        assert any(friend["friend_id"] == friend_tapo_id for friend in social_state["friends"])

        removed = remove_friend(TEST_USER_ID, friend_tapo_id)
        assert removed["success"] is True

        tapo_doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        assert friend_tapo_id not in tapo_doc["Friend_List"]

    def test_enviar_regalo_crea_inbox_y_cooldown(self, mongo_test_data):
        friend_tapo_id = "friend-tapo-002"
        mongo_test_data[COL_MASCOTAS].insert_one({
            "id_mascota": friend_tapo_id,
            "Nombre": "Amigo 2",
            "Vitales": {},
            "Estadistica": {},
            "Estado_Sistema": False,
            "Last_Sync": "2026-01-01T00:00:00",
            "Friend_List": [],
            "Gift_Cooldowns": [],
        })
        mongo_test_data[COL_USUARIOS].insert_one({
            "Id": "friend-user-002",
            "Username": "amigo2",
            "Correo": "amigo2@tapomon.cl",
            "Password": "hash",
            "Tapo_ID": friend_tapo_id,
        })

        result = send_gift(TEST_USER_ID, friend_tapo_id, gift_type="comida")
        assert result["success"] is True

        inbox_doc = mongo_test_data[COL_INBOX].find_one({"Recipient_ID": friend_tapo_id})
        assert inbox_doc is not None
        assert inbox_doc["Payload"]["tipo"] == "regalo"

        tapo_doc = mongo_test_data[COL_MASCOTAS].find_one({"id_mascota": TEST_TAPO_ID})
        assert any(entry["friend_id"] == friend_tapo_id for entry in tapo_doc["Gift_Cooldowns"])
