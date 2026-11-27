from fastapi import APIRouter, Depends, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_database
from app.core.security import require_admin
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserRole, UserUpdate
from app.services.user_service import UserService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(require_admin)],
)


def get_user_service(db: AsyncDatabase = Depends(get_database)) -> UserService:
    return UserService(UserRepository(db))


@router.get(
    "",
    response_model=PaginatedResponse[UserResponse],
    summary="Listar usuarios con paginación (solo admin)",
)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    service: UserService = Depends(get_user_service),
) -> PaginatedResponse[UserResponse]:
    return await service.list_users(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo usuario (solo admin)",
)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.create_user(payload)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Obtener detalle de usuario por ID (solo admin)",
)
async def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.get_user_by_id(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Actualizar usuario existente (solo admin)",
)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.update_user(user_id, payload)
