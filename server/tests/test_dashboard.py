"""
tests/test_dashboard.py
Tests de integración para los endpoints y rutas del Dashboard de desarrollador.
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.tests.conftest import requires_mongo


@requires_mongo
class TestDashboardRoutes:
    """Tests para los endpoints administrativos del Dashboard."""

    def test_serve_dashboard(self, app_client):
        """Verifica que la página principal del Dashboard HTML se sirve correctamente."""
        resp = app_client.get("/dashboard")
        assert resp.status_code == 200
        assert "TapoMon Developer Dashboard" in resp.text

    def test_get_stats(self, app_client, mongo_test_data):
        """Verifica que se recuperen estadísticas globales del sistema."""
        resp = app_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        assert "tapos" in data
        assert "total_users" in data["stats"]
        assert "total_tapos" in data["stats"]

    def test_seed_database(self, app_client):
        """Verifica que el endpoint de sembrado limpie y pueble la DB."""
        resp = app_client.post("/api/dashboard/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "sembrada" in data["message"]

    def test_fast_forward(self, app_client, mongo_test_data):
        """Verifica que el viaje en el tiempo funcione sobre un Tapo sembrado."""
        # Asegurar datos sembrados
        app_client.post("/api/dashboard/seed")

        resp = app_client.post("/api/dashboard/fast-forward", json={
            "tapo_id": "tapo-fuego-001",
            "hours": 5.0
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_fast_forward_tapo_inexistente(self, app_client, mongo_test_data):
        """Verifica que el viaje en el tiempo retorne 404 para un Tapo inexistente."""
        resp = app_client.post("/api/dashboard/fast-forward", json={
            "tapo_id": "tapo-fantasma",
            "hours": 5.0
        })
        assert resp.status_code == 404

    def test_force_tick(self, app_client, mongo_test_data):
        """Verifica la ejecución manual del tick IDLE."""
        # Asegurar datos sembrados
        app_client.post("/api/dashboard/seed")

        resp = app_client.post("/api/dashboard/tick")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "processed" in data
