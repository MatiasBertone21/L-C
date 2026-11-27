from httpx import AsyncClient
import pytest


async def login_headers(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_products_crud_atomic_stock_and_movements_audit(
    client: AsyncClient,
    test_credentials: dict[str, str],
) -> None:
    admin_headers = await login_headers(
        client, test_credentials["admin_email"], test_credentials["admin_password"]
    )
    user_headers = await login_headers(
        client, test_credentials["user_email"], test_credentials["user_password"]
    )

    # 1) Rol user NO puede crear productos -> 403
    forbid_create = await client.post(
        "/api/v1/products",
        headers=user_headers,
        json={
            "sku": "LIB-TEST-01",
            "barcode": "7790001112223",
            "name": "Cuaderno Universitario A4",
            "category": "Cuadernos",
            "unit_price": 4500.0,
            "stock": 10,
            "min_stock": 4,
        },
    )
    assert forbid_create.status_code == 403

    # 2) Admin crea producto con stock inicial 10 -> 201 y genera movimiento initial_stock
    create_resp = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": "LIB-TEST-01",
            "barcode": "7790001112223",
            "name": "Cuaderno Universitario A4",
            "description": "Rayado 84 hojas",
            "category": "Cuadernos",
            "unit_price": 4500.0,
            "stock": 10,
            "min_stock": 4,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    prod = create_resp.json()
    prod_id = prod["id"]
    assert prod["stock"] == 10
    assert prod["stock_status"] == "ok"

    # 3) Duplicado de SKU o barcode -> 409 Conflict
    dup_barcode = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": "LIB-TEST-02",
            "barcode": "7790001112223",
            "name": "Otro Producto",
            "category": "Cuadernos",
            "unit_price": 1200.0,
            "stock": 0,
            "min_stock": 1,
        },
    )
    assert dup_barcode.status_code == 409

    # 4) Lookup exacto por código de barras y por SKU para rol user (mostrador) -> 200
    lookup_bc = await client.get("/api/v1/products/lookup/7790001112223", headers=user_headers)
    assert lookup_bc.status_code == 200
    assert lookup_bc.json()["id"] == prod_id

    lookup_sku = await client.get("/api/v1/products/lookup/lib-test-01", headers=user_headers)
    assert lookup_sku.status_code == 200
    assert lookup_sku.json()["id"] == prod_id

    # 5) PATCH actualiza unit_price sin mutar stock
    patch_resp = await client.patch(
        f"/api/v1/products/{prod_id}",
        headers=admin_headers,
        json={"unit_price": 4950.0, "min_stock": 8},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["unit_price"] == 4950.0
    assert patch_resp.json()["stock"] == 10

    # 6) Egreso de 7 unidades (queda en 3 <= min_stock 8 -> low_stock)
    out_resp = await client.post(
        f"/api/v1/products/{prod_id}/stock",
        headers=admin_headers,
        json={"type": "out", "quantity": 7, "reason": "damaged", "notes": "Tapas dañadas"},
    )
    assert out_resp.status_code == 200
    out_data = out_resp.json()
    assert out_data["stock"] == 3
    assert out_data["stock_status"] == "low_stock"

    # 7) Intento de descontar más del stock disponible (5 > 3) -> 409 InsufficientStockError y stock sigue en 3
    neg_resp = await client.post(
        f"/api/v1/products/{prod_id}/stock",
        headers=admin_headers,
        json={"type": "out", "quantity": 5, "reason": "manual_adjustment"},
    )
    assert neg_resp.status_code == 409
    assert neg_resp.json()["code"] == "insufficient_stock"

    # 8) Ajuste de conteo físico exacto (adjustment -> new_stock = 0 -> out_of_stock)
    adj_resp = await client.post(
        f"/api/v1/products/{prod_id}/stock",
        headers=admin_headers,
        json={"type": "adjustment", "new_stock": 0, "reason": "manual_adjustment", "notes": "Arqueo estantería"},
    )
    assert adj_resp.status_code == 200
    assert adj_resp.json()["stock"] == 0
    assert adj_resp.json()["stock_status"] == "out_of_stock"

    # 9) Verificar KPIs en /products/summary y filtros stock_alert
    summary_resp = await client.get("/api/v1/products/summary", headers=user_headers)
    assert summary_resp.status_code == 200
    s_data = summary_resp.json()
    assert s_data["active_count"] == 1
    assert s_data["out_of_stock_count"] == 1
    assert s_data["low_stock_count"] == 1

    # 10) Historial auditable en /stock-movements: prohibido para user (403), visible para admin con 3 eventos
    forbid_mov = await client.get("/api/v1/stock-movements", headers=user_headers)
    assert forbid_mov.status_code == 403

    mov_resp = await client.get(
        "/api/v1/stock-movements",
        params={"product_id": prod_id},
        headers=admin_headers,
    )
    assert mov_resp.status_code == 200
    mov_items = mov_resp.json()["items"]
    assert len(mov_items) == 3
    assert [m["type"] for m in mov_items] == ["adjustment", "out", "in"]
    assert mov_items[0]["previous_stock"] == 3 and mov_items[0]["new_stock"] == 0
    assert mov_items[1]["previous_stock"] == 10 and mov_items[1]["new_stock"] == 3
    assert mov_items[2]["previous_stock"] == 0 and mov_items[2]["new_stock"] == 10

    # 11) Baja lógica DELETE -> deja de salir en activos pero conserva movimientos
    del_resp = await client.delete(f"/api/v1/products/{prod_id}", headers=admin_headers)
    assert del_resp.status_code == 204

    active_list = await client.get("/api/v1/products", headers=user_headers)
    assert active_list.json()["total"] == 0

    inactive_list = await client.get("/api/v1/products", params={"is_active": "false"}, headers=admin_headers)
    assert inactive_list.json()["total"] == 1
