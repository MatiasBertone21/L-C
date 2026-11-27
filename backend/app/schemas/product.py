from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class ProductSupplierRef(BaseModel):
    supplier: str
    code: str


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="General", max_length=100)
    unit_price: float = Field(..., ge=0)
    stock: int = Field(default=0, ge=0)
    min_stock: int = Field(default=0, ge=0)
    is_active: bool = True
    supplier_ref: ProductSupplierRef | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    is_active: bool
    supplier_ref: ProductSupplierRef | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


StockMovementType = Literal["in", "out", "adjustment"]


class StockMovementResponse(BaseModel):
    id: str
    product_id: str
    type: StockMovementType
    quantity_delta: int
    previous_stock: int
    new_stock: int
    reference_id: str | None = None
    user_id: str
    reason: str
    created_at: datetime
