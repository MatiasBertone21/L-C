import math
from typing import Any

from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserRole, UserUpdate


class UserService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def create_user(self, payload: UserCreate) -> UserResponse:
        password_hash = hash_password(payload.password)
        return await self.user_repository.create(
            email=payload.email,
            full_name=payload.full_name,
            password_hash=password_hash,
            role=payload.role,
            is_active=payload.is_active,
        )

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[UserResponse]:
        items, total = await self.user_repository.list_paginated(
            page=page,
            page_size=page_size,
            role=role,
            is_active=is_active,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return PaginatedResponse[UserResponse](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_user(self, user_id: str, payload: UserUpdate) -> UserResponse:
        update_fields: dict[str, Any] = {}
        if payload.full_name is not None:
            update_fields["full_name"] = payload.full_name.strip()
        if payload.role is not None:
            update_fields["role"] = payload.role.value
        if payload.is_active is not None:
            update_fields["is_active"] = payload.is_active
        if payload.password is not None:
            update_fields["password_hash"] = hash_password(payload.password)

        if not update_fields:
            return await self.get_user_by_id(user_id)

        updated = await self.user_repository.update(user_id, update_fields)
        if updated is None:
            raise NotFoundError("Usuario no encontrado.")
        return updated
