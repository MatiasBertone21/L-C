from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from bson import ObjectId
from pymongo import DeleteOne, InsertOne, UpdateOne

from app.core.bson_utils import DEC2, DEC6, to_dec128, to_decimal
from app.services.supplier_parsing.models import NormalizedRow

SNAPSHOT_KEYS = (
    "description",
    "description_clean",
    "search_text",
    "supplier_flags",
    "packaging_raw",
    "packaging",
    "is_liquidation",
    "liquidation_tag",
    "price_net",
    "price_with_vat",
    "supplier_utility_pct",
    "price_pack_with_utility",
    "units_per_package",
    "price_unit_with_utility",
    "vat_rate_detected",
    "price_anomaly",
    "prev_price_net",
    "prev_price_with_vat",
    "prev_price_unit_with_utility",
    "last_change_type",
    "last_change_pct",
    "image_source_url",
    "in_latest_list",
    "last_import_id",
    "last_verified_at",
    "last_price_changed_at",
    "discontinued_at",
    "discontinued_import_id",
    "row_fingerprint",
)


@dataclass(slots=True)
class CatalogDiffPlan:
    is_baseline: bool
    catalog_ops: list[Any] = field(default_factory=list)
    history_docs: list[dict[str, Any]] = field(default_factory=list)
    unchanged_codes: list[str] = field(default_factory=list)
    price_up_count: int = 0
    price_down_count: int = 0
    new_count: int = 0
    reactivated_count: int = 0
    discontinued_count: int = 0
    metadata_updated_count: int = 0

    @property
    def changed_count(self) -> int:
        return self.price_up_count + self.price_down_count


def extract_before_snapshot(existing_doc: dict[str, Any]) -> dict[str, Any]:
    return {k: existing_doc.get(k) for k in SNAPSHOT_KEYS}


def _row_to_catalog_fields(row: NormalizedRow) -> dict[str, Any]:
    return {
        "description": row.description,
        "description_clean": row.description_clean,
        "search_text": row.search_text,
        "supplier_flags": {
            "star_prefix": row.star_prefix,
            "hash_suffix": row.hash_suffix,
        },
        "packaging_raw": row.packaging_raw,
        "packaging": row.packaging,
        "is_liquidation": row.is_liquidation,
        "liquidation_tag": row.liquidation_tag,
        "price_net": to_dec128(row.price_net, DEC6),
        "price_with_vat": to_dec128(row.price_with_vat, DEC6),
        "supplier_utility_pct": to_dec128(row.supplier_utility_pct, DEC2),
        "price_pack_with_utility": to_dec128(row.price_pack_with_utility, DEC6),
        "units_per_package": row.units_per_package,
        "price_unit_with_utility": to_dec128(row.price_unit_with_utility, DEC6),
        "vat_rate_detected": to_dec128(row.vat_rate_detected, Decimal("0.001")) if row.vat_rate_detected is not None else None,
        "price_anomaly": row.price_anomaly,
        "image_source_url": row.image_source_url,
        "row_fingerprint": row.row_fingerprint,
    }


def compute_catalog_diff(
    *,
    supplier: str,
    import_id: ObjectId,
    import_date: str,
    now: datetime,
    existing_by_code: dict[str, dict[str, Any]],
    incoming_rows: list[NormalizedRow],
) -> CatalogDiffPlan:
    is_baseline = len(existing_by_code) == 0
    plan = CatalogDiffPlan(is_baseline=is_baseline)
    seen_codes: set[str] = set()

    for row in incoming_rows:
        seen_codes.add(row.code)
        existing = existing_by_code.get(row.code)
        base_fields = _row_to_catalog_fields(row)

        if existing is None:
            # Producto nuevo en el catálogo maestro
            plan.new_count += 1
            new_doc = {
                "supplier": supplier,
                "code": row.code,
                **base_fields,
                "prev_price_net": None,
                "prev_price_with_vat": None,
                "prev_price_unit_with_utility": None,
                "last_change_type": None if is_baseline else "new",
                "last_change_pct": None,
                "in_latest_list": True,
                "first_seen_at": now,
                "first_import_id": import_id,
                "last_import_id": import_id,
                "last_verified_at": now,
                "last_price_changed_at": None if is_baseline else now,
                "discontinued_at": None,
                "discontinued_import_id": None,
                "linked_product_id": None,
                "created_at": now,
                "updated_at": now,
            }
            plan.catalog_ops.append(InsertOne(new_doc))

            # Registramos en historial para rollback total; en baseline queda oculto en Diff para evitar 6.385 filas iniciales
            plan.history_docs.append(
                {
                    "import_id": import_id,
                    "import_date": import_date,
                    "supplier": supplier,
                    "code": row.code,
                    "description_snapshot": row.description,
                    "packaging_snapshot": row.packaging,
                    "change_type": "new",
                    "visible_in_diff": not is_baseline,
                    "is_reactivation": False,
                    "old_price_net": None,
                    "new_price_net": to_dec128(row.price_net, DEC6),
                    "old_price_with_vat": None,
                    "new_price_with_vat": to_dec128(row.price_with_vat, DEC6),
                    "old_price_unit": None,
                    "new_price_unit": to_dec128(row.price_unit_with_utility, DEC6),
                    "old_units_per_package": None,
                    "new_units_per_package": row.units_per_package,
                    "diff_amount": None,
                    "diff_pct": None,
                    "abs_diff_pct": to_dec128(Decimal("0"), Decimal("0.0001")),
                    "before_snapshot": None,
                    "created_at": now,
                }
            )
            continue

        was_in_latest = bool(existing.get("in_latest_list", True))
        old_net = to_decimal(existing.get("price_net")) or Decimal("0")
        old_vat = to_decimal(existing.get("price_with_vat")) or Decimal("0")
        old_unit = to_decimal(existing.get("price_unit_with_utility")) or Decimal("0")
        old_uxp = int(existing.get("units_per_package", 1))

        if not was_in_latest:
            # Producto que estaba discontinuado y volvió a aparecer en la lista
            plan.new_count += 1
            plan.reactivated_count += 1
            diff_amt = row.price_with_vat - old_vat
            diff_pct = (
                ((diff_amt / old_vat) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                if old_vat > 0
                else Decimal("0")
            )
            upd_fields = {
                **base_fields,
                "prev_price_net": existing.get("price_net"),
                "prev_price_with_vat": existing.get("price_with_vat"),
                "prev_price_unit_with_utility": existing.get("price_unit_with_utility"),
                "last_change_type": "new",
                "last_change_pct": to_dec128(diff_pct, Decimal("0.01")),
                "in_latest_list": True,
                "discontinued_at": None,
                "discontinued_import_id": None,
                "last_import_id": import_id,
                "last_verified_at": now,
                "last_price_changed_at": now,
                "updated_at": now,
            }
            plan.catalog_ops.append(UpdateOne({"_id": existing["_id"]}, {"$set": upd_fields}))
            plan.history_docs.append(
                {
                    "import_id": import_id,
                    "import_date": import_date,
                    "supplier": supplier,
                    "code": row.code,
                    "description_snapshot": row.description,
                    "packaging_snapshot": row.packaging,
                    "change_type": "new",
                    "visible_in_diff": True,
                    "is_reactivation": True,
                    "old_price_net": existing.get("price_net"),
                    "new_price_net": to_dec128(row.price_net, DEC6),
                    "old_price_with_vat": existing.get("price_with_vat"),
                    "new_price_with_vat": to_dec128(row.price_with_vat, DEC6),
                    "old_price_unit": existing.get("price_unit_with_utility"),
                    "new_price_unit": to_dec128(row.price_unit_with_utility, DEC6),
                    "old_units_per_package": old_uxp,
                    "new_units_per_package": row.units_per_package,
                    "diff_amount": to_dec128(diff_amt, DEC6),
                    "diff_pct": to_dec128(diff_pct, Decimal("0.0001")),
                    "abs_diff_pct": to_dec128(abs(diff_pct), Decimal("0.0001")),
                    "before_snapshot": extract_before_snapshot(existing),
                    "created_at": now,
                }
            )
            continue

        # Producto vigente: comparar precio cuantizado a centavos o cambio de unidades por paquete
        old_vat_c = old_vat.quantize(DEC2, rounding=ROUND_HALF_UP)
        new_vat_c = row.price_with_vat.quantize(DEC2, rounding=ROUND_HALF_UP)
        old_net_c = old_net.quantize(DEC2, rounding=ROUND_HALF_UP)
        new_net_c = row.price_net.quantize(DEC2, rounding=ROUND_HALF_UP)

        price_changed = (old_vat_c != new_vat_c) or (old_net_c != new_net_c) or (old_uxp != row.units_per_package)

        if price_changed:
            diff_amt = row.price_with_vat - old_vat
            if abs(diff_amt) < Decimal("0.005") and old_uxp != row.units_per_package:
                unit_diff = row.price_unit_with_utility - old_unit
                base_for_pct = old_unit if old_unit > 0 else Decimal("1")
                diff_pct = ((unit_diff / base_for_pct) * Decimal("100")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                change_type = "price_up" if unit_diff >= 0 else "price_down"
            else:
                base_for_pct = old_vat if old_vat > 0 else (old_net if old_net > 0 else Decimal("1"))
                effective_diff = diff_amt if abs(diff_amt) >= Decimal("0.005") else (row.price_net - old_net)
                diff_pct = ((effective_diff / base_for_pct) * Decimal("100")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                change_type = "price_up" if effective_diff >= 0 else "price_down"

            if change_type == "price_up":
                plan.price_up_count += 1
            else:
                plan.price_down_count += 1

            upd_fields = {
                **base_fields,
                "prev_price_net": existing.get("price_net"),
                "prev_price_with_vat": existing.get("price_with_vat"),
                "prev_price_unit_with_utility": existing.get("price_unit_with_utility"),
                "last_change_type": change_type,
                "last_change_pct": to_dec128(diff_pct, Decimal("0.01")),
                "in_latest_list": True,
                "last_import_id": import_id,
                "last_verified_at": now,
                "last_price_changed_at": now,
                "updated_at": now,
            }
            plan.catalog_ops.append(UpdateOne({"_id": existing["_id"]}, {"$set": upd_fields}))
            plan.history_docs.append(
                {
                    "import_id": import_id,
                    "import_date": import_date,
                    "supplier": supplier,
                    "code": row.code,
                    "description_snapshot": row.description,
                    "packaging_snapshot": row.packaging,
                    "change_type": change_type,
                    "visible_in_diff": True,
                    "is_reactivation": False,
                    "old_price_net": existing.get("price_net"),
                    "new_price_net": to_dec128(row.price_net, DEC6),
                    "old_price_with_vat": existing.get("price_with_vat"),
                    "new_price_with_vat": to_dec128(row.price_with_vat, DEC6),
                    "old_price_unit": existing.get("price_unit_with_utility"),
                    "new_price_unit": to_dec128(row.price_unit_with_utility, DEC6),
                    "old_units_per_package": old_uxp,
                    "new_units_per_package": row.units_per_package,
                    "diff_amount": to_dec128(diff_amt, DEC6),
                    "diff_pct": to_dec128(diff_pct, Decimal("0.0001")),
                    "abs_diff_pct": to_dec128(abs(diff_pct), Decimal("0.0001")),
                    "before_snapshot": extract_before_snapshot(existing),
                    "created_at": now,
                }
            )
            continue

        # Precio idéntico: revisar si cambió algún metadato (descripción, empaque o URL imagen)
        if existing.get("row_fingerprint") != row.row_fingerprint:
            plan.metadata_updated_count += 1
            upd_fields = {
                **base_fields,
                "in_latest_list": True,
                "last_import_id": import_id,
                "last_verified_at": now,
                "updated_at": now,
            }
            plan.catalog_ops.append(UpdateOne({"_id": existing["_id"]}, {"$set": upd_fields}))
            plan.history_docs.append(
                {
                    "import_id": import_id,
                    "import_date": import_date,
                    "supplier": supplier,
                    "code": row.code,
                    "description_snapshot": row.description,
                    "packaging_snapshot": row.packaging,
                    "change_type": "metadata_only",
                    "visible_in_diff": False,
                    "is_reactivation": False,
                    "old_price_net": existing.get("price_net"),
                    "new_price_net": to_dec128(row.price_net, DEC6),
                    "old_price_with_vat": existing.get("price_with_vat"),
                    "new_price_with_vat": to_dec128(row.price_with_vat, DEC6),
                    "old_price_unit": existing.get("price_unit_with_utility"),
                    "new_price_unit": to_dec128(row.price_unit_with_utility, DEC6),
                    "old_units_per_package": old_uxp,
                    "new_units_per_package": row.units_per_package,
                    "diff_amount": to_dec128(Decimal("0"), DEC6),
                    "diff_pct": to_dec128(Decimal("0"), Decimal("0.0001")),
                    "abs_diff_pct": to_dec128(Decimal("0"), Decimal("0.0001")),
                    "before_snapshot": extract_before_snapshot(existing),
                    "created_at": now,
                }
            )
        else:
            plan.unchanged_codes.append(row.code)

    # Detectar artículos que estaban en la última lista y dejaron de aparecer hoy
    for code, existing in existing_by_code.items():
        if code not in seen_codes and bool(existing.get("in_latest_list", True)):
            plan.discontinued_count += 1
            plan.catalog_ops.append(
                UpdateOne(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "in_latest_list": False,
                            "discontinued_at": now,
                            "discontinued_import_id": import_id,
                            "updated_at": now,
                        }
                    },
                )
            )
            plan.history_docs.append(
                {
                    "import_id": import_id,
                    "import_date": import_date,
                    "supplier": supplier,
                    "code": code,
                    "description_snapshot": existing.get("description", ""),
                    "packaging_snapshot": existing.get("packaging", "SIN_DATO"),
                    "change_type": "discontinued",
                    "visible_in_diff": True,
                    "is_reactivation": False,
                    "old_price_net": existing.get("price_net"),
                    "new_price_net": None,
                    "old_price_with_vat": existing.get("price_with_vat"),
                    "new_price_with_vat": None,
                    "old_price_unit": existing.get("price_unit_with_utility"),
                    "new_price_unit": None,
                    "old_units_per_package": int(existing.get("units_per_package", 1)),
                    "new_units_per_package": None,
                    "diff_amount": None,
                    "diff_pct": None,
                    "abs_diff_pct": to_dec128(Decimal("0"), Decimal("0.0001")),
                    "before_snapshot": extract_before_snapshot(existing),
                    "created_at": now,
                }
            )

    return plan


def build_rollback_operations(
    *,
    supplier: str,
    history_docs: list[dict[str, Any]],
    current_items_by_code: dict[str, dict[str, Any]],
    now: datetime,
) -> tuple[list[Any], int, int, int]:
    ops: list[Any] = []
    restored_updated = 0
    deleted_new = 0
    preserved_linked_new = 0

    for hdoc in history_docs:
        code = hdoc["code"]
        before = hdoc.get("before_snapshot")
        current = current_items_by_code.get(code)

        if before is None:
            # Fue un InsertOne nuevo en esta importación
            if current is None:
                continue
            if current.get("linked_product_id") is not None:
                preserved_linked_new += 1
                ops.append(
                    UpdateOne(
                        {"_id": current["_id"]},
                        {
                            "$set": {
                                "in_latest_list": False,
                                "discontinued_at": now,
                                "updated_at": now,
                            }
                        },
                    )
                )
            else:
                deleted_new += 1
                ops.append(DeleteOne({"supplier": supplier, "code": code, "linked_product_id": None}))
        else:
            restored_updated += 1
            restore_payload = {**before, "updated_at": now}
            ops.append(UpdateOne({"supplier": supplier, "code": code}, {"$set": restore_payload}))

    return ops, restored_updated, deleted_new, preserved_linked_new
