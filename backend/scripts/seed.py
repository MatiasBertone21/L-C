import asyncio
import logging

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRole
from app.services.user_service import UserService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


async def seed_users() -> None:
    if not settings.seed_admin_password or not settings.seed_user_password:
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD y SEED_USER_PASSWORD deben estar definidos en .env para ejecutar el seed."
        )

    await connect_to_mongo()
    try:
        db = get_database()
        await db["users"].delete_many({"email": {"$regex": r"\.local$"}})

        user_repo = UserRepository(db)
        await user_repo.ensure_indexes()
        user_service = UserService(user_repo)

        users_to_seed = [
            UserCreate(
                email=settings.seed_admin_email,
                full_name="Administración L&C",
                password=settings.seed_admin_password,
                role=UserRole.ADMIN,
                is_active=True,
            ),
            UserCreate(
                email=settings.seed_user_email,
                full_name="Mostrador Ventas L&C",
                password=settings.seed_user_password,
                role=UserRole.USER,
                is_active=True,
            ),
        ]

        for payload in users_to_seed:
            existing = await user_repo.get_by_email(payload.email)
            if existing is not None:
                logger.info("Usuario '%s' (%s) ya existe — omitiendo.", existing.email, existing.role.value)
                continue

            created = await user_service.create_user(payload)
            logger.info("Usuario creado: '%s' con rol '%s'.", created.email, created.role.value)
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed_users())
