from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

ImportStatus = Literal["processing", "completed", "failed", "rolled_back"]
ImportMode = Literal["baseline", "full", "quick_validation"]
ChangeTypeVisible = Literal["price_up", "price_down", "new", "discontinued"]


class UploadedBySummary(BaseModel):
    user_id: str
    email: str


class ImportWarningSchema(BaseModel):
    row: int
    code: str
    message: str


class SupplierImportSummary(BaseModel):
    id: str
    supplier: str
    import_date: str
    sequence_in_day: int = 1
    status: ImportStatus
    mode: ImportMode
    original_filename: str
    detected_format: str
    file_size_bytes: int
    file_hash: str
    content_hash: str
    total_items: int
    changed_count: int
    price_up_count: int
    price_down_count: int
    unchanged_count: int
    new_count: int
    reactivated_count: int = 0
    discontinued_count: int
    metadata_updated_count: int = 0
    skipped_rows: int = 0
    invalid_rows: int = 0
    price_anomaly_count: int = 0
    duration_ms: int = 0
    message: str = ""
    is_latest_completed: bool = False
    uploaded_by: UploadedBySummary
    rolled_back_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None


class SupplierImportDetail(SupplierImportSummary):
    warnings: list[ImportWarningSchema] = Field(default_factory=list)


class LatestImportStatusResponse(BaseModel):
    latest_import: SupplierImportSummary | None = None
    active_catalog_count: int = 0
    discontinued_catalog_count: int = 0
    discontinued_alert: bool = False
    discontinued_threshold: int = 100
    in_my_stock_count: int = 0


class SupplierFlagsSchema(BaseModel):
    star_prefix: bool = False
    hash_suffix: bool = False


class CatalogItemListItem(BaseModel):
    id: str
    supplier: str
    code: str
    description: str
    description_clean: str
    supplier_flags: SupplierFlagsSchema
    packaging_raw: str
    packaging: str
    is_liquidation: bool
    liquidation_tag: str | None = None
    price_net: float
    price_with_vat: float
    supplier_utility_pct: float
    price_pack_with_utility: float
    units_per_package: int
    price_unit_with_utility: float
    vat_rate_detected: float | None = None
    price_anomaly: bool = False
    prev_price_with_vat: float | None = None
    prev_price_unit_with_utility: float | None = None
    last_change_type: str | None = None
    last_change_pct: float | None = None
    in_latest_list: bool = True
    last_verified_at: datetime
    last_price_changed_at: datetime | None = None
    discontinued_at: datetime | None = None
    linked_product_id: str | None = None
    image_source_url: str | None = None


class LinkedProductSummary(BaseModel):
    id: str
    sku: str
    name: str
    unit_price: float
    stock: int
    min_stock: int


class PriceChangeEventItem(BaseModel):
    id: str
    import_id: str
    import_date: str
    supplier: str
    code: str
    description_snapshot: str
    packaging_snapshot: str
    change_type: ChangeTypeVisible
    is_reactivation: bool = False
    old_price_net: float | None = None
    new_price_net: float | None = None
    old_price_with_vat: float | None = None
    new_price_with_vat: float | None = None
    old_price_unit: float | None = None
    new_price_unit: float | None = None
    old_units_per_package: int | None = None
    new_units_per_package: int | None = None
    diff_amount: float | None = None
    diff_pct: float | None = None
    in_my_stock: bool = False
    my_sale_price: float | None = None
    changes_count: int = 1
    created_at: datetime


class CatalogItemDetailResponse(CatalogItemListItem):
    first_seen_at: datetime
    linked_product: LinkedProductSummary | None = None
    recent_changes: list[PriceChangeEventItem] = Field(default_factory=list)


class PackagingCountItem(BaseModel):
    packaging: str
    count: int


class CatalogFiltersResponse(BaseModel):
    packagings: list[PackagingCountItem]
    active_count: int
    discontinued_count: int
    discontinued_alert: bool
    discontinued_threshold: int = 100
    in_my_stock_count: int


class PurgeDiscontinuedResponse(BaseModel):
    deleted_count: int
    preserved_linked_count: int
    remaining_discontinued_count: int


class RollbackImportResponse(BaseModel):
    import_id: str
    restored_updated_count: int
    deleted_new_count: int
    preserved_linked_new_count: int
    reverted_verified_count: int
    previous_import_id: str | None = None
    message: str


class LoadToStockItemInput(BaseModel):
    code: str = Field(..., min_length=1, max_length=24)
    initial_stock: int = Field(default=0, ge=0, le=1_000_000)
    min_stock: int = Field(default=0, ge=0, le=1_000_000)
    sale_price: float = Field(..., gt=0)
    category: str = Field(default="Librería", min_length=1, max_length=100)
    barcode: str | None = Field(default=None, max_length=64)


class LoadToStockRequest(BaseModel):
    items: list[LoadToStockItemInput] = Field(..., min_length=1, max_length=100)


class LoadToStockSkippedItem(BaseModel):
    code: str
    reason: str


class LoadToStockResponse(BaseModel):
    created_count: int
    skipped_count: int
    created_product_ids: list[str]
    skipped: list[LoadToStockSkippedItem]


class PriceChangesSummaryResponse(BaseModel):
    price_up: int = 0
    price_down: int = 0
    new: int = 0
    discontinued: int = 0
    total: int = 0
    in_my_stock_changed: int = 0
    period_label: str = ""
