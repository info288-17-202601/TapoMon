"""
tests/test_integration.py
Tests de integración del servidor TapoMon.

TODOS requieren MongoDB ya que el servidor completo necesita la DB.
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.tests.conftest import (
    TEST_USERNAME, TEST_PASSWORD, TEST_USER_ID, TEST_TAPO_ID,
    TEST_TAPO_DOC, requires_mongo,
)


@requires_mongo
class TestHealthCheck:
    """Test del endpoint de salud."""

    def test_health(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "TapoMon Central Server"


@requires_mongo
class TestLoginEndpoint:
    """Tests del endpoint POST /auth/login."""

    def test_login_exitoso(self, app_client, mongo_test_data):
        """Login con credenciales válidas retorna token."""
        resp = app_client.post("/auth/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["usuario_id"] == TEST_USER_ID
        assert data["token_type"] == "bearer"

    def test_login_fallido(self, app_client, mongo_test_data):
        """Login con password incorrecto retorna 401."""
        resp = app_client.post("/auth/login", json={
            "username": TEST_USERNAME,
            "password": "wrongpass",
        })
        assert resp.status_code == 401


@requires_mongo
class TestSyncUploadEndpoint:
    """Tests del endpoint POST /sync/upload."""

    def test_upload_exitoso(self, app_client, auth_headers, mongo_test_data):
        """Upload con token válido y datos correctos retorna 200."""
        payload = TEST_TAPO_DOC.copy()
        payload.pop("_id", None)

        resp = app_client.post(
            "/sync/upload",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tapo_id"] == TEST_TAPO_ID

    def test_upload_sin_token(self, app_client, mongo_test_data):
        """Upload sin token retorna 401."""
        payload = TEST_TAPO_DOC.copy()
        payload.pop("_id", None)

        resp = app_client.post("/sync/upload", json=payload)
        assert resp.status_code == 401

    def test_upload_tapo_ajeno(self, app_client, auth_headers, mongo_test_data):
        """Upload de un Tapo que no pertenece al usuario retorna 403."""
        from server.config import COL_USUARIOS
        mongo_test_data[COL_USUARIOS].insert_one({
            "Id": "other-user-id",
            "Username": "otherplayer",
            "Correo": "other@tapomon.cl",
            "Password": "hash",
            "Tapo_ID": "tapo-de-otro-usuario",
        })

        payload = TEST_TAPO_DOC.copy()
        payload.pop("_id", None)
        payload["id_mascota"] = "tapo-de-otro-usuario"

        resp = app_client.post(
            "/sync/upload",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 403


@requires_mongo
class TestResumeStateEndpoint:
    """Tests del endpoint GET /sync/resume/{usuario_id}."""

    def test_resume_exitoso(self, app_client, auth_headers, mongo_test_data):
        """Resume con token válido retorna estado + inbox."""
        resp = app_client.get(
            f"/sync/resume/{TEST_USER_ID}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tapo"]["id_mascota"] == TEST_TAPO_ID
        assert isinstance(data["inbox"], list)

    def test_resume_sin_token(self, app_client, mongo_test_data):
        """Resume sin token retorna 401."""
        resp = app_client.get(f"/sync/resume/{TEST_USER_ID}")
        assert resp.status_code == 401

    def test_resume_usuario_ajeno(self, app_client, auth_headers, mongo_test_data):
        """Resume del estado de otro usuario retorna 403."""
        resp = app_client.get(
            "/sync/resume/otro-usuario-id",
            headers=auth_headers,
        )
        assert resp.status_code == 403


@requires_mongo
class TestFlujoCompleto:
    """Test de integración del flujo completo sync_upload → resume_state."""

    def test_upload_y_resume(self, app_client, auth_headers, mongo_test_data):
        """
        Flujo completo:
        1. Subir estado con hambre=42
        2. Descargar estado
        3. Verificar que hambre se conserva
        """
        # 1. Upload con hambre modificado
        payload = TEST_TAPO_DOC.copy()
        payload.pop("_id", None)
        payload["Vitales"]["hambre"] = 42

        resp_upload = app_client.post(
            "/sync/upload",
            json=payload,
            headers=auth_headers,
        )
        assert resp_upload.status_code == 200

        # 2. Resume
        resp_resume = app_client.get(
            f"/sync/resume/{TEST_USER_ID}",
            headers=auth_headers,
        )
        assert resp_resume.status_code == 200
        data = resp_resume.json()

        # 3. Verificar conservación
        assert data["tapo"]["Vitales"]["hambre"] <= 42
