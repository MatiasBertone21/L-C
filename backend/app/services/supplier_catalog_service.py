from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import logging
import time
from typing import Any
from bson import ObjectId
from pymongo import UpdateOne

from app.core.bson_utils import parse_object_id, to_decimal, to_money_float
from app.core.clock import get_business_date, now_utc
from app.core.config import settings
from app.core.exceptions import (
    DomainValidationError,
    DuplicateResourceError,
    NotFoundError,
    UnprocessableEntityError,
)
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import (
    SupplierCatalogRepository,
    compute_total_pages,
)
from app.schemas.common import PaginatedResponse
from app.schemas.supplier_catalog import (
    CatalogFiltersResponse,
    CatalogItemDetailResponse,
    CatalogItemListItem,
    ImportWarningSchema,
    LatestImportStatusResponse,
    LinkedProductSummary,
    LoadToStockRequest,
    LoadToStockResponse,
    LoadToStockSkippedItem,
    PackagingCountItem,
    PriceChangeEventItem,
    PriceChangesSummaryResponse,
    PurgeDiscontinuedResponse,
    RollbackImportResponse,
    SupplierFlagsSchema,
    SupplierImportDetail,
    SupplierImportSummary,
    UploadedBySummary,
)
from app.schemas.user import UserResponse
from app.services.catalog_diff import build_rollback_operations, compute_catalog_diff
from app.services.supplier_parsing import (
    cleanup_expired_canonical_csvs,
    delete_canonical_csv,
    parse_and_normalize_supplier_bytes,
    sanitize_filename,
    save_canonical_csv,
)

logger = logging.getLogger(__name__)
DISCONTINUED_ALERT_THRESHOLD = 100


class SupplierCatalogService:
    def __init__(
        self,
        catalog_repo: SupplierCatalogRepository,
        product_repo: ProductRepository,
        supplier_code: str | None = None,
    ) -> None:
        self.repo = catalog_repo
        self.product_repo = product_repo
        self.supplier = supplier_code or settings.supplier_default_code

    # --- Serialización ---
    @staticmethod
    def _serialize_import_summary(doc: dict[str, Any], latest_completed_id: ObjectId | None = None) -> SupplierImportSummary:
        up_by = doc.get("uploaded_by") or {}
        return SupplierImportSummary(
            id=str(doc["_id"]),
            supplier=doc["supplier"],
            import_date=doc["import_date"],
            sequence_in_day=int(doc.get("sequence_in_day", 1)),
            status=doc["status"],
            mode=doc.get("mode", "full"),
            original_filename=doc.get("original_filename", ""),
            detected_format=doc.get("detected_format", "csv"),
            file_size_bytes=int(doc.get("file_size_bytes", 0)),
            file_hash=doc.get("file_hash", ""),
            content_hash=doc.get("content_hash", ""),
            total_items=int(doc.get("total_items", 0)),
            changed_count=int(doc.get("changed_count", 0)),
            price_up_count=int(doc.get("price_up_count", 0)),
            price_down_count=int(doc.get("price_down_count", 0)),
            unchanged_count=int(doc.get("unchanged_count", 0)),
            new_count=int(doc.get("new_count", 0)),
            reactivated_count=int(doc.get("reactivated_count", 0)),
            discontinued_count=int(doc.get("discontinued_count", 0)),
            metadata_updated_count=int(doc.get("metadata_updated_count", 0)),
            skipped_rows=int(doc.get("skipped_rows", 0)),
            invalid_rows=int(doc.get("invalid_rows", 0)),
            price_anomaly_count=int(doc.get("price_anomaly_count", 0)),
            duration_ms=int(doc.get("duration_ms", 0)),
            message=doc.get("message", ""),
            is_latest_completed=bool(latest_completed_id and doc["_id"] == latest_completed_id),
            uploaded_by=UploadedBySummary(
                user_id=str(up_by.get("user_id", "")),
                email=str(up_by.get("email", "")),
            ),
            rolled_back_at=doc.get("rolled_back_at"),
            created_at=doc["created_at"],
            completed_at=doc.get("completed_at"),
        )

    @staticmethod
    def _serialize_catalog_item(doc: dict[str, Any]) -> CatalogItemListItem:
        flags = doc.get("supplier_flags") or {}
        return CatalogItemListItem(
            id=str(doc["_id"]),
            supplier=doc["supplier"],
            code=doc["code"],
            description=doc["description"],
            description_clean=doc.get("description_clean") or doc["description"],
            supplier_flags=SupplierFlagsSchema(
                star_prefix=bool(flags.get("star_prefix", False)),
                hash_suffix=bool(flags.get("hash_suffix", False)),
            ),
            packaging_raw=doc.get("packaging_raw", ""),
            packaging=doc.get("packaging", "SIN_DATO"),
            is_liquidation=bool(doc.get("is_liquidation", False)),
            liquidation_tag=doc.get("liquidation_tag"),
            price_net=to_money_float(doc.get("price_net"), 2) or 0.0,
            price_with_vat=to_money_float(doc.get("price_with_vat"), 2) or 0.0,
            supplier_utility_pct=to_money_float(doc.get("supplier_utility_pct"), 2) or 0.0,
            price_pack_with_utility=to_money_float(doc.get("price_pack_with_utility"), 2) or 0.0,
            units_per_package=int(doc.get("units_per_package", 1)),
            price_unit_with_utility=to_money_float(doc.get("price_unit_with_utility"), 2) or 0.0,
            vat_rate_detected=to_money_float(doc.get("vat_rate_detected"), 3),
            price_anomaly=bool(doc.get("price_anomaly", False)),
            prev_price_with_vat=to_money_float(doc.get("prev_price_with_vat"), 2),
            prev_price_unit_with_utility=to_money_float(doc.get("prev_price_unit_with_utility"), 2),
            last_change_type=doc.get("last_change_type"),
            last_change_pct=to_money_float(doc.get("last_change_pct"), 2),
            in_latest_list=bool(doc.get("in_latest_list", True)),
            last_verified_at=doc["last_verified_at"],
            last_price_changed_at=doc.get("last_price_changed_at"),
            discontinued_at=doc.get("discontinued_at"),
            linked_product_id=str(doc["linked_product_id"]) if doc.get("linked_product_id") else None,
            image_source_url=doc.get("image_source_url"),
        )

    @staticmethod
    def _serialize_price_change(
        doc: dict[str, Any],
        linked_sale_prices: dict[str, float] | None = None,
        changes_count: int = 1,
    ) -> PriceChangeEventItem:
        code = doc["code"]
        sale_price = linked_sale_prices.get(code) if linked_sale_prices else None
        in_stock = bool(linked_sale_prices is not None and code in linked_sale_prices)
        return PriceChangeEventItem(
            id=str(doc["_id"]),
            import_id=str(doc["import_id"]),
            import_date=doc["import_date"],
            supplier=doc["supplier"],
            code=code,
            description_snapshot=doc.get("description_snapshot", ""),
            packaging_snapshot=doc.get("packaging_snapshot", "SIN_DATO"),
            change_type=doc["change_type"],
            is_reactivation=bool(doc.get("is_reactivation", False)),
            old_price_net=to_money_float(doc.get("old_price_net"), 2),
            new_price_net=to_money_float(doc.get("new_price_net"), 2),
            old_price_with_vat=to_money_float(doc.get("old_price_with_vat"), 2),
            new_price_with_vat=to_money_float(doc.get("new_price_with_vat"), 2),
            old_price_unit=to_money_float(doc.get("old_price_unit"), 2),
            new_price_unit=to_money_float(doc.get("new_price_unit"), 2),
            old_units_per_package=doc.get("old_units_per_package"),
            new_units_per_package=doc.get("new_units_per_package"),
            diff_amount=to_money_float(doc.get("diff_amount"), 2),
            diff_pct=to_money_float(doc.get("diff_pct"), 2),
            in_my_stock=in_stock,
            my_sale_price=sale_price,
            changes_count=changes_count,
            created_at=doc["created_at"],
        )

    # --- Recuperación al arrancar ---
    async def recover_interrupted_imports(self) -> int:
        stale = await self.repo.find_stale_processing_imports(self.supplier)
        recovered = 0
        for imp in stale:
            logger.warning("Recuperando importación interrumpida %s...", imp["_id"])
            await self._execute_rollback_core(imp, mark_status="failed")
            recovered += 1
        return recovered

    # --- Subida y procesamiento diario ---
    async def process_daily_upload(
        self,
        *,
        raw_bytes: bytes,
        filename: str | None,
        current_user: UserResponse,
        force: bool = False,
    ) -> SupplierImportSummary:
        started = time.perf_counter()
        now = now_utc()
        today_str = get_business_date(now)
        clean_filename = sanitize_filename(filename)

        # Chequeo rápido por file_hash antes de parsear
        quick_file_hash = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
        same_day_key = f"{self.supplier}|{today_str}|{quick_file_hash}"
        existing_dup = await self.repo.find_same_day_duplicate(same_day_key)
        if existing_dup is not None:
            raise DuplicateResourceError(
                f"Esta misma lista ('{existing_dup.get('original_filename')}') ya fue cargada hoy ({today_str}). "
                "Si el proveedor publicó una actualización nueva más tarde, seleccioná el archivo actualizado."
            )

        await self.repo.acquire_lock(self.supplier, "import", current_user.id, now)
        created_import_id: ObjectId | None = None
        try:
            parsed = parse_and_normalize_supplier_bytes(raw_bytes, clean_filename)

            # Chequeo de mismo contenido normalizado en el mismo día (ej. .xls y .csv idénticos subidos hoy)
            same_day_content = await self.repo.find_same_day_by_content_hash(
                self.supplier, today_str, parsed.content_hash
            )
            if same_day_content is not None:
                raise DuplicateResourceError(
                    f"El contenido de esta lista ya fue cargado hoy ({today_str}) desde '{same_day_content.get('original_filename')}'. "
                    "No se detectaron diferencias respecto a esa carga del día."
                )

            latest_completed = await self.repo.get_latest_completed_import(self.supplier)
            seq_in_day = (await self.repo.count_completed_in_day(self.supplier, today_str)) + 1

            # Modo validación rápida: mismo contenido exacto que la última carga vigente, pero en un nuevo día
            if (
                latest_completed is not None
                and latest_completed.get("content_hash") == parsed.content_hash
                and latest_completed.get("import_date") != today_str
            ):
                active_count, _, _ = await self.repo.get_catalog_counts(self.supplier)
                quick_doc: dict[str, Any] = {
                    "supplier": self.supplier,
                    "import_date": today_str,
                    "sequence_in_day": seq_in_day,
                    "status": "completed",
                    "mode": "quick_validation",
                    "original_filename": clean_filename,
                    "detected_format": parsed.detected_format,
                    "file_size_bytes": len(raw_bytes),
                    "file_hash": parsed.file_hash,
                    "content_hash": parsed.content_hash,
                    "same_day_dedupe_key": same_day_key,
                    "previous_import_id": latest_completed["_id"],
                    "total_items": len(parsed.rows),
                    "changed_count": 0,
                    "price_up_count": 0,
                    "price_down_count": 0,
                    "unchanged_count": active_count or len(parsed.rows),
                    "new_count": 0,
                    "reactivated_count": 0,
                    "discontinued_count": 0,
                    "metadata_updated_count": 0,
                    "skipped_rows": parsed.skipped_rows,
                    "invalid_rows": parsed.invalid_rows,
                    "price_anomaly_count": parsed.price_anomaly_count,
                    "warnings": [
                        {"row": w.row, "code": w.code, "message": w.message} for w in parsed.warnings
                    ],
                    "normalized_csv_path": None,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "message": (
                        f"Sin variaciones de precio respecto a la carga del {latest_completed['import_date']}. "
                        f"Se validaron {len(parsed.rows)} artículos con fecha de hoy."
                    ),
                    "uploaded_by": {"user_id": current_user.id, "email": current_user.email},
                    "rolled_back_at": None,
                    "rolled_back_by": None,
                    "created_at": now,
                    "completed_at": now,
                }
                new_id = await self.repo.insert_import(quick_doc)
                await self.repo.quick_validate_all_active(
                    supplier=self.supplier,
                    new_import_id=new_id,
                    verified_at=now,
                )
                cleanup_expired_canonical_csvs()
                quick_doc["_id"] = new_id
                return self._serialize_import_summary(quick_doc, latest_completed_id=new_id)

            # Guardia anti-archivo truncado frente al catálogo vigente actual
            existing_map = await self.repo.fetch_all_catalog_map(self.supplier)
            current_active_count = sum(1 for doc in existing_map.values() if doc.get("in_latest_list", True))
            if (
                not force
                and current_active_count >= 50
                and len(parsed.rows) < int(current_active_count * settings.import_min_rows_ratio)
            ):
                raise UnprocessableEntityError(
                    f"La lista subida contiene {len(parsed.rows)} artículos, pero el catálogo vigente tiene "
                    f"{current_active_count}. Por seguridad se bloqueó la carga para evitar discontinuar miles de "
                    "artículos por un archivo incompleto. Si es intencional, activá 'Forzar carga incompleta'."
                )

            mode = "baseline" if len(existing_map) == 0 else "full"
            processing_doc: dict[str, Any] = {
                "supplier": self.supplier,
                "import_date": today_str,
                "sequence_in_day": seq_in_day,
                "status": "processing",
                "mode": mode,
                "original_filename": clean_filename,
                "detected_format": parsed.detected_format,
                "file_size_bytes": len(raw_bytes),
                "file_hash": parsed.file_hash,
                "content_hash": parsed.content_hash,
                "same_day_dedupe_key": same_day_key,
                "previous_import_id": latest_completed["_id"] if latest_completed else None,
                "total_items": len(parsed.rows),
                "changed_count": 0,
                "price_up_count": 0,
                "price_down_count": 0,
                "unchanged_count": 0,
                "new_count": 0,
                "reactivated_count": 0,
                "discontinued_count": 0,
                "metadata_updated_count": 0,
                "skipped_rows": parsed.skipped_rows,
                "invalid_rows": parsed.invalid_rows,
                "price_anomaly_count": parsed.price_anomaly_count,
                "warnings": [{"row": w.row, "code": w.code, "message": w.message} for w in parsed.warnings],
                "normalized_csv_path": None,
                "duration_ms": 0,
                "message": "",
                "uploaded_by": {"user_id": current_user.id, "email": current_user.email},
                "rolled_back_at": None,
                "rolled_back_by": None,
                "created_at": now,
                "completed_at": None,
            }
            created_import_id = await self.repo.insert_import(processing_doc)
            csv_path = save_canonical_csv(str(created_import_id), parsed.canonical_csv_text)

            diff_plan = compute_catalog_diff(
                supplier=self.supplier,
                import_id=created_import_id,
                import_date=today_str,
                now=now,
                existing_by_code=existing_map,
                incoming_rows=parsed.rows,
            )

            # 1) Persistir primero historial con before_snapshot
            if diff_plan.history_docs:
                await self.repo.bulk_insert_history(diff_plan.history_docs)

            # 2) Aplicar operaciones bulk de altas/cambios/discontinuados
            if diff_plan.catalog_ops:
                await self.repo.bulk_write_catalog(diff_plan.catalog_ops)

            # 3) Actualizar last_verified_at de los artículos sin cambios
            if diff_plan.unchanged_codes:
                await self.repo.mark_unchanged_codes_verified(
                    supplier=self.supplier,
                    codes=diff_plan.unchanged_codes,
                    import_id=created_import_id,
                    verified_at=now,
                )

            completed_at = now_utc()
            duration_ms = int((time.perf_counter() - started) * 1000)
            if mode == "baseline":
                msg = f"Catálogo inicial cargado con {len(parsed.rows)} artículos vigentes."
            else:
                msg = (
                    f"Lista procesada: {diff_plan.changed_count} cambiaron de precio "
                    f"(▲ {diff_plan.price_up_count} / ▼ {diff_plan.price_down_count}), "
                    f"{len(diff_plan.unchanged_codes)} validados sin cambios, "
                    f"{diff_plan.new_count} nuevos y {diff_plan.discontinued_count} discontinuados."
                )

            final_fields = {
                "status": "completed",
                "changed_count": diff_plan.changed_count,
                "price_up_count": diff_plan.price_up_count,
                "price_down_count": diff_plan.price_down_count,
                "unchanged_count": len(diff_plan.unchanged_codes),
                "new_count": diff_plan.new_count,
                "reactivated_count": diff_plan.reactivated_count,
                "discontinued_count": diff_plan.discontinued_count,
                "metadata_updated_count": diff_plan.metadata_updated_count,
                "normalized_csv_path": csv_path,
                "duration_ms": duration_ms,
                "message": msg,
                "completed_at": completed_at,
            }
            await self.repo.update_import(created_import_id, final_fields)
            cleanup_expired_canonical_csvs()

            saved_doc = await self.repo.get_import_by_id(created_import_id)
            assert saved_doc is not None
            return self._serialize_import_summary(saved_doc, latest_completed_id=created_import_id)

        except Exception:
            if created_import_id is not None:
                failed_doc = await self.repo.get_import_by_id(created_import_id)
                if failed_doc is not None:
                    await self._execute_rollback_core(failed_doc, mark_status="failed")
            raise
        finally:
            await self.repo.release_lock(self.supplier)

    # --- Rollback y Eliminación ---
    async def _execute_rollback_core(
        self,
        import_doc: dict[str, Any],
        *,
        mark_status: str,
        actor: UserResponse | None = None,
    ) -> RollbackImportResponse:
        now = now_utc()
        imp_id: ObjectId = import_doc["_id"]
        prev_import = await self.repo.get_previous_completed_import(self.supplier, imp_id)

        history_docs = await self.repo.get_history_for_import(imp_id)
        current_map = await self.repo.fetch_all_catalog_map(self.supplier)

        ops, restored_updated, deleted_new, preserved_linked_new = build_rollback_operations(
            supplier=self.supplier,
            history_docs=history_docs,
            current_items_by_code=current_map,
            now=now,
        )
        if ops:
            await self.repo.bulk_write_catalog(ops)

        reverted_verified = 0
        if prev_import is not None:
            reverted_verified = await self.repo.revert_verified_items_for_import(
                supplier=self.supplier,
                import_id=imp_id,
                previous_import_id=prev_import["_id"],
                previous_verified_at=prev_import.get("completed_at") or prev_import["created_at"],
                now=now,
            )

        await self.repo.delete_history_for_import(imp_id)
        delete_canonical_csv(import_doc.get("normalized_csv_path"))

        upd: dict[str, Any] = {
            "status": mark_status,
            "normalized_csv_path": None,
            "rolled_back_at": now,
        }
        if actor is not None:
            upd["rolled_back_by"] = {"user_id": actor.id, "email": actor.email}

        await self.repo.update_import(imp_id, upd, unset_fields=["same_day_dedupe_key"])

        return RollbackImportResponse(
            import_id=str(imp_id),
            restored_updated_count=restored_updated,
            deleted_new_count=deleted_new,
            preserved_linked_new_count=preserved_linked_new,
            reverted_verified_count=reverted_verified,
            previous_import_id=str(prev_import["_id"]) if prev_import else None,
            message=(
                f"Se deshizo la carga correctamente: {restored_updated} artículos restaurados a su estado previo "
                f"y {deleted_new} altas recientes revertidas. El stock propio no fue modificado."
            ),
        )

    async def rollback_latest_import(self, import_id_str: str, current_user: UserResponse) -> RollbackImportResponse:
        imp_oid = parse_object_id(import_id_str, "ID de importación")
        now = now_utc()
        await self.repo.acquire_lock(self.supplier, "rollback", current_user.id, now)
        try:
            imp_doc = await self.repo.get_import_by_id(imp_oid)
            if imp_doc is None or imp_doc.get("supplier") != self.supplier:
                raise NotFoundError("La importación indicada no existe.")
            if imp_doc.get("status") != "completed":
                raise DuplicateResourceError(
                    f"Solo se puede deshacer una carga completada (estado actual: {imp_doc.get('status')})."
                )

            latest = await self.repo.get_latest_completed_import(self.supplier)
            if latest is None or latest["_id"] != imp_oid:
                raise DuplicateResourceError(
                    "Solo se permite deshacer la última importación vigente. "
                    "Para limpiar registros más antiguos usá 'Eliminar del historial'."
                )

            return await self._execute_rollback_core(imp_doc, mark_status="rolled_back", actor=current_user)
        finally:
            await self.repo.release_lock(self.supplier)

    async def delete_historical_import(self, import_id_str: str, current_user: UserResponse) -> None:
        imp_oid = parse_object_id(import_id_str, "ID de importación")
        now = now_utc()
        await self.repo.acquire_lock(self.supplier, "delete_import", current_user.id, now)
        try:
            imp_doc = await self.repo.get_import_by_id(imp_oid)
            if imp_doc is None or imp_doc.get("supplier") != self.supplier:
                raise NotFoundError("La importación indicada no existe.")

            latest = await self.repo.get_latest_completed_import(self.supplier)
            if latest is not None and latest["_id"] == imp_oid:
                raise DuplicateResourceError(
                    "No se puede eliminar directamente la última importación vigente. "
                    "Usá 'Deshacer carga' si querés revertir sus cambios."
                )

            await self.repo.delete_history_for_import(imp_oid)
            delete_canonical_csv(imp_doc.get("normalized_csv_path"))
            await self.repo.delete_import_doc(imp_oid)
        finally:
            await self.repo.release_lock(self.supplier)

    # --- Consultas de Importaciones y Catálogo ---
    async def get_latest_status(self) -> LatestImportStatusResponse:
        latest = await self.repo.get_latest_completed_import(self.supplier)
        active_cnt, disc_cnt, linked_cnt = await self.repo.get_catalog_counts(self.supplier)
        summary = (
            self._serialize_import_summary(latest, latest_completed_id=latest["_id"])
            if latest is not None
            else None
        )
        return LatestImportStatusResponse(
            latest_import=summary,
            active_catalog_count=active_cnt,
            discontinued_catalog_count=disc_cnt,
            discontinued_alert=disc_cnt > DISCONTINUED_ALERT_THRESHOLD,
            discontinued_threshold=DISCONTINUED_ALERT_THRESHOLD,
            in_my_stock_count=linked_cnt,
        )

    async def list_imports(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> PaginatedResponse[SupplierImportSummary]:
        latest = await self.repo.get_latest_completed_import(self.supplier)
        latest_id = latest["_id"] if latest else None
        docs, total = await self.repo.list_imports_paginated(
            supplier=self.supplier,
            page=page,
            page_size=page_size,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        items = [self._serialize_import_summary(d, latest_completed_id=latest_id) for d in docs]
        return PaginatedResponse[SupplierImportSummary](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=compute_total_pages(total, page_size),
        )

    async def get_import_detail(self, import_id_str: str) -> SupplierImportDetail:
        imp_oid = parse_object_id(import_id_str, "ID de importación")
        doc = await self.repo.get_import_by_id(imp_oid)
        if doc is None or doc.get("supplier") != self.supplier:
            raise NotFoundError("Importación no encontrada.")
        latest = await self.repo.get_latest_completed_import(self.supplier)
        base = self._serialize_import_summary(doc, latest_completed_id=latest["_id"] if latest else None)
        warnings = [
            ImportWarningSchema(row=int(w.get("row", 0)), code=str(w.get("code", "")), message=str(w.get("message", "")))
            for w in (doc.get("warnings") or [])
        ]
        return SupplierImportDetail(**base.model_dump(), warnings=warnings)

    async def list_catalog_items(
        self,
        *,
        q: str | None,
        packaging: str | None,
        is_liquidation: bool | None,
        stock_status: str,
        changed_within_days: int | None,
        status: str,
        price_anomaly: bool | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[CatalogItemListItem]:
        changed_since: datetime | None = None
        if changed_within_days is not None:
            now = now_utc()
            if changed_within_days <= 0:
                today_str = get_business_date(now)
                changed_since = datetime.fromisoformat(f"{today_str}T00:00:00+00:00") - timedelta(hours=4)
            else:
                changed_since = now - timedelta(days=changed_within_days)

        docs, total = await self.repo.list_catalog_items_paginated(
            supplier=self.supplier,
            q=q,
            packaging=packaging,
            is_liquidation=is_liquidation,
            stock_status=stock_status,
            changed_since=changed_since,
            status=status,
            price_anomaly=price_anomaly,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse[CatalogItemListItem](
            items=[self._serialize_catalog_item(d) for d in docs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=compute_total_pages(total, page_size),
        )

    async def get_catalog_filters(self) -> CatalogFiltersResponse:
        facets = await self.repo.get_packaging_facets(self.supplier)
        active_cnt, disc_cnt, linked_cnt = await self.repo.get_catalog_counts(self.supplier)
        return CatalogFiltersResponse(
            packagings=[PackagingCountItem(packaging=f["packaging"], count=f["count"]) for f in facets],
            active_count=active_cnt,
            discontinued_count=disc_cnt,
            discontinued_alert=disc_cnt > DISCONTINUED_ALERT_THRESHOLD,
            discontinued_threshold=DISCONTINUED_ALERT_THRESHOLD,
            in_my_stock_count=linked_cnt,
        )

    async def get_catalog_item_detail(self, code: str) -> CatalogItemDetailResponse:
        doc = await self.repo.get_item_by_code(self.supplier, code.strip())
        if doc is None:
            raise NotFoundError(f"El artículo con código '{code}' no existe en el catálogo.")

        base = self._serialize_catalog_item(doc)
        linked_summary: LinkedProductSummary | None = None
        linked_sale_map: dict[str, float] = {}
        if doc.get("linked_product_id"):
            pdoc = await self.product_repo.get_by_id(doc["linked_product_id"])
            if pdoc is not None:
                summary_dict = self.product_repo.to_summary_dict(pdoc)
                linked_summary = LinkedProductSummary(**summary_dict)
                linked_sale_map[doc["code"]] = summary_dict["unit_price"]

        recent_docs = await self.repo.get_recent_changes_for_code(self.supplier, doc["code"], limit=20)
        recent_items = [self._serialize_price_change(h, linked_sale_map) for h in recent_docs]

        return CatalogItemDetailResponse(
            **base.model_dump(),
            first_seen_at=doc.get("first_seen_at") or doc["created_at"],
            linked_product=linked_summary,
            recent_changes=recent_items,
        )

    async def purge_discontinued(self, current_user: UserResponse) -> PurgeDiscontinuedResponse:
        now = now_utc()
        await self.repo.acquire_lock(self.supplier, "purge_discontinued", current_user.id, now)
        try:
            deleted_cnt, preserved_cnt, remaining_cnt = await self.repo.purge_discontinued_unlinked(self.supplier)
            return PurgeDiscontinuedResponse(
                deleted_count=deleted_cnt,
                preserved_linked_count=preserved_cnt,
                remaining_discontinued_count=remaining_cnt,
            )
        finally:
            await self.repo.release_lock(self.supplier)

    # --- Cargar ítems al stock propio (products + stock_movements) ---
    async def load_items_to_stock(
        self,
        payload: LoadToStockRequest,
        current_user: UserResponse,
    ) -> LoadToStockResponse:
        now = now_utc()
        user_oid = parse_object_id(current_user.id, "ID de usuario")
        requested_codes = list({item.code.strip() for item in payload.items})

        catalog_map = await self.repo.find_items_by_codes(self.supplier, requested_codes)
        existing_products = await self.product_repo.find_by_supplier_codes(self.supplier, requested_codes)

        created_ids: list[str] = []
        skipped: list[LoadToStockSkippedItem] = []
        catalog_link_ops: list[Any] = []
        seen_in_request: set[str] = set()

        for req_item in payload.items:
            code = req_item.code.strip()
            if code in seen_in_request:
                skipped.append(LoadToStockSkippedItem(code=code, reason="Código repetido en la misma solicitud."))
                continue
            seen_in_request.add(code)

            cat_doc = catalog_map.get(code)
            if cat_doc is None:
                skipped.append(LoadToStockSkippedItem(code=code, reason="No existe en el catálogo del proveedor."))
                continue

            if code in existing_products or cat_doc.get("linked_product_id") is not None:
                skipped.append(LoadToStockSkippedItem(code=code, reason="Ya se encuentra cargado en tu stock propio."))
                continue

            base_sku = f"ELO-{code}"
            sku = base_sku
            suffix = 1
            while await self.product_repo.sku_exists(sku):
                suffix += 1
                sku = f"{base_sku}-{suffix}"

            metadata_snapshot = {
                "supplier": self.supplier,
                "supplier_code": code,
                "supplier_packaging": cat_doc.get("packaging"),
                "units_per_package": int(cat_doc.get("units_per_package", 1)),
                "cost_reference_at_load": {
                    "price_net": to_money_float(cat_doc.get("price_net"), 2),
                    "price_with_vat": to_money_float(cat_doc.get("price_with_vat"), 2),
                    "price_pack_with_utility": to_money_float(cat_doc.get("price_pack_with_utility"), 2),
                    "price_unit_with_utility": to_money_float(cat_doc.get("price_unit_with_utility"), 2),
                    "captured_at": now.isoformat(),
                },
            }

            new_prod_id = await self.product_repo.create_product_with_initial_movement(
                sku=sku,
                barcode=req_item.barcode.strip() if req_item.barcode and req_item.barcode.strip() else None,
                name=cat_doc.get("description_clean") or cat_doc["description"],
                description=cat_doc["description"],
                category=req_item.category.strip() or "Librería",
                unit_price=Decimal(str(req_item.sale_price)),
                initial_stock=req_item.initial_stock,
                min_stock=req_item.min_stock,
                supplier_ref={"supplier": self.supplier, "code": code},
                metadata=metadata_snapshot,
                user_id=user_oid,
                reference_id=cat_doc["_id"],
                now=now,
            )

            created_ids.append(str(new_prod_id))
            catalog_link_ops.append(
                UpdateOne(
                    {"_id": cat_doc["_id"]},
                    {"$set": {"linked_product_id": new_prod_id, "updated_at": now}},
                )
            )

        if catalog_link_ops:
            await self.repo.bulk_write_catalog(catalog_link_ops)

        return LoadToStockResponse(
            created_count=len(created_ids),
            skipped_count=len(skipped),
            created_product_ids=created_ids,
            skipped=skipped,
        )

    # --- Precios Diff (Variaciones) ---
    async def _resolve_diff_period(
        self,
        *,
        import_id: str | None,
        preset: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[ObjectId | None, str | None, str | None, str]:
        if import_id:
            imp_oid = parse_object_id(import_id, "ID de importación")
            imp = await self.repo.get_import_by_id(imp_oid)
            if imp is None or imp.get("supplier") != self.supplier:
                raise NotFoundError("Importación no encontrada.")
            return imp_oid, None, None, f"Carga {imp['import_date']} (#{imp.get('sequence_in_day', 1)})"

        today_str = get_business_date(now_utc())
        today_dt = datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        if preset == "today":
            return None, today_str, today_str, f"Hoy ({today_str})"
        if preset == "last_7_days":
            start = (today_dt - timedelta(days=6)).strftime("%Y-%m-%d")
            return None, start, today_str, "Últimos 7 días"
        if preset == "last_30_days":
            start = (today_dt - timedelta(days=29)).strftime("%Y-%m-%d")
            return None, start, today_str, "Últimos 30 días"

        if date_from or date_to:
            if date_from and date_to and date_from > date_to:
                raise DomainValidationError("La fecha inicial no puede ser posterior a la fecha final.")
            return None, date_from, date_to, f"Rango {date_from or '...'} a {date_to or '...'}"

        # Por defecto: última importación completada
        latest = await self.repo.get_latest_completed_import(self.supplier)
        if latest is None:
            return None, today_str, today_str, "Sin cargas registradas"
        return (
            latest["_id"],
            None,
            None,
            f"Última carga: {latest['import_date']} (#{latest.get('sequence_in_day', 1)})",
        )

    async def _get_linked_sale_prices_map(self) -> dict[str, float]:
        linked_map = await self.repo.get_linked_codes_map(self.supplier)
        if not linked_map:
            return {}
        prod_docs = await self.product_repo.find_by_ids(list(linked_map.values()))
        out: dict[str, float] = {}
        for code, prod_id in linked_map.items():
            pdoc = prod_docs.get(prod_id)
            if pdoc is not None:
                out[code] = to_money_float(pdoc.get("unit_price"), 2) or 0.0
        return out

    async def list_price_changes(
        self,
        *,
        import_id: str | None,
        preset: str | None,
        date_from: str | None,
        date_to: str | None,
        change_types: list[str] | None,
        only_my_stock: bool,
        min_pct: float | None,
        q: str | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[PriceChangeEventItem]:
        imp_oid, d_from, d_to, _ = await self._resolve_diff_period(
            import_id=import_id, preset=preset, date_from=date_from, date_to=date_to
        )
        linked_sale_prices = await self._get_linked_sale_prices_map()
        allowed_codes: list[str] | None = None
        if only_my_stock:
            allowed_codes = list(linked_sale_prices.keys())
            if not allowed_codes:
                return PaginatedResponse[PriceChangeEventItem](
                    items=[], total=0, page=page, page_size=page_size, total_pages=0
                )

        filt = self.repo.build_price_changes_filter(
            supplier=self.supplier,
            import_id=imp_oid,
            date_from=d_from,
            date_to=d_to,
            change_types=change_types,
            min_pct=min_pct,
            allowed_codes=allowed_codes,
            q=q,
        )
        docs, total = await self.repo.list_price_change_events_paginated(
            filt=filt,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        items = [self._serialize_price_change(d, linked_sale_prices) for d in docs]
        return PaginatedResponse[PriceChangeEventItem](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=compute_total_pages(total, page_size),
        )

    async def get_price_changes_summary(
        self,
        *,
        import_id: str | None,
        preset: str | None,
        date_from: str | None,
        date_to: str | None,
        only_my_stock: bool = False,
        min_pct: float | None = None,
        q: str | None = None,
    ) -> PriceChangesSummaryResponse:
        imp_oid, d_from, d_to, label = await self._resolve_diff_period(
            import_id=import_id, preset=preset, date_from=date_from, date_to=date_to
        )
        linked_sale_prices = await self._get_linked_sale_prices_map()
        linked_codes = list(linked_sale_prices.keys())

        allowed_codes: list[str] | None = linked_codes if only_my_stock else None
        if only_my_stock and not linked_codes:
            return PriceChangesSummaryResponse(period_label=label)

        base_filter = self.repo.build_price_changes_filter(
            supplier=self.supplier,
            import_id=imp_oid,
            date_from=d_from,
            date_to=d_to,
            change_types=None,
            min_pct=min_pct,
            allowed_codes=allowed_codes,
            q=q,
        )
        counts = await self.repo.summarize_price_changes(
            base_period_filter=base_filter,
            linked_codes=linked_codes,
        )
        return PriceChangesSummaryResponse(
            price_up=counts["price_up"],
            price_down=counts["price_down"],
            new=counts["new"],
            discontinued=counts["discontinued"],
            total=counts["total"],
            in_my_stock_changed=counts["in_my_stock_changed"],
            period_label=label,
        )
