from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ProductSupplierRef(BaseModel):
    supplier: str
    code: str


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="Librería", min_length=1, max_length=100)
    unit_price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    min_stock: int = Field(default=0, ge=0, le=1_000_000)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    unit_price: float | None = Field(default=None, gt=0)
    min_stock: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


StockStatusTag = Literal["ok", "low_stock", "out_of_stock"]


class SupplierCostSummary(BaseModel):
    supplier: str
    code: str
    price_net: float
    price_with_vat: float
    units_per_package: int
    price_unit_with_utility: float
    in_latest_list: bool
    last_verified_at: datetime
    last_price_changed_at: datetime | None = None


class ProductResponse(BaseModel):
    id: str
    sku: str
    barcode: str | None = None
    name: str
    description: str
    category: str
    unit_price: float
    stock: int
    min_stock: int
    stock_status: StockStatusTag
    is_active: bool
    supplier_ref: ProductSupplierRef | None = None
    supplier_cost: SupplierCostSummary | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CategoryCountItem(BaseModel):
    category: str
    count: int


class InventorySummaryResponse(BaseModel):
    active_count: int = 0
    inactive_count: int = 0
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    linked_to_supplier_count: int = 0
    categories: list[CategoryCountItem] = Field(default_factory=list)


StockMovementType = Literal["in", "out", "adjustment"]
StockMovementReason = Literal[
    "initial_stock",
    "restock",
    "manual_adjustment",
    "damaged",
    "return",
    "sale",
]


class StockAdjustRequest(BaseModel):
    type: StockMovementType
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    new_stock: int | None = Field(default=None, ge=0, le=1_000_000)
    reason: StockMovementReason = "manual_adjustment"
    notes: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_adjustment_mode(self) -> "StockAdjustRequest":
        if self.type in ("in", "out"):
            if self.quantity is None or self.quantity < 1:
                raise ValueError("Para ingresos ('in') o egresos ('out') debés indicar 'quantity' >= 1.")
        elif self.type == "adjustment":
            if self.new_stock is None and self.quantity is None:
                raise ValueError(
                    "Para un ajuste ('adjustment') debés indicar el conteo físico final en 'new_stock'."
                )
        return self


class StockMovementResponse(BaseModel):
    id: str
    product_id: str
    product_sku: str | None = None
    product_name: str | None = None
    type: StockMovementType
    quantity_delta: int
    previous_stock: int
    new_stock: int
    reference_id: str | None = None
    user_id: str
    user_email: str | None = None
    reason: str
    notes: str | None = None
    created_at: datetime


class ProductDetailResponse(ProductResponse):
    recent_movements: list[StockMovementResponse] = Field(default_factory=list)
