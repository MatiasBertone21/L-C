import logging
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import settings

logger = logging.getLogger(__name__)

_mongo_client: AsyncMongoClient | None = None


async def connect_to_mongo() -> None:
    global _mongo_client
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is not configured. Check your .env file.")

    _mongo_client = AsyncMongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    await _mongo_client.admin.command("ping")
    logger.info("Connected to MongoDB (target db: '%s').", settings.mongo_db_name)


async def close_mongo_connection() -> None:
    global _mongo_client
    if _mongo_client is not None:
        await _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB connection closed.")


def get_database() -> AsyncDatabase:
    if _mongo_client is None:
        raise RuntimeError("MongoDB client is not initialized.")
    return _mongo_client[settings.mongo_db_name]


async def ping_mongo() -> bool:
    if _mongo_client is None:
        return False
    try:
        await _mongo_client.admin.command("ping")
        return True
    except Exception as exc:
        logger.error("MongoDB ping failed: %s", exc)
        return False
