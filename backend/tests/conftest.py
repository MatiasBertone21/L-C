import secrets
from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
import pytest

from app.core.config import settings
from app.core.database import get_database
from app.core.security import hash_password
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserRole


@pytest.fixture
def test_credentials() -> dict[str, str]:
    return {
        "admin_email": "admin.test@librerialc.com.ar",
        "admin_password": f"Adm_{secrets.token_urlsafe(12)}",
        "user_email": "user.test@librerialc.com.ar",
        "user_password": f"Usr_{secrets.token_urlsafe(12)}",
    }


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch,
    test_credentials: dict[str, str],
) -> AsyncGenerator[AsyncClient, None]:
    base_db_name = settings.mongo_db_name.removesuffix("_test")
    monkeypatch.setattr(settings, "mongo_db_name", f"{base_db_name}_test")
    monkeypatch.setattr(settings, "jwt_secret_key", secrets.token_hex(32))
    monkeypatch.setattr(settings, "internal_api_key", secrets.token_hex(16))

    async with app.router.lifespan_context(app):
        db = get_database()
        for coll_name in (
            "users",
            "products",
            "stock_movements",
            "supplier_imports",
            "supplier_catalog_items",
            "price_change_history",
            "supplier_import_locks",
        ):
            await db[coll_name].delete_many({})

        user_repo = UserRepository(db)
        await user_repo.create(
            email=test_credentials["admin_email"],
            full_name="Admin Test",
            password_hash=hash_password(test_credentials["admin_password"]),
            role=UserRole.ADMIN,
            is_active=True,
        )
        await user_repo.create(
            email=test_credentials["user_email"],
            full_name="Seller Test",
            password_hash=hash_password(test_credentials["user_password"]),
            role=UserRole.USER,
            is_active=True,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client

        for coll_name in (
            "users",
            "products",
            "stock_movements",
            "supplier_imports",
            "supplier_catalog_items",
            "price_change_history",
            "supplier_import_locks",
        ):
            await db[coll_name].delete_many({})
