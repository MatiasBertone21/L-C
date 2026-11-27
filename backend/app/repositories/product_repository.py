from datetime import datetime
from decimal import Decimal
import re
from typing import Any
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.bson_utils import DEC2, to_dec128, to_money_float
from app.core.exceptions import DuplicateResourceError, InsufficientStockError, NotFoundError
from app.services.supplier_parsing import strip_accents


def build_product_search_text(
    sku: str,
    name: str,
    barcode: str | None = None,
    category: str | None = None,
) -> str:
    parts = [sku, barcode or "", name, category or ""]
    joined = " ".join(p for p in parts if p)
    return re.sub(r"\s+", " ", strip_accents(joined).upper()).strip()


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
                IndexModel(
                    [("is_active", ASCENDING), ("category", ASCENDING), ("name", ASCENDING)],
                    name="ix_product_active_category_name",
                ),
                IndexModel([("is_active", ASCENDING), ("stock", ASCENDING)], name="ix_product_active_stock"),
            ]
        )
        await self.movements.create_indexes(
            [
                IndexModel([("product_id", ASCENDING), ("created_at", DESCENDING)], name="ix_mov_product_date"),
                IndexModel([("created_at", DESCENDING)], name="ix_mov_created_at"),
                IndexModel([("type", ASCENDING), ("created_at", DESCENDING)], name="ix_mov_type_date"),
            ]
        )

    @staticmethod
    def _translate_duplicate_key(exc: DuplicateKeyError) -> DuplicateResourceError:
        msg = str(exc)
        if "barcode" in msg:
            return DuplicateResourceError("Ya existe otro producto registrado con ese código de barras.")
        if "supplier_ref" in msg:
            return DuplicateResourceError("Ese artículo del proveedor ya está vinculado a un producto de tu stock.")
        return DuplicateResourceError("Ya existe un producto registrado con ese código SKU.")

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

    async def find_active_by_barcode_or_sku(self, code: str) -> dict[str, Any] | None:
        cleaned = code.strip()
        if not cleaned:
            return None
        doc = await self.products.find_one({"barcode": cleaned, "is_active": True})
        if doc is not None:
            return doc
        return await self.products.find_one(
            {"sku": {"$regex": f"^{re.escape(cleaned)}$", "$options": "i"}, "is_active": True}
        )

    async def sku_exists(self, sku: str) -> bool:
        doc = await self.products.find_one({"sku": sku}, {"_id": 1})
        return doc is not None

    async def count_all(self) -> int:
        return await self.products.count_documents({})

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
        is_active: bool = True,
    ) -> ObjectId:
        clean_sku = sku.strip()
        clean_barcode = barcode.strip() if barcode and barcode.strip() else None
        clean_name = name.strip()
        clean_cat = category.strip() or "Librería"

        doc: dict[str, Any] = {
            "sku": clean_sku,
            "name": clean_name,
            "description": description.strip(),
            "category": clean_cat,
            "unit_price": to_dec128(unit_price, DEC2),
            "stock": initial_stock,
            "min_stock": min_stock,
            "is_active": is_active,
            "search_text": build_product_search_text(clean_sku, clean_name, clean_barcode, clean_cat),
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }
        if clean_barcode:
            doc["barcode"] = clean_barcode
        if supplier_ref:
            doc["supplier_ref"] = supplier_ref

        try:
            res = await self.products.insert_one(doc)
        except DuplicateKeyError as exc:
            raise self._translate_duplicate_key(exc) from exc

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
                    "notes": "Stock inicial de alta",
                    "created_at": now,
                }
            )

        return product_id

    async def update_product_fields(
        self,
        product_id: ObjectId,
        *,
        set_fields: dict[str, Any],
        unset_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        update_op: dict[str, Any] = {"$set": set_fields}
        if unset_fields:
            update_op["$unset"] = {k: "" for k in unset_fields}

        try:
            return await self.products.find_one_and_update(
                {"_id": product_id},
                update_op,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise self._translate_duplicate_key(exc) from exc

    async def adjust_stock_atomically(
        self,
        *,
        product_id: ObjectId,
        mov_type: str,
        quantity: int | None,
        target_new_stock: int | None,
        reason: str,
        notes: str | None,
        user_id: ObjectId,
        reference_id: ObjectId | None,
        now: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if mov_type == "in":
            assert quantity is not None and quantity >= 1
            updated = await self.products.find_one_and_update(
                {"_id": product_id},
                {"$inc": {"stock": quantity}, "$set": {"updated_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                raise NotFoundError("Producto no encontrado.")
            new_stock = int(updated["stock"])
            prev_stock = new_stock - quantity
            delta = quantity

        elif mov_type == "out":
            assert quantity is not None and quantity >= 1
            # Descuento condicional atómico: solo actualiza si stock >= quantity
            updated = await self.products.find_one_and_update(
                {"_id": product_id, "stock": {"$gte": quantity}},
                {"$inc": {"stock": -quantity}, "$set": {"updated_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                existing = await self.get_by_id(product_id)
                if existing is None:
                    raise NotFoundError("Producto no encontrado.")
                current_stock = int(existing.get("stock", 0))
                raise InsufficientStockError(
                    f"Stock insuficiente para '{existing['name']}': disponible {current_stock} u., "
                    f"intentaste descontar {quantity} u."
                )
            new_stock = int(updated["stock"])
            prev_stock = new_stock + quantity
            delta = -quantity

        else:
            # Conteo físico (adjustment): aplica optimísticamente sobre el stock leído para exactitud de auditoría
            for _attempt in range(3):
                existing = await self.get_by_id(product_id)
                if existing is None:
                    raise NotFoundError("Producto no encontrado.")
                prev_stock = int(existing.get("stock", 0))
                desired = target_new_stock if target_new_stock is not None else prev_stock
                delta = desired - prev_stock
                updated = await self.products.find_one_and_update(
                    {"_id": product_id, "stock": prev_stock},
                    {"$set": {"stock": desired, "updated_at": now}},
                    return_document=ReturnDocument.AFTER,
                )
                if updated is not None:
                    new_stock = desired
                    break
            else:
                raise InsufficientStockError(
                    "El stock del producto fue modificado simultáneamente por otra operación; reintentá el ajuste."
                )

        mov_doc: dict[str, Any] = {
            "product_id": product_id,
            "type": mov_type,
            "quantity_delta": delta,
            "previous_stock": prev_stock,
            "new_stock": new_stock,
            "reference_id": reference_id,
            "user_id": user_id,
            "reason": reason,
            "notes": notes.strip() if notes and notes.strip() else None,
            "created_at": now,
        }
        ins = await self.movements.insert_one(mov_doc)
        mov_doc["_id"] = ins.inserted_id
        return updated, mov_doc

    async def list_products_paginated(
        self,
        *,
        q: str | None,
        category: str | None,
        is_active: bool | None,
        stock_alert: str,
        has_supplier: bool | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[dict[str, Any]] = []

        if is_active is not None:
            conditions.append({"is_active": is_active})

        if category and category.strip():
            conditions.append({"category": category.strip()})

        if stock_alert == "out_of_stock":
            conditions.append({"stock": {"$lte": 0}})
        elif stock_alert == "low_stock":
            conditions.append({"$expr": {"$lte": ["$stock", "$min_stock"]}})

        if has_supplier is True:
            conditions.append({"supplier_ref.code": {"$exists": True}})
        elif has_supplier is False:
            conditions.append({"supplier_ref.code": {"$exists": False}})

        if q and q.strip():
            raw_q = q.strip()
            norm_tokens = [re.escape(t) for t in strip_accents(raw_q).upper().split() if t]
            if len(norm_tokens) == 1:
                tok = norm_tokens[0]
                escaped_raw = re.escape(raw_q)
                conditions.append(
                    {
                        "$or": [
                            {"search_text": {"$regex": tok}},
                            {"sku": {"$regex": escaped_raw, "$options": "i"}},
                            {"barcode": {"$regex": escaped_raw, "$options": "i"}},
                            {"name": {"$regex": escaped_raw, "$options": "i"}},
                        ]
                    }
                )
            else:
                for tok in norm_tokens[:6]:
                    conditions.append({"search_text": {"$regex": tok}})

        filt: dict[str, Any] = {"$and": conditions} if conditions else {}

        sort_map: dict[str, list[tuple[str, int]]] = {
            "name": [("name", ASCENDING), ("sku", ASCENDING)],
            "sku": [("sku", ASCENDING)],
            "stock": [("stock", ASCENDING), ("name", ASCENDING)],
            "-stock": [("stock", DESCENDING), ("name", ASCENDING)],
            "unit_price": [("unit_price", ASCENDING), ("name", ASCENDING)],
            "-unit_price": [("unit_price", DESCENDING), ("name", ASCENDING)],
            "-updated_at": [("updated_at", DESCENDING)],
        }
        sort_spec = sort_map.get(sort, sort_map["name"])

        total = await self.products.count_documents(filt)
        cursor = (
            self.products.find(filt, {"search_text": 0})
            .sort(sort_spec)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [doc async for doc in cursor], total

    async def get_inventory_summary(self) -> dict[str, Any]:
        active_count = await self.products.count_documents({"is_active": True})
        inactive_count = await self.products.count_documents({"is_active": False})
        out_of_stock_count = await self.products.count_documents({"is_active": True, "stock": {"$lte": 0}})
        low_stock_count = await self.products.count_documents(
            {"is_active": True, "$expr": {"$lte": ["$stock", "$min_stock"]}}
        )
        linked_count = await self.products.count_documents(
            {"is_active": True, "supplier_ref.code": {"$exists": True}}
        )

        cat_pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
        ]
        cat_cursor = await self.products.aggregate(cat_pipeline)
        categories = [{"category": row["_id"] or "General", "count": int(row["count"])} async for row in cat_cursor]

        return {
            "active_count": active_count,
            "inactive_count": inactive_count,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "linked_to_supplier_count": linked_count,
            "categories": categories,
        }

    async def list_movements_for_product(self, product_id: ObjectId, limit: int = 15) -> list[dict[str, Any]]:
        cursor = self.movements.find({"product_id": product_id}).sort([("created_at", DESCENDING)]).limit(limit)
        return [doc async for doc in cursor]

    async def find_matching_product_ids(self, q: str) -> list[ObjectId]:
        escaped = re.escape(q.strip())
        cursor = self.products.find(
            {
                "$or": [
                    {"sku": {"$regex": escaped, "$options": "i"}},
                    {"name": {"$regex": escaped, "$options": "i"}},
                    {"barcode": {"$regex": escaped, "$options": "i"}},
                ]
            },
            {"_id": 1},
        ).limit(200)
        return [doc["_id"] async for doc in cursor]

    async def list_movements_paginated(
        self,
        *,
        product_ids: list[ObjectId] | None,
        mov_type: str | None,
        reason: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        filt: dict[str, Any] = {}
        if product_ids is not None:
            filt["product_id"] = {"$in": product_ids}
        if mov_type:
            filt["type"] = mov_type
        if reason:
            filt["reason"] = reason
        if created_from or created_to:
            dt_cond: dict[str, Any] = {}
            if created_from:
                dt_cond["$gte"] = created_from
            if created_to:
                dt_cond["$lte"] = created_to
            filt["created_at"] = dt_cond

        total = await self.movements.count_documents(filt)
        cursor = (
            self.movements.find(filt)
            .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [doc async for doc in cursor], total

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
