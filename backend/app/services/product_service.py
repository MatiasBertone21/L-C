from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo
from bson import ObjectId

from app.core.bson_utils import DEC2, parse_object_id, to_dec128, to_money_float
from app.core.clock import now_utc
from app.core.config import settings
from app.core.exceptions import DomainValidationError, NotFoundError
from app.repositories.product_repository import ProductRepository, build_product_search_text
from app.repositories.supplier_catalog_repository import (
    SupplierCatalogRepository,
    compute_total_pages,
)
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.product import (
    CategoryCountItem,
    InventorySummaryResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductResponse,
    ProductSupplierRef,
    ProductUpdate,
    StockAdjustRequest,
    StockMovementResponse,
    StockStatusTag,
    SupplierCostSummary,
)
from app.schemas.user import UserResponse


class ProductService:
    def __init__(
        self,
        product_repo: ProductRepository,
        catalog_repo: SupplierCatalogRepository,
        user_repo: UserRepository,
    ) -> None:
        self.repo = product_repo
        self.catalog_repo = catalog_repo
        self.user_repo = user_repo

    @staticmethod
    def _compute_stock_status(stock: int, min_stock: int) -> StockStatusTag:
        if stock <= 0:
            return "out_of_stock"
        if stock <= min_stock:
            return "low_stock"
        return "ok"

    @staticmethod
    def _serialize_supplier_cost(cat_doc: dict[str, Any] | None) -> SupplierCostSummary | None:
        if cat_doc is None:
            return None
        return SupplierCostSummary(
            supplier=cat_doc["supplier"],
            code=cat_doc["code"],
            price_net=to_money_float(cat_doc.get("price_net"), 2) or 0.0,
            price_with_vat=to_money_float(cat_doc.get("price_with_vat"), 2) or 0.0,
            units_per_package=int(cat_doc.get("units_per_package", 1)),
            price_unit_with_utility=to_money_float(cat_doc.get("price_unit_with_utility"), 2) or 0.0,
            in_latest_list=bool(cat_doc.get("in_latest_list", True)),
            last_verified_at=cat_doc["last_verified_at"],
            last_price_changed_at=cat_doc.get("last_price_changed_at"),
        )

    def _serialize_product(
        self,
        doc: dict[str, Any],
        supplier_cost_doc: dict[str, Any] | None = None,
    ) -> ProductResponse:
        stock = int(doc.get("stock", 0))
        min_stock = int(doc.get("min_stock", 0))
        sup_ref_raw = doc.get("supplier_ref")
        sup_ref = (
            ProductSupplierRef(supplier=sup_ref_raw["supplier"], code=sup_ref_raw["code"])
            if sup_ref_raw and sup_ref_raw.get("code")
            else None
        )
        return ProductResponse(
            id=str(doc["_id"]),
            sku=doc["sku"],
            barcode=doc.get("barcode"),
            name=doc["name"],
            description=doc.get("description", ""),
            category=doc.get("category", "Librería"),
            unit_price=to_money_float(doc.get("unit_price"), 2) or 0.0,
            stock=stock,
            min_stock=min_stock,
            stock_status=self._compute_stock_status(stock, min_stock),
            is_active=bool(doc.get("is_active", True)),
            supplier_ref=sup_ref,
            supplier_cost=self._serialize_supplier_cost(supplier_cost_doc),
            metadata=doc.get("metadata") or {},
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _serialize_movement(
        mov: dict[str, Any],
        *,
        product_doc: dict[str, Any] | None = None,
        user_email: str | None = None,
    ) -> StockMovementResponse:
        return StockMovementResponse(
            id=str(mov["_id"]),
            product_id=str(mov["product_id"]),
            product_sku=product_doc.get("sku") if product_doc else None,
            product_name=product_doc.get("name") if product_doc else None,
            type=mov["type"],
            quantity_delta=int(mov["quantity_delta"]),
            previous_stock=int(mov["previous_stock"]),
            new_stock=int(mov["new_stock"]),
            reference_id=str(mov["reference_id"]) if mov.get("reference_id") else None,
            user_id=str(mov["user_id"]),
            user_email=user_email,
            reason=mov.get("reason", "manual_adjustment"),
            notes=mov.get("notes"),
            created_at=mov["created_at"],
        )

    async def _fetch_supplier_costs_for_products(
        self,
        product_docs: list[dict[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        by_supplier: dict[str, list[str]] = {}
        for doc in product_docs:
            ref = doc.get("supplier_ref")
            if ref and ref.get("supplier") and ref.get("code"):
                by_supplier.setdefault(ref["supplier"], []).append(ref["code"])

        result: dict[tuple[str, str], dict[str, Any]] = {}
        for sup, codes in by_supplier.items():
            items_map = await self.catalog_repo.find_items_by_codes(sup, list(set(codes)))
            for code, cat_doc in items_map.items():
                result[(sup, code)] = cat_doc
        return result

    async def list_products(
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
    ) -> PaginatedResponse[ProductResponse]:
        docs, total = await self.repo.list_products_paginated(
            q=q,
            category=category,
            is_active=is_active,
            stock_alert=stock_alert,
            has_supplier=has_supplier,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        costs_map = await self._fetch_supplier_costs_for_products(docs)
        items: list[ProductResponse] = []
        for doc in docs:
            ref = doc.get("supplier_ref") or {}
            cost_doc = costs_map.get((ref.get("supplier", ""), ref.get("code", "")))
            items.append(self._serialize_product(doc, supplier_cost_doc=cost_doc))

        return PaginatedResponse[ProductResponse](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=compute_total_pages(total, page_size),
        )

    async def get_inventory_summary(self) -> InventorySummaryResponse:
        raw = await self.repo.get_inventory_summary()
        return InventorySummaryResponse(
            active_count=raw["active_count"],
            inactive_count=raw["inactive_count"],
            low_stock_count=raw["low_stock_count"],
            out_of_stock_count=raw["out_of_stock_count"],
            linked_to_supplier_count=raw["linked_to_supplier_count"],
            categories=[CategoryCountItem(**c) for c in raw["categories"]],
        )

    async def lookup_by_code(self, code: str) -> ProductResponse:
        doc = await self.repo.find_active_by_barcode_or_sku(code)
        if doc is None:
            raise NotFoundError(f"No se encontró ningún producto activo con código '{code}'.")
        costs_map = await self._fetch_supplier_costs_for_products([doc])
        ref = doc.get("supplier_ref") or {}
        cost_doc = costs_map.get((ref.get("supplier", ""), ref.get("code", "")))
        return self._serialize_product(doc, supplier_cost_doc=cost_doc)

    async def get_product_detail(self, product_id_str: str) -> ProductDetailResponse:
        prod_oid = parse_object_id(product_id_str, "ID de producto")
        doc = await self.repo.get_by_id(prod_oid)
        if doc is None:
            raise NotFoundError("Producto no encontrado.")

        costs_map = await self._fetch_supplier_costs_for_products([doc])
        ref = doc.get("supplier_ref") or {}
        cost_doc = costs_map.get((ref.get("supplier", ""), ref.get("code", "")))
        base = self._serialize_product(doc, supplier_cost_doc=cost_doc)

        mov_docs = await self.repo.list_movements_for_product(prod_oid, limit=15)
        user_ids = list({m["user_id"] for m in mov_docs if isinstance(m.get("user_id"), ObjectId)})
        emails_map = await self.user_repo.find_emails_by_ids(user_ids)

        recent_movements = [
            self._serialize_movement(
                m,
                product_doc=doc,
                user_email=emails_map.get(m.get("user_id")),
            )
            for m in mov_docs
        ]

        return ProductDetailResponse(**base.model_dump(), recent_movements=recent_movements)

    async def create_product(self, payload: ProductCreate, current_user: UserResponse) -> ProductResponse:
        now = now_utc()
        user_oid = parse_object_id(current_user.id, "ID de usuario")
        prod_id = await self.repo.create_product_with_initial_movement(
            sku=payload.sku,
            barcode=payload.barcode,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            unit_price=Decimal(str(payload.unit_price)),
            initial_stock=payload.stock,
            min_stock=payload.min_stock,
            supplier_ref=None,
            metadata=payload.metadata,
            user_id=user_oid,
            reference_id=None,
            now=now,
            is_active=payload.is_active,
        )
        created = await self.repo.get_by_id(prod_id)
        assert created is not None
        return self._serialize_product(created)

    async def update_product(self, product_id_str: str, payload: ProductUpdate) -> ProductResponse:
        prod_oid = parse_object_id(product_id_str, "ID de producto")
        existing = await self.repo.get_by_id(prod_oid)
        if existing is None:
            raise NotFoundError("Producto no encontrado.")

        provided = payload.model_dump(exclude_unset=True)
        if not provided:
            return self._serialize_product(existing)

        now = now_utc()
        set_fields: dict[str, Any] = {"updated_at": now}
        unset_fields: list[str] = []

        next_sku = existing["sku"]
        next_name = existing["name"]
        next_barcode: str | None = existing.get("barcode")
        next_cat = existing.get("category", "Librería")

        if "sku" in provided and provided["sku"] is not None:
            next_sku = provided["sku"].strip()
            set_fields["sku"] = next_sku

        if "barcode" in provided:
            raw_bc = provided["barcode"]
            if raw_bc is None or not raw_bc.strip():
                next_barcode = None
                unset_fields.append("barcode")
            else:
                next_barcode = raw_bc.strip()
                set_fields["barcode"] = next_barcode

        if "name" in provided and provided["name"] is not None:
            next_name = provided["name"].strip()
            set_fields["name"] = next_name

        if "description" in provided and provided["description"] is not None:
            set_fields["description"] = provided["description"].strip()

        if "category" in provided and provided["category"] is not None:
            next_cat = provided["category"].strip() or "Librería"
            set_fields["category"] = next_cat

        if "unit_price" in provided and provided["unit_price"] is not None:
            set_fields["unit_price"] = to_dec128(Decimal(str(provided["unit_price"])), DEC2)

        if "min_stock" in provided and provided["min_stock"] is not None:
            set_fields["min_stock"] = int(provided["min_stock"])

        if "is_active" in provided and provided["is_active"] is not None:
            set_fields["is_active"] = bool(provided["is_active"])

        if "metadata" in provided and provided["metadata"] is not None:
            set_fields["metadata"] = provided["metadata"]

        set_fields["search_text"] = build_product_search_text(
            next_sku, next_name, next_barcode, next_cat
        )

        updated = await self.repo.update_product_fields(
            prod_oid,
            set_fields=set_fields,
            unset_fields=unset_fields or None,
        )
        if updated is None:
            raise NotFoundError("Producto no encontrado.")

        costs_map = await self._fetch_supplier_costs_for_products([updated])
        ref = updated.get("supplier_ref") or {}
        cost_doc = costs_map.get((ref.get("supplier", ""), ref.get("code", "")))
        return self._serialize_product(updated, supplier_cost_doc=cost_doc)

    async def soft_delete_product(self, product_id_str: str) -> None:
        prod_oid = parse_object_id(product_id_str, "ID de producto")
        updated = await self.repo.update_product_fields(
            prod_oid,
            set_fields={"is_active": False, "updated_at": now_utc()},
        )
        if updated is None:
            raise NotFoundError("Producto no encontrado.")

    async def adjust_product_stock(
        self,
        product_id_str: str,
        payload: StockAdjustRequest,
        current_user: UserResponse,
    ) -> ProductDetailResponse:
        prod_oid = parse_object_id(product_id_str, "ID de producto")
        user_oid = parse_object_id(current_user.id, "ID de usuario")
        now = now_utc()

        await self.repo.adjust_stock_atomically(
            product_id=prod_oid,
            mov_type=payload.type,
            quantity=payload.quantity,
            target_new_stock=payload.new_stock,
            reason=payload.reason,
            notes=payload.notes,
            user_id=user_oid,
            reference_id=None,
            now=now,
        )
        return await self.get_product_detail(product_id_str)

    async def list_stock_movements(
        self,
        *,
        product_id: str | None,
        mov_type: str | None,
        reason: str | None,
        q: str | None,
        date_from: str | None,
        date_to: str | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[StockMovementResponse]:
        if date_from and date_to and date_from > date_to:
            raise DomainValidationError("La fecha inicial no puede ser posterior a la fecha final.")

        product_ids_filter: list[ObjectId] | None = None
        if product_id:
            product_ids_filter = [parse_object_id(product_id, "ID de producto")]
        elif q and q.strip():
            matched_ids = await self.repo.find_matching_product_ids(q)
            if not matched_ids:
                return PaginatedResponse[StockMovementResponse](
                    items=[], total=0, page=page, page_size=page_size, total_pages=0
                )
            product_ids_filter = matched_ids

        tz = ZoneInfo(settings.business_timezone)
        created_from: datetime | None = None
        created_to: datetime | None = None
        if date_from:
            dt_local = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz)
            created_from = dt_local.astimezone(timezone.utc)
        if date_to:
            dt_local_end = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=tz)
            created_to = dt_local_end.astimezone(timezone.utc)

        mov_docs, total = await self.repo.list_movements_paginated(
            product_ids=product_ids_filter,
            mov_type=mov_type,
            reason=reason,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )

        unique_prod_ids = list({m["product_id"] for m in mov_docs if isinstance(m.get("product_id"), ObjectId)})
        unique_user_ids = list({m["user_id"] for m in mov_docs if isinstance(m.get("user_id"), ObjectId)})

        products_map = await self.repo.find_by_ids(unique_prod_ids)
        emails_map = await self.user_repo.find_emails_by_ids(unique_user_ids)

        items = [
            self._serialize_movement(
                m,
                product_doc=products_map.get(m.get("product_id")),
                user_email=emails_map.get(m.get("user_id")),
            )
            for m in mov_docs
        ]

        return PaginatedResponse[StockMovementResponse](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=compute_total_pages(total, page_size),
        )
