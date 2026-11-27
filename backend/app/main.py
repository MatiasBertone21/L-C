from contextlib import asynccontextmanager
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.core.exceptions import register_exception_handlers
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import SupplierCatalogRepository
from app.repositories.user_repository import UserRepository
from app.services.supplier_catalog_service import SupplierCatalogService
from app.services.supplier_parsing import cleanup_expired_canonical_csvs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ensure_database_indexes_and_recover() -> None:
    db = get_database()
    user_repo = UserRepository(db)
    product_repo = ProductRepository(db)
    catalog_repo = SupplierCatalogRepository(db)

    await user_repo.ensure_indexes()
    await product_repo.ensure_indexes()
    await catalog_repo.ensure_indexes()

    catalog_service = SupplierCatalogService(catalog_repo=catalog_repo, product_repo=product_repo)
    await catalog_service.recover_interrupted_imports()
    cleanup_expired_canonical_csvs()
    logger.info("MongoDB indexes verified and supplier catalog ready.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await connect_to_mongo()
    await ensure_database_indexes_and_recover()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

register_exception_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        "%s %s - Status: %s - Time: %.4fs",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"], summary="Información general del servicio")
async def read_root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


app.include_router(health.router)
app.include_router(api_v1_router)
