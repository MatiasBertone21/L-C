from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.user_repository.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise UnauthorizedError("Credenciales inválidas.")

        if not user.is_active:
            raise ForbiddenError("La cuenta de usuario se encuentra inactiva.")

        access_token, expires_in = create_access_token(
            subject=user.id,
            email=user.email,
            role=user.role,
        )
        user_response = UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user_response,
        )
