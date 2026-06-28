from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from server.api.auth_routes import get_current_user
from server.models.schemas import (
    SocialFriendRequest,
    SocialGiftRequest,
    SocialGiftResponse,
    SocialStateResponse,
)
from server.services.social_service import add_friend, get_social_state, remove_friend, send_gift

router = APIRouter()


@router.get("/friends", response_model=SocialStateResponse)
async def list_friends(current_user: dict = Depends(get_current_user)):
    """Devuelve la lista de amigos y los cooldowns del Tapo del usuario autenticado."""
    usuario_id = current_user["sub"]
    state = get_social_state(usuario_id)
    if not state["success"]:
        raise HTTPException(status_code=404, detail=state["message"])

    return SocialStateResponse(**state)


@router.post("/friends", response_model=SocialStateResponse)
async def add_friend_route(
    request: SocialFriendRequest,
    current_user: dict = Depends(get_current_user),
):
    """Agrega un amigo al Tapo del usuario autenticado."""
    usuario_id = current_user["sub"]
    result = add_friend(usuario_id, request.friend_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    state = get_social_state(usuario_id)
    return SocialStateResponse(**state)


@router.delete("/friends/{friend_id}", response_model=SocialStateResponse)
async def remove_friend_route(
    friend_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Quita un amigo del Tapo del usuario autenticado."""
    usuario_id = current_user["sub"]
    result = remove_friend(usuario_id, friend_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    state = get_social_state(usuario_id)
    return SocialStateResponse(**state)


@router.post("/gift", response_model=SocialGiftResponse)
async def send_gift_route(
    request: SocialGiftRequest,
    current_user: dict = Depends(get_current_user),
):
    """Envía un regalo a un amigo del Tapo del usuario autenticado."""
    usuario_id = current_user["sub"]
    result = send_gift(
        usuario_id,
        request.friend_id,
        gift_type=request.gift_type,
        message=request.message,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return SocialGiftResponse(**result)
