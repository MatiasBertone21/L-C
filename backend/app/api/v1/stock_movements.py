from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_database
from app.core.security import require_admin
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import SupplierCatalogRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.product import StockMovementReason, StockMovementResponse, StockMovementType
from app.services.product_service import ProductService

router = APIRouter(
    prefix="/stock-movements",
    tags=["Stock Movements"],
    dependencies=[Depends(require_admin)],
)


def get_product_service(db: AsyncDatabase = Depends(get_database)) -> ProductService:
    return ProductService(
        product_repo=ProductRepository(db),
        catalog_repo=SupplierCatalogRepository(db),
        user_repo=UserRepository(db),
    )


@router.get(
    "",
    response_model=PaginatedResponse[StockMovementResponse],
    summary="Listar historial auditable de movimientos de stock con filtros (solo admin)",
)
async def list_stock_movements(
    product_id: str | None = Query(default=None),
    movement_type: StockMovementType | None = Query(default=None, alias="type"),
    reason: StockMovementReason | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: ProductService = Depends(get_product_service),
) -> PaginatedResponse[StockMovementResponse]:
    return await service.list_stock_movements(
        product_id=product_id,
        mov_type=movement_type,
        reason=reason,
        q=q,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
