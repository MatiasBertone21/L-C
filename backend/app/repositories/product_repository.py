from datetime import datetime
from decimal import Decimal
from typing import Any
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

from app.core.bson_utils import DEC2, to_dec128, to_money_float


class ProductRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.products = db["products"]
        self.movements = db["stock_movements"]

    async def ensure_indexes(self) -> None:
        await self.products.create_indexes(
            [
                IndexModel([("sku", ASCENDING)], unique=True, name="uq_product_sku"),
                IndexModel(
                    [("barcode", ASCENDING)],
                    unique=True,
                    sparse=True,
                    name="uq_product_barcode_sparse",
                ),
                IndexModel(
                    [("supplier_ref.supplier", ASCENDING), ("supplier_ref.code", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"supplier_ref.code": {"$exists": True}},
                    name="uq_product_supplier_ref",
                ),
                IndexModel([("is_active", ASCENDING), ("category", ASCENDING)], name="ix_product_active_category"),
            ]
        )
        await self.movements.create_indexes(
            [
                IndexModel([("product_id", ASCENDING), ("created_at", DESCENDING)], name="ix_mov_product_date"),
                IndexModel([("created_at", DESCENDING)], name="ix_mov_created_at"),
                IndexModel([("type", ASCENDING), ("created_at", DESCENDING)], name="ix_mov_type_date"),
            ]
        )

    async def find_by_supplier_codes(self, supplier: str, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        cursor = self.products.find(
            {"supplier_ref.supplier": supplier, "supplier_ref.code": {"$in": codes}},
            {"sku": 1, "name": 1, "unit_price": 1, "stock": 1, "min_stock": 1, "supplier_ref": 1},
        )
        out: dict[str, dict[str, Any]] = {}
        async for doc in cursor:
            ref = doc.get("supplier_ref") or {}
            code = ref.get("code")
            if code:
                out[code] = doc
        return out

    async def find_by_ids(self, ids: list[ObjectId]) -> dict[ObjectId, dict[str, Any]]:
        if not ids:
            return {}
        cursor = self.products.find(
            {"_id": {"$in": ids}},
            {"sku": 1, "name": 1, "unit_price": 1, "stock": 1, "min_stock": 1, "supplier_ref": 1},
        )
        return {doc["_id"]: doc async for doc in cursor}

    async def get_by_id(self, product_id: ObjectId) -> dict[str, Any] | None:
        return await self.products.find_one({"_id": product_id})

    async def sku_exists(self, sku: str) -> bool:
        doc = await self.products.find_one({"sku": sku}, {"_id": 1})
        return doc is not None

    async def create_product_with_initial_movement(
        self,
        *,
        sku: str,
        barcode: str | None,
        name: str,
        description: str,
        category: str,
        unit_price: Decimal,
        initial_stock: int,
        min_stock: int,
        supplier_ref: dict[str, str] | None,
        metadata: dict[str, Any],
        user_id: ObjectId,
        reference_id: ObjectId | None,
        now: datetime,
    ) -> ObjectId:
        doc: dict[str, Any] = {
            "sku": sku,
            "name": name,
            "description": description,
            "category": category,
            "unit_price": to_dec128(unit_price, DEC2),
            "stock": initial_stock,
            "min_stock": min_stock,
            "is_active": True,
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }
        if barcode:
            doc["barcode"] = barcode
        if supplier_ref:
            doc["supplier_ref"] = supplier_ref

        res = await self.products.insert_one(doc)
        product_id = res.inserted_id

        if initial_stock > 0:
            await self.movements.insert_one(
                {
                    "product_id": product_id,
                    "type": "in",
                    "quantity_delta": initial_stock,
                    "previous_stock": 0,
                    "new_stock": initial_stock,
                    "reference_id": reference_id,
                    "user_id": user_id,
                    "reason": "initial_stock",
                    "created_at": now,
                }
            )

        return product_id

    @staticmethod
    def to_summary_dict(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "sku": doc["sku"],
            "name": doc["name"],
            "unit_price": to_money_float(doc.get("unit_price"), 2) or 0.0,
            "stock": int(doc.get("stock", 0)),
            "min_stock": int(doc.get("min_stock", 0)),
        }
