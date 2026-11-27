from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_database
from app.core.security import get_current_user
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_auth_service(db: AsyncDatabase = Depends(get_database)) -> AuthService:
    return AuthService(UserRepository(db))


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión con email y contraseña")
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.login(payload)


@router.get("/me", response_model=UserResponse, summary="Obtener perfil del usuario autenticado")
async def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    return current_user
