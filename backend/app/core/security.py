from datetime import datetime, timedelta, timezone
import hmac
from typing import Any, Callable

import bcrypt
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.database import get_database
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserResponse, UserRole

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(
    *,
    subject: str,
    email: str,
    role: UserRole,
) -> tuple[str, int]:
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured. Check your .env file.")

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    expire_at = now + expires_delta

    payload: dict[str, Any] = {
        "sub": subject,
        "email": email,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }
    encoded_jwt = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured. Check your .env file.")
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("La sesión ha expirado. Iniciá sesión nuevamente.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Token de autenticación inválido.") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncDatabase = Depends(get_database),
) -> UserResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Token de autenticación requerido.")

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise UnauthorizedError("Token de autenticación inválido.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("Usuario no encontrado.")
    if not user.is_active:
        raise ForbiddenError("La cuenta de usuario se encuentra inactiva.")

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def require_roles(*allowed_roles: UserRole) -> Callable[..., Any]:
    async def role_dependency(
        current_user: UserResponse = Depends(get_current_user),
    ) -> UserResponse:
        if current_user.role not in allowed_roles:
            raise ForbiddenError("No tiene permisos suficientes para realizar esta acción.")
        return current_user

    return role_dependency


require_admin = require_roles(UserRole.ADMIN)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    """Server-to-server optional API Key dependency for future batch/import scripts."""
    configured_key = settings.internal_api_key
    if not configured_key or not api_key:
        raise UnauthorizedError("API Key inválida o ausente.")

    if not hmac.compare_digest(api_key, configured_key):
        raise UnauthorizedError("API Key inválida o ausente.")

    return api_key
