import secrets
from fastapi import Depends
from httpx import AsyncClient
import pytest

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import verify_api_key
from app.main import app


async def _login_and_get_token(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    return body["access_token"]


async def test_login_success_and_me_profile(
    client: AsyncClient,
    test_credentials: dict[str, str],
) -> None:
    token = await _login_and_get_token(
        client,
        test_credentials["admin_email"],
        test_credentials["admin_password"],
    )

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["email"] == test_credentials["admin_email"]
    assert me_body["role"] == "admin"
    assert "password_hash" not in me_body


async def test_login_invalid_credentials_returns_401(
    client: AsyncClient,
    test_credentials: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_credentials["admin_email"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_protected_endpoint_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_role_authorization_blocks_user_and_allows_admin(
    client: AsyncClient,
    test_credentials: dict[str, str],
) -> None:
    user_token = await _login_and_get_token(
        client,
        test_credentials["user_email"],
        test_credentials["user_password"],
    )
    admin_token = await _login_and_get_token(
        client,
        test_credentials["admin_email"],
        test_credentials["admin_password"],
    )

    # User role cannot list or create users
    forbidden_list = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert forbidden_list.status_code == 403

    new_password = f"New_{secrets.token_urlsafe(10)}"
    forbidden_create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "email": "nuevo@librerialc.com.ar",
            "full_name": "Nuevo Vendedor",
            "password": new_password,
            "role": "user",
        },
    )
    assert forbidden_create.status_code == 403

    # Admin role can create, list (paginated) and detect duplicate email
    created = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "nuevo@librerialc.com.ar",
            "full_name": "Nuevo Vendedor",
            "password": new_password,
            "role": "user",
        },
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["email"] == "nuevo@librerialc.com.ar"
    assert created_body["role"] == "user"
    assert "password_hash" not in created_body

    duplicate = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "NUEVO@librerialc.com.ar",
            "full_name": "Duplicado",
            "password": new_password,
            "role": "user",
        },
    )
    assert duplicate.status_code == 409

    listed = await client.get(
        "/api/v1/users?page=1&page_size=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["total"] == 3
    assert len(listed_body["items"]) == 3


async def test_verify_api_key_dependency() -> None:
    with pytest.raises(UnauthorizedError):
        await verify_api_key(None)

    with pytest.raises(UnauthorizedError):
        await verify_api_key("invalid-key")

    valid = await verify_api_key(settings.internal_api_key)
    assert valid == settings.internal_api_key
    assert Depends(verify_api_key) is not None
