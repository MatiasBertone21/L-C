import csv
from datetime import datetime, timezone
import io
from typing import Any
from httpx import AsyncClient
import pytest

from app.services import supplier_catalog_service as svc_module

HEADERS = [
    "Código",
    "Descripción",
    "Empaque",
    "$ S/IVA",
    "$ C/IVA",
    "Utilidad %",
    "$ C/IVA y Utilidad Paquete",
    "Unidades Por Paquete",
    "$ C/IVA y Utilidad Unidad",
    "IMG",
]


def build_csv(rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADERS)
    w.writerow(["0", "", "", "0", "0", "10", "0", "1", "0", ""])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


async def login_headers(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_full_supplier_import_diff_rollback_and_stock_flow(
    client: AsyncClient,
    test_credentials: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers = await login_headers(
        client, test_credentials["admin_email"], test_credentials["admin_password"]
    )
    user_headers = await login_headers(
        client, test_credentials["user_email"], test_credentials["user_password"]
    )

    # Día 1 mañana: fijar reloj a 2026-11-26
    day1 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(svc_module, "now_utc", lambda: day1)

    list_day1_morning = build_csv(
        [
            ["1001", "*CUADERNO A4 RAYADO #", "UNIDAD", "1000", "1210", "10", "1331", "1", "1331", ""],
            ["1002", "LAPICERA AZUL X12", "CAJA", "2000", "2420", "10", "2662", "12", "221,8333", ""],
            ["1003", "GOMA BORRAR BLANCA", "LIQUIDA", "500", "605", "10", "665,5", "1", "665,5", ""],
        ]
    )

    # User (vendedor) no puede subir lista -> 403
    forbidden_resp = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=user_headers,
        files={"file": ("lista_maniana.csv", list_day1_morning, "text/csv")},
    )
    assert forbidden_resp.status_code == 403

    # Admin sube baseline inicial -> 201
    imp1_resp = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        files={"file": ("lista_maniana.csv", list_day1_morning, "text/csv")},
    )
    assert imp1_resp.status_code == 201, imp1_resp.text
    imp1 = imp1_resp.json()
    assert imp1["mode"] == "baseline"
    assert imp1["total_items"] == 3
    assert imp1["new_count"] == 3

    # Subir exactamente el mismo archivo el mismo día -> 409 Conflict en español
    dup_resp = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        files={"file": ("lista_maniana.csv", list_day1_morning, "text/csv")},
    )
    assert dup_resp.status_code == 409
    assert "ya fue cargada hoy" in dup_resp.json()["detail"]

    # User PUEDE consultar catálogo y ver costos -> 200
    items_user_resp = await client.get("/api/v1/supplier-catalog/items", headers=user_headers)
    assert items_user_resp.status_code == 200
    assert items_user_resp.json()["total"] == 3

    # Admin carga el código 1001 al stock propio (products + stock_movements)
    load_resp = await client.post(
        "/api/v1/supplier-catalog/items/load-to-stock",
        headers=admin_headers,
        json={
            "items": [
                {
                    "code": "1001",
                    "initial_stock": 15,
                    "min_stock": 3,
                    "sale_price": 1950.0,
                    "category": "Cuadernos",
                }
            ]
        },
    )
    assert load_resp.status_code == 201
    assert load_resp.json()["created_count"] == 1

    # Día 1 tarde: el proveedor publica una segunda lista con cambios reales -> permitida!
    day1_afternoon = datetime(2026, 11, 26, 19, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(svc_module, "now_utc", lambda: day1_afternoon)

    list_day1_afternoon = build_csv(
        [
            # 1001 sube 10% y cambia descripción
            ["1001", "*CUADERNO A4 RAYADO PREMIUM #", "UNIDAD", "1100", "1331", "10", "1464,1", "1", "1464,1", ""],
            # 1002 sin cambios
            ["1002", "LAPICERA AZUL X12", "CAJA", "2000", "2420", "10", "2662", "12", "221,8333", ""],
            # 1003 desaparece (discontinuado) y entra 1004 nuevo
            ["1004", "MARCADOR FLUORESCENTE AMARILLO", "UNIDAD", "800", "968", "10", "1064,8", "1", "1064,8", ""],
        ]
    )
    imp2_resp = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        files={"file": ("lista_tarde.csv", list_day1_afternoon, "text/csv")},
    )
    assert imp2_resp.status_code == 201, imp2_resp.text
    imp2 = imp2_resp.json()
    assert imp2["sequence_in_day"] == 2
    assert imp2["price_up_count"] == 1
    assert imp2["unchanged_count"] == 1
    assert imp2["new_count"] == 1
    assert imp2["discontinued_count"] == 1

    # Consultar Precios Diff con filtro only_my_stock=true -> debe traer solo 1001 con my_sale_price=1950
    diff_stock_resp = await client.get(
        "/api/v1/supplier-catalog/price-changes",
        params={"only_my_stock": "true"},
        headers=user_headers,
    )
    assert diff_stock_resp.status_code == 200
    diff_items = diff_stock_resp.json()["items"]
    assert len(diff_items) == 1
    assert diff_items[0]["code"] == "1001"
    assert diff_items[0]["my_sale_price"] == 1950.0
    assert diff_items[0]["change_type"] == "price_up"

    # Día 2: se sube exactamente el mismo archivo de la tarde anterior -> modo quick_validation
    day2 = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(svc_module, "now_utc", lambda: day2)
    imp3_resp = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        files={"file": ("lista_tarde.csv", list_day1_afternoon, "text/csv")},
    )
    assert imp3_resp.status_code == 201
    imp3 = imp3_resp.json()
    assert imp3["mode"] == "quick_validation"
    assert imp3["changed_count"] == 0

    # No permite DELETE directo de la última vigente (imp3) -> 409
    del_latest_resp = await client.delete(
        f"/api/v1/supplier-catalog/imports/{imp3['id']}",
        headers=admin_headers,
    )
    assert del_latest_resp.status_code == 409

    # Deshacer imp3 (quick_validation) y luego deshacer imp2 -> debe revertir precio, descripción, alta 1004 y discontinuado 1003!
    rb3 = await client.post(f"/api/v1/supplier-catalog/imports/{imp3['id']}/rollback", headers=admin_headers)
    assert rb3.status_code == 200

    rb2 = await client.post(f"/api/v1/supplier-catalog/imports/{imp2['id']}/rollback", headers=admin_headers)
    assert rb2.status_code == 200

    # Verificar que 1001 volvió a $1210 y descripción original, 1003 volvió a estar activo y 1004 fue eliminado
    detail_1001 = await client.get("/api/v1/supplier-catalog/items/1001", headers=admin_headers)
    assert detail_1001.status_code == 200
    assert detail_1001.json()["price_with_vat"] == 1210.0
    assert detail_1001.json()["description"] == "*CUADERNO A4 RAYADO #"
    assert detail_1001.json()["linked_product"]["unit_price"] == 1950.0  # Stock propio intacto

    detail_1003 = await client.get("/api/v1/supplier-catalog/items/1003", headers=admin_headers)
    assert detail_1003.status_code == 200
    assert detail_1003.json()["in_latest_list"] is True

    detail_1004 = await client.get("/api/v1/supplier-catalog/items/1004", headers=admin_headers)
    assert detail_1004.status_code == 404


@pytest.mark.asyncio
async def test_discontinued_alert_over_100_and_purge(
    client: AsyncClient,
    test_credentials: dict[str, str],
) -> None:
    admin_headers = await login_headers(
        client, test_credentials["admin_email"], test_credentials["admin_password"]
    )

    # Cargar 105 artículos iniciales
    initial_rows = [
        [str(2000 + i), f"ARTICULO PRUEBA {i}", "UNIDAD", "100", "121", "10", "133,1", "1", "133,1", ""]
        for i in range(105)
    ]
    r1 = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        files={"file": ("inicial_105.csv", build_csv(initial_rows), "text/csv")},
    )
    assert r1.status_code == 201

    # Vincular uno de los que van a quedar discontinuados (2050) al stock propio para verificar que NO se purga
    await client.post(
        "/api/v1/supplier-catalog/items/load-to-stock",
        headers=admin_headers,
        json={"items": [{"code": "2050", "initial_stock": 5, "min_stock": 1, "sale_price": 250.0}]},
    )

    # Subir nueva lista con solo 3 artículos forzando carga incompleta (force=true) -> 102 quedan discontinuados (> 100)
    reduced_rows = initial_rows[:3]
    r2 = await client.post(
        "/api/v1/supplier-catalog/imports",
        headers=admin_headers,
        data={"force": "true"},
        files={"file": ("reducida.csv", build_csv(reduced_rows), "text/csv")},
    )
    assert r2.status_code == 201

    status_resp = await client.get("/api/v1/supplier-catalog/imports/latest", headers=admin_headers)
    status_data = status_resp.json()
    assert status_data["discontinued_catalog_count"] == 102
    assert status_data["discontinued_alert"] is True

    # Ejecutar depuración de discontinuados -> borra 101 y preserva 1 (el vinculado 2050)
    purge_resp = await client.delete("/api/v1/supplier-catalog/items/discontinued", headers=admin_headers)
    assert purge_resp.status_code == 200
    purge_data = purge_resp.json()
    assert purge_data["deleted_count"] == 101
    assert purge_data["preserved_linked_count"] == 1
    assert purge_data["remaining_discontinued_count"] == 1
