from fastapi import APIRouter
from app.core.config import settings
from app.core.database import ping_mongo
from app.core.exceptions import ServiceUnavailableError

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Estado de la API y conexión a MongoDB")
async def health_check() -> dict[str, str]:
    db_connected = await ping_mongo()
    if not db_connected:
        raise ServiceUnavailableError("No se pudo establecer conexión con MongoDB.")

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "connected",
        "db_name": settings.mongo_db_name,
    }
