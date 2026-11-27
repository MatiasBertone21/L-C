from typing import Literal
from fastapi import APIRouter, Depends, Query, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_database
from app.core.security import get_current_user, require_admin
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import SupplierCatalogRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.product import (
    InventorySummaryResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
    StockAdjustRequest,
)
from app.schemas.user import UserResponse
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products & Stock"])


def get_product_service(db: AsyncDatabase = Depends(get_database)) -> ProductService:
    return ProductService(
        product_repo=ProductRepository(db),
        catalog_repo=SupplierCatalogRepository(db),
        user_repo=UserRepository(db),
    )


@router.get(
    "",
    response_model=PaginatedResponse[ProductResponse],
    summary="Listar productos del stock propio con búsqueda, alertas y paginación",
)
async def list_products(
    q: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=100),
    is_active: bool | None = Query(default=True),
    stock_alert: Literal["all", "low_stock", "out_of_stock"] = Query(default="all"),
    has_supplier: bool | None = Query(default=None),
    sort: Literal[
        "name",
        "sku",
        "stock",
        "-stock",
        "unit_price",
        "-unit_price",
        "-updated_at",
    ] = Query(default="name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _current_user: UserResponse = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> PaginatedResponse[ProductResponse]:
    return await service.list_products(
        q=q,
        category=category,
        is_active=is_active,
        stock_alert=stock_alert,
        has_supplier=has_supplier,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/summary",
    response_model=InventorySummaryResponse,
    summary="Obtener KPIs de stock (activos, stock bajo, sin stock) y categorías",
)
async def get_inventory_summary(
    _current_user: UserResponse = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> InventorySummaryResponse:
    return await service.get_inventory_summary()


@router.get(
    "/lookup/{code}",
    response_model=ProductResponse,
    summary="Buscar producto activo exacto por código de barras o SKU (lector POS)",
)
async def lookup_product_by_code(
    code: str,
    _current_user: UserResponse = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.lookup_by_code(code)


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Obtener detalle de un producto y sus últimos movimientos de stock",
)
async def get_product_detail(
    product_id: str,
    _current_user: UserResponse = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> ProductDetailResponse:
    return await service.get_product_detail(product_id)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo producto propio con movimiento inicial trazado (solo admin)",
)
async def create_product(
    payload: ProductCreate,
    current_user: UserResponse = Depends(require_admin),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.create_product(payload, current_user)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Actualizar precio de venta o datos maestros de un producto (solo admin)",
)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    _current_user: UserResponse = Depends(require_admin),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.update_product(product_id, payload)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja lógica un producto (solo admin)",
)
async def delete_product(
    product_id: str,
    _current_user: UserResponse = Depends(require_admin),
    service: ProductService = Depends(get_product_service),
) -> Response:
    await service.soft_delete_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{product_id}/stock",
    response_model=ProductDetailResponse,
    summary="Registrar ingreso, egreso o ajuste físico atómico de stock (solo admin)",
)
async def adjust_product_stock(
    product_id: str,
    payload: StockAdjustRequest,
    current_user: UserResponse = Depends(require_admin),
    service: ProductService = Depends(get_product_service),
) -> ProductDetailResponse:
    return await service.adjust_product_stock(product_id, payload, current_user)
