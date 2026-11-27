from typing import Literal
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_database
from app.core.security import get_current_user, require_admin
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import SupplierCatalogRepository
from app.schemas.common import PaginatedResponse
from app.schemas.supplier_catalog import (
    CatalogFiltersResponse,
    CatalogItemDetailResponse,
    CatalogItemListItem,
    ChangeTypeVisible,
    ImportStatus,
    LatestImportStatusResponse,
    LoadToStockRequest,
    LoadToStockResponse,
    PriceChangeEventItem,
    PriceChangesSummaryResponse,
    PurgeDiscontinuedResponse,
    RollbackImportResponse,
    SupplierImportDetail,
    SupplierImportSummary,
)
from app.schemas.user import UserResponse
from app.services.supplier_catalog_service import SupplierCatalogService

router = APIRouter(prefix="/supplier-catalog", tags=["Supplier Catalog"])


def get_supplier_catalog_service(db: AsyncDatabase = Depends(get_database)) -> SupplierCatalogService:
    return SupplierCatalogService(
        catalog_repo=SupplierCatalogRepository(db),
        product_repo=ProductRepository(db),
    )


@router.post(
    "/imports",
    response_model=SupplierImportSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Subir y procesar lista diaria del proveedor (solo admin)",
)
async def upload_supplier_list(
    file: UploadFile = File(...),
    force: bool = Form(default=False),
    current_user: UserResponse = Depends(require_admin),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> SupplierImportSummary:
    raw_bytes = await file.read()
    return await service.process_daily_upload(
        raw_bytes=raw_bytes,
        filename=file.filename,
        current_user=current_user,
        force=force,
    )


@router.get(
    "/imports/latest",
    response_model=LatestImportStatusResponse,
    summary="Obtener estado de la última carga y contadores del catálogo",
)
async def get_latest_import_status(
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> LatestImportStatusResponse:
    return await service.get_latest_status()


@router.get(
    "/imports",
    response_model=PaginatedResponse[SupplierImportSummary],
    summary="Listar historial de importaciones de listas",
)
async def list_supplier_imports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ImportStatus | None = Query(default=None, alias="status"),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> PaginatedResponse[SupplierImportSummary]:
    return await service.list_imports(
        page=page,
        page_size=page_size,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/imports/{import_id}",
    response_model=SupplierImportDetail,
    summary="Obtener detalle de una importación y sus advertencias",
)
async def get_supplier_import_detail(
    import_id: str,
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> SupplierImportDetail:
    return await service.get_import_detail(import_id)


@router.post(
    "/imports/{import_id}/rollback",
    response_model=RollbackImportResponse,
    summary="Deshacer por completo la última importación vigente (solo admin)",
)
async def rollback_latest_supplier_import(
    import_id: str,
    current_user: UserResponse = Depends(require_admin),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> RollbackImportResponse:
    return await service.rollback_latest_import(import_id, current_user)


@router.delete(
    "/imports/{import_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar del historial una importación antigua sin afectar catálogo vigente (solo admin)",
)
async def delete_historical_supplier_import(
    import_id: str,
    current_user: UserResponse = Depends(require_admin),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> Response:
    await service.delete_historical_import(import_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/items",
    response_model=PaginatedResponse[CatalogItemListItem],
    summary="Consultar catálogo maestro del proveedor con búsqueda y filtros",
)
async def list_catalog_items(
    q: str | None = Query(default=None, max_length=120),
    packaging: str | None = Query(default=None, max_length=40),
    is_liquidation: bool | None = Query(default=None),
    stock_status: Literal["all", "in_stock", "not_in_stock"] = Query(default="all"),
    changed_within_days: int | None = Query(default=None, ge=0, le=365),
    status_filter: Literal["active", "discontinued", "all"] = Query(default="active", alias="status"),
    price_anomaly: bool | None = Query(default=None),
    sort: Literal[
        "description",
        "code",
        "-last_price_changed_at",
        "price_with_vat",
        "-price_with_vat",
    ] = Query(default="description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> PaginatedResponse[CatalogItemListItem]:
    return await service.list_catalog_items(
        q=q,
        packaging=packaging,
        is_liquidation=is_liquidation,
        stock_status=stock_status,
        changed_within_days=changed_within_days,
        status=status_filter,
        price_anomaly=price_anomaly,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/items/filters",
    response_model=CatalogFiltersResponse,
    summary="Obtener valores disponibles de empaque y contadores de estado",
)
async def get_catalog_filters(
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> CatalogFiltersResponse:
    return await service.get_catalog_filters()


@router.delete(
    "/items/discontinued",
    response_model=PurgeDiscontinuedResponse,
    summary="Depurar productos discontinuados no vinculados al stock propio (solo admin)",
)
async def purge_discontinued_items(
    current_user: UserResponse = Depends(require_admin),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> PurgeDiscontinuedResponse:
    return await service.purge_discontinued(current_user)


@router.post(
    "/items/load-to-stock",
    response_model=LoadToStockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar productos seleccionados del catálogo al stock propio (solo admin)",
)
async def load_catalog_items_to_stock(
    payload: LoadToStockRequest,
    current_user: UserResponse = Depends(require_admin),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> LoadToStockResponse:
    return await service.load_items_to_stock(payload, current_user)


@router.get(
    "/items/{code}",
    response_model=CatalogItemDetailResponse,
    summary="Obtener detalle completo e historial reciente de un artículo del catálogo",
)
async def get_catalog_item_detail(
    code: str,
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> CatalogItemDetailResponse:
    return await service.get_catalog_item_detail(code)


@router.get(
    "/price-changes",
    response_model=PaginatedResponse[PriceChangeEventItem],
    summary="Consultar variaciones de precios (Precios Diff) por importación o rango de fechas",
)
async def list_price_changes(
    import_id: str | None = Query(default=None),
    preset: Literal["latest", "today", "last_7_days", "last_30_days"] | None = Query(default=None),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    change_type: list[ChangeTypeVisible] | None = Query(default=None),
    only_my_stock: bool = Query(default=False),
    min_pct: float | None = Query(default=None, ge=0, le=10000),
    q: str | None = Query(default=None, max_length=120),
    sort: Literal["-abs_diff_pct", "-diff_pct", "diff_pct", "-created_at", "code"] = Query(
        default="-abs_diff_pct"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> PaginatedResponse[PriceChangeEventItem]:
    effective_preset = None if preset == "latest" else preset
    return await service.list_price_changes(
        import_id=import_id,
        preset=effective_preset,
        date_from=date_from,
        date_to=date_to,
        change_types=list(change_type) if change_type else None,
        only_my_stock=only_my_stock,
        min_pct=min_pct,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/price-changes/summary",
    response_model=PriceChangesSummaryResponse,
    summary="Obtener KPIs rápidos de variaciones de precios",
)
async def get_price_changes_summary(
    import_id: str | None = Query(default=None),
    preset: Literal["latest", "today", "last_7_days", "last_30_days"] | None = Query(default=None),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    only_my_stock: bool = Query(default=False),
    min_pct: float | None = Query(default=None, ge=0, le=10000),
    q: str | None = Query(default=None, max_length=120),
    _current_user: UserResponse = Depends(get_current_user),
    service: SupplierCatalogService = Depends(get_supplier_catalog_service),
) -> PriceChangesSummaryResponse:
    effective_preset = None if preset == "latest" else preset
    return await service.get_price_changes_summary(
        import_id=import_id,
        preset=effective_preset,
        date_from=date_from,
        date_to=date_to,
        only_my_stock=only_my_stock,
        min_pct=min_pct,
        q=q,
    )
