from datetime import datetime, timedelta
import math
import re
from typing import Any
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import DuplicateResourceError
from app.services.supplier_parsing import strip_accents

BULK_BATCH_SIZE = 1000
CODE_IN_BATCH_SIZE = 2000


class SupplierCatalogRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.imports = db["supplier_imports"]
        self.items = db["supplier_catalog_items"]
        self.history = db["price_change_history"]
        self.locks = db["supplier_import_locks"]

    async def ensure_indexes(self) -> None:
        await self.locks.create_indexes(
            [
                IndexModel(
                    [("expires_at", ASCENDING)],
                    expireAfterSeconds=0,
                    name="ttl_import_lock_expires",
                )
            ]
        )
        await self.imports.create_indexes(
            [
                IndexModel(
                    [("same_day_dedupe_key", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"same_day_dedupe_key": {"$exists": True}},
                    name="uq_import_same_day_dedupe",
                ),
                IndexModel(
                    [("supplier", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
                    name="ix_import_supplier_status_created",
                ),
                IndexModel(
                    [("supplier", ASCENDING), ("import_date", DESCENDING), ("created_at", DESCENDING)],
                    name="ix_import_supplier_date_created",
                ),
            ]
        )
        await self.items.create_indexes(
            [
                IndexModel([("supplier", ASCENDING), ("code", ASCENDING)], unique=True, name="uq_catalog_supplier_code"),
                IndexModel(
                    [("supplier", ASCENDING), ("in_latest_list", ASCENDING), ("description_clean", ASCENDING)],
                    name="ix_catalog_active_desc",
                ),
                IndexModel(
                    [("supplier", ASCENDING), ("last_price_changed_at", DESCENDING)],
                    name="ix_catalog_last_changed",
                ),
                IndexModel([("supplier", ASCENDING), ("packaging", ASCENDING)], name="ix_catalog_packaging"),
                IndexModel([("supplier", ASCENDING), ("is_liquidation", ASCENDING)], name="ix_catalog_liquidation"),
                IndexModel([("supplier", ASCENDING), ("linked_product_id", ASCENDING)], name="ix_catalog_linked_product"),
                IndexModel([("supplier", ASCENDING), ("last_import_id", ASCENDING)], name="ix_catalog_last_import"),
            ]
        )
        await self.history.create_indexes(
            [
                IndexModel(
                    [("import_id", ASCENDING), ("visible_in_diff", ASCENDING), ("abs_diff_pct", DESCENDING)],
                    name="ix_hist_import_visible_impact",
                ),
                IndexModel(
                    [
                        ("supplier", ASCENDING),
                        ("visible_in_diff", ASCENDING),
                        ("import_date", DESCENDING),
                        ("abs_diff_pct", DESCENDING),
                    ],
                    name="ix_hist_supplier_date_impact",
                ),
                IndexModel(
                    [("supplier", ASCENDING), ("code", ASCENDING), ("visible_in_diff", ASCENDING), ("created_at", DESCENDING)],
                    name="ix_hist_supplier_code_date",
                ),
            ]
        )

    # --- Locks ---
    async def acquire_lock(self, supplier: str, operation: str, user_id: str, now: datetime, ttl_seconds: int = 600) -> None:
        try:
            await self.locks.insert_one(
                {
                    "_id": supplier,
                    "operation": operation,
                    "user_id": user_id,
                    "acquired_at": now,
                    "expires_at": now + timedelta(seconds=ttl_seconds),
                }
            )
        except DuplicateKeyError as exc:
            raise DuplicateResourceError(
                "Hay otra operación de actualización o reversión de catálogo en curso. Aguardá unos segundos."
            ) from exc

    async def release_lock(self, supplier: str) -> None:
        await self.locks.delete_one({"_id": supplier})

    # --- Imports ---
    async def find_same_day_duplicate(self, dedupe_key: str) -> dict[str, Any] | None:
        return await self.imports.find_one({"same_day_dedupe_key": dedupe_key, "status": "completed"})

    async def find_same_day_by_content_hash(self, supplier: str, import_date: str, content_hash: str) -> dict[str, Any] | None:
        return await self.imports.find_one(
            {
                "supplier": supplier,
                "import_date": import_date,
                "content_hash": content_hash,
                "status": "completed",
            }
        )

    async def count_completed_in_day(self, supplier: str, import_date: str) -> int:
        return await self.imports.count_documents(
            {"supplier": supplier, "import_date": import_date, "status": "completed"}
        )

    async def get_latest_completed_import(self, supplier: str) -> dict[str, Any] | None:
        return await self.imports.find_one(
            {"supplier": supplier, "status": "completed"},
            sort=[("created_at", DESCENDING), ("_id", DESCENDING)],
        )

    async def get_previous_completed_import(self, supplier: str, exclude_id: ObjectId) -> dict[str, Any] | None:
        return await self.imports.find_one(
            {"supplier": supplier, "status": "completed", "_id": {"$ne": exclude_id}},
            sort=[("created_at", DESCENDING), ("_id", DESCENDING)],
        )

    async def find_stale_processing_imports(self, supplier: str | None = None) -> list[dict[str, Any]]:
        filt: dict[str, Any] = {"status": "processing"}
        if supplier:
            filt["supplier"] = supplier
        cursor = self.imports.find(filt, sort=[("created_at", DESCENDING)])
        return [doc async for doc in cursor]

    async def get_import_by_id(self, import_id: ObjectId) -> dict[str, Any] | None:
        return await self.imports.find_one({"_id": import_id})

    async def insert_import(self, doc: dict[str, Any]) -> ObjectId:
        res = await self.imports.insert_one(doc)
        return res.inserted_id

    async def update_import(self, import_id: ObjectId, set_fields: dict[str, Any], unset_fields: list[str] | None = None) -> None:
        upd: dict[str, Any] = {"$set": set_fields}
        if unset_fields:
            upd["$unset"] = {k: "" for k in unset_fields}
        await self.imports.update_one({"_id": import_id}, upd)

    async def delete_import_doc(self, import_id: ObjectId) -> None:
        await self.imports.delete_one({"_id": import_id})

    async def list_imports_paginated(
        self,
        *,
        supplier: str,
        page: int,
        page_size: int,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        filt: dict[str, Any] = {"supplier": supplier}
        if status:
            filt["status"] = status
        if date_from or date_to:
            date_filter: dict[str, Any] = {}
            if date_from:
                date_filter["$gte"] = date_from
            if date_to:
                date_filter["$lte"] = date_to
            filt["import_date"] = date_filter

        total = await self.imports.count_documents(filt)
        cursor = (
            self.imports.find(filt, {"warnings": 0})
            .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [doc async for doc in cursor], total

    # --- Catalog Bulk & Queries ---
    async def fetch_all_catalog_map(self, supplier: str) -> dict[str, dict[str, Any]]:
        cursor = self.items.find({"supplier": supplier})
        return {doc["code"]: doc async for doc in cursor}

    async def bulk_write_catalog(self, operations: list[Any]) -> None:
        for i in range(0, len(operations), BULK_BATCH_SIZE):
            batch = operations[i : i + BULK_BATCH_SIZE]
            if batch:
                await self.items.bulk_write(batch, ordered=False)

    async def bulk_insert_history(self, history_docs: list[dict[str, Any]]) -> None:
        for i in range(0, len(history_docs), BULK_BATCH_SIZE):
            batch = history_docs[i : i + BULK_BATCH_SIZE]
            if batch:
                await self.history.insert_many(batch, ordered=False)

    async def mark_unchanged_codes_verified(
        self,
        *,
        supplier: str,
        codes: list[str],
        import_id: ObjectId,
        verified_at: datetime,
    ) -> int:
        modified = 0
        for i in range(0, len(codes), CODE_IN_BATCH_SIZE):
            chunk = codes[i : i + CODE_IN_BATCH_SIZE]
            res = await self.items.update_many(
                {"supplier": supplier, "code": {"$in": chunk}},
                {
                    "$set": {
                        "last_verified_at": verified_at,
                        "last_import_id": import_id,
                        "in_latest_list": True,
                        "updated_at": verified_at,
                    }
                },
            )
            modified += res.modified_count
        return modified

    async def quick_validate_all_active(
        self,
        *,
        supplier: str,
        new_import_id: ObjectId,
        verified_at: datetime,
    ) -> int:
        res = await self.items.update_many(
            {"supplier": supplier, "in_latest_list": True},
            {
                "$set": {
                    "last_verified_at": verified_at,
                    "last_import_id": new_import_id,
                    "updated_at": verified_at,
                }
            },
        )
        return res.modified_count

    async def revert_verified_items_for_import(
        self,
        *,
        supplier: str,
        import_id: ObjectId,
        previous_import_id: ObjectId | None,
        previous_verified_at: datetime | None,
        now: datetime,
    ) -> int:
        if previous_import_id is None or previous_verified_at is None:
            return 0
        res = await self.items.update_many(
            {"supplier": supplier, "last_import_id": import_id},
            {
                "$set": {
                    "last_import_id": previous_import_id,
                    "last_verified_at": previous_verified_at,
                    "updated_at": now,
                }
            },
        )
        return res.modified_count

    async def get_history_for_import(self, import_id: ObjectId) -> list[dict[str, Any]]:
        cursor = self.history.find({"import_id": import_id})
        return [doc async for doc in cursor]

    async def delete_history_for_import(self, import_id: ObjectId) -> int:
        res = await self.history.delete_many({"import_id": import_id})
        return res.deleted_count

    async def get_catalog_counts(self, supplier: str) -> tuple[int, int, int]:
        active = await self.items.count_documents({"supplier": supplier, "in_latest_list": True})
        discontinued = await self.items.count_documents({"supplier": supplier, "in_latest_list": False})
        linked = await self.items.count_documents({"supplier": supplier, "linked_product_id": {"$ne": None}})
        return active, discontinued, linked

    async def get_packaging_facets(self, supplier: str) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"supplier": supplier, "in_latest_list": True}},
            {"$group": {"_id": "$packaging", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
        ]
        cursor = await self.items.aggregate(pipeline)
        return [{"packaging": doc["_id"] or "SIN_DATO", "count": doc["count"]} async for doc in cursor]

    @staticmethod
    def _build_search_regex_conditions(q: str | None) -> list[dict[str, Any]]:
        if not q or not q.strip():
            return []
        norm = strip_accents(q.upper()).strip()
        tokens = [re.escape(tok) for tok in norm.split() if tok]
        return [{"search_text": {"$regex": tok}} for tok in tokens[:6]]

    async def list_catalog_items_paginated(
        self,
        *,
        supplier: str,
        q: str | None,
        packaging: str | None,
        is_liquidation: bool | None,
        stock_status: str,
        changed_since: datetime | None,
        status: str,
        price_anomaly: bool | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        filt: dict[str, Any] = {"supplier": supplier}

        if status == "active":
            filt["in_latest_list"] = True
        elif status == "discontinued":
            filt["in_latest_list"] = False

        if packaging:
            filt["packaging"] = packaging.upper().strip()
        if is_liquidation is not None:
            filt["is_liquidation"] = is_liquidation

        if stock_status == "in_stock":
            filt["linked_product_id"] = {"$ne": None}
        elif stock_status == "not_in_stock":
            filt["linked_product_id"] = None

        if changed_since is not None:
            filt["last_price_changed_at"] = {"$gte": changed_since}
        if price_anomaly is not None:
            filt["price_anomaly"] = price_anomaly

        regex_conds = self._build_search_regex_conditions(q)
        if regex_conds:
            filt["$and"] = regex_conds

        sort_map: dict[str, list[tuple[str, int]]] = {
            "description": [("description_clean", ASCENDING), ("code", ASCENDING)],
            "code": [("code", ASCENDING)],
            "-last_price_changed_at": [("last_price_changed_at", DESCENDING), ("code", ASCENDING)],
            "price_with_vat": [("price_with_vat", ASCENDING), ("code", ASCENDING)],
            "-price_with_vat": [("price_with_vat", DESCENDING), ("code", ASCENDING)],
        }
        sort_spec = sort_map.get(sort, sort_map["description"])

        total = await self.items.count_documents(filt)
        cursor = (
            self.items.find(filt, {"search_text": 0, "row_fingerprint": 0})
            .sort(sort_spec)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [doc async for doc in cursor], total

    async def get_item_by_code(self, supplier: str, code: str) -> dict[str, Any] | None:
        return await self.items.find_one({"supplier": supplier, "code": code})

    async def find_items_by_codes(self, supplier: str, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        cursor = self.items.find({"supplier": supplier, "code": {"$in": codes}})
        return {doc["code"]: doc async for doc in cursor}

    async def get_linked_codes_map(self, supplier: str) -> dict[str, ObjectId]:
        cursor = self.items.find(
            {"supplier": supplier, "linked_product_id": {"$ne": None}},
            {"code": 1, "linked_product_id": 1},
        )
        return {doc["code"]: doc["linked_product_id"] async for doc in cursor}

    async def purge_discontinued_unlinked(self, supplier: str) -> tuple[int, int, int]:
        preserved = await self.items.count_documents(
            {"supplier": supplier, "in_latest_list": False, "linked_product_id": {"$ne": None}}
        )
        res = await self.items.delete_many(
            {"supplier": supplier, "in_latest_list": False, "linked_product_id": None}
        )
        remaining = await self.items.count_documents({"supplier": supplier, "in_latest_list": False})
        return res.deleted_count, preserved, remaining

    async def get_recent_changes_for_code(self, supplier: str, code: str, limit: int = 20) -> list[dict[str, Any]]:
        cursor = (
            self.history.find(
                {"supplier": supplier, "code": code, "visible_in_diff": True},
                {"before_snapshot": 0},
            )
            .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
            .limit(limit)
        )
        return [doc async for doc in cursor]

    # --- Price Changes (Diff) ---
    def build_price_changes_filter(
        self,
        *,
        supplier: str,
        import_id: ObjectId | None,
        date_from: str | None,
        date_to: str | None,
        change_types: list[str] | None,
        min_pct: float | None,
        allowed_codes: list[str] | None,
        q: str | None,
    ) -> dict[str, Any]:
        filt: dict[str, Any] = {"supplier": supplier, "visible_in_diff": True}
        if import_id is not None:
            filt["import_id"] = import_id
        elif date_from or date_to:
            df: dict[str, Any] = {}
            if date_from:
                df["$gte"] = date_from
            if date_to:
                df["$lte"] = date_to
            filt["import_date"] = df

        if change_types:
            filt["change_type"] = {"$in": change_types}

        if min_pct is not None and min_pct > 0:
            filt["abs_diff_pct"] = {"$gte": min_pct}

        if allowed_codes is not None:
            filt["code"] = {"$in": allowed_codes}

        if q and q.strip():
            escaped = re.escape(q.strip())
            filt["$or"] = [
                {"code": {"$regex": escaped, "$options": "i"}},
                {"description_snapshot": {"$regex": escaped, "$options": "i"}},
            ]

        return filt

    async def list_price_change_events_paginated(
        self,
        *,
        filt: dict[str, Any],
        sort: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        sort_map: dict[str, list[tuple[str, int]]] = {
            "-abs_diff_pct": [("abs_diff_pct", DESCENDING), ("created_at", DESCENDING)],
            "-diff_pct": [("diff_pct", DESCENDING), ("created_at", DESCENDING)],
            "diff_pct": [("diff_pct", ASCENDING), ("created_at", DESCENDING)],
            "-created_at": [("created_at", DESCENDING)],
            "code": [("code", ASCENDING)],
        }
        sort_spec = sort_map.get(sort, sort_map["-abs_diff_pct"])
        total = await self.history.count_documents(filt)
        cursor = (
            self.history.find(filt, {"before_snapshot": 0})
            .sort(sort_spec)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [doc async for doc in cursor], total

    async def summarize_price_changes(
        self,
        *,
        base_period_filter: dict[str, Any],
        linked_codes: list[str],
    ) -> dict[str, int]:
        pipeline = [
            {"$match": base_period_filter},
            {"$group": {"_id": "$change_type", "count": {"$sum": 1}}},
        ]
        cursor = await self.history.aggregate(pipeline)
        counts = {"price_up": 0, "price_down": 0, "new": 0, "discontinued": 0}
        async for row in cursor:
            ctype = row["_id"]
            if ctype in counts:
                counts[ctype] = int(row["count"])

        in_my_stock_changed = 0
        if linked_codes:
            stock_filter = dict(base_period_filter)
            stock_filter["code"] = {"$in": linked_codes}
            in_my_stock_changed = await self.history.count_documents(stock_filter)

        counts["total"] = sum(counts.values())
        counts["in_my_stock_changed"] = in_my_stock_changed
        return counts


def compute_total_pages(total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    return math.ceil(total / page_size)
