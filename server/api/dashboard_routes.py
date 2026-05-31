"""
server/api/dashboard_routes.py
Endpoints administrativos para el Dashboard de desarrollador.
Facilitan el monitoreo en tiempo real, el sembrado y la manipulación de estados de las mascotas.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.config import COL_MASCOTAS, COL_USUARIOS
from server.db.mongo import get_db
from server.db.seed import sembrar_base_de_datos
from server.db.fast_forward import fast_forward_tapo
from server.services.idle_engine import ejecutar_idle_tick

router = APIRouter()


class FastForwardRequest(BaseModel):
    tapo_id: str
    hours: float


@router.get("/stats")
async def get_dashboard_stats():
    """
    Retorna estadísticas globales del servidor y la lista de todos los Tapos
    con sus dueños correspondientes y estados en tiempo real.
    """
    try:
        db = get_db()
        
        # 1. Mapear Tapo_ID -> Username
        usuarios_cursor = db[COL_USUARIOS].find({}, {"Tapo_ID": 1, "Username": 1})
        owner_map = {}
        for u in usuarios_cursor:
            t_id = u.get("Tapo_ID")
            uname = u.get("Username")
            if t_id and uname:
                owner_map[t_id] = uname
                
        # 2. Recuperar todos los Tapos
        tapos_cursor = db[COL_MASCOTAS].find({})
        tapos = []
        total_active = 0
        total_idle = 0
        
        for t in tapos_cursor:
            t.pop("_id", None)
            t_id = t.get("id_mascota")
            t["Propietario"] = owner_map.get(t_id, "Sin Dueño")
            
            # Normalizar Last_Sync para visualización
            last_sync = t.get("Last_Sync", "")
            
            if t.get("Estado_Sistema"):
                total_active += 1
            else:
                total_idle += 1
                
            tapos.append(t)
            
        return {
            "stats": {
                "total_users": len(owner_map),
                "total_tapos": len(tapos),
                "active_tapos": total_active,
                "idle_tapos": total_idle
            },
            "tapos": tapos
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener estadísticas del dashboard: {e}"
        )


@router.post("/seed")
async def run_seed():
    """Limpia y siembra la base de datos con datos simulados."""
    try:
        sembrar_base_de_datos()
        return {
            "success": True,
            "message": "Base de datos restablecida y sembrada con éxito."
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al ejecutar sembrado de base de datos: {e}"
        )


@router.post("/fast-forward")
async def run_fast_forward(req: FastForwardRequest):
    """Resta horas a Last_Sync de un Tapo para simular tiempo desconectado y calcula la degradación automáticamente."""
    try:
        success = fast_forward_tapo(req.tapo_id, req.hours)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró el Tapo con ID o Nombre '{req.tapo_id}'."
            )
        
        # Ejecutar inmediatamente la degradación del simulador IDLE de forma automática
        ejecutar_idle_tick()
        
        return {
            "success": True,
            "message": f"Viaje en el tiempo de -{req.hours} horas aplicado y procesado automáticamente por el Simulador IDLE."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al aplicar viaje en el tiempo: {e}"
        )


@router.post("/tick")
async def force_tick():
    """Ejecuta inmediatamente un tick del motor IDLE."""
    try:
        procesados = ejecutar_idle_tick()
        return {
            "success": True,
            "message": f"Simulación IDLE ejecutada manualmente. {procesados} mascota(s) procesada(s).",
            "processed": procesados
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al forzar tick del simulador IDLE: {e}"
        )
