import asyncio
import logging

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.product_repository import ProductRepository
from app.repositories.supplier_catalog_repository import SupplierCatalogRepository
from app.repositories.user_repository import UserRepository
from app.schemas.product import ProductCreate
from app.schemas.user import UserCreate, UserResponse, UserRole
from app.services.product_service import ProductService
from app.services.user_service import UserService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

SAMPLE_STATIONERY_PRODUCTS: list[dict] = [
    {"sku": "LIB-CUA-001", "barcode": "7798001000011", "name": "Cuaderno Tapa Dura A4 Rayado 84h", "category": "Cuadernos", "unit_price": 5200.0, "stock": 28, "min_stock": 6},
    {"sku": "LIB-CUA-002", "barcode": "7798001000028", "name": "Cuaderno Tapa Dura A4 Cuadriculado 84h", "category": "Cuadernos", "unit_price": 5200.0, "stock": 22, "min_stock": 6},
    {"sku": "LIB-CUA-003", "barcode": "7798001000035", "name": "Cuaderno Escolar ABC Araña 48h Rayado", "category": "Cuadernos", "unit_price": 4100.0, "stock": 4, "min_stock": 8},
    {"sku": "LIB-REP-001", "barcode": "7798001000042", "name": "Repuesto Escolar Nº3 Rayado x480 Hojas", "category": "Papelería", "unit_price": 14800.0, "stock": 12, "min_stock": 4},
    {"sku": "LIB-REP-002", "barcode": "7798001000059", "name": "Resma A4 75gr Obra Blanca x500 Hojas", "category": "Papelería", "unit_price": 8900.0, "stock": 35, "min_stock": 10},
    {"sku": "LIB-REP-003", "barcode": "7798001000066", "name": "Block Dibujo Nº5 Blanco x24 Hojas", "category": "Papelería", "unit_price": 2350.0, "stock": 18, "min_stock": 5},
    {"sku": "LIB-ESC-001", "barcode": "7798001000073", "name": "Bolígrafo Trazo Medio Azul", "category": "Escritura", "unit_price": 650.0, "stock": 90, "min_stock": 20},
    {"sku": "LIB-ESC-002", "barcode": "7798001000080", "name": "Bolígrafo Trazo Medio Negro", "category": "Escritura", "unit_price": 650.0, "stock": 64, "min_stock": 20},
    {"sku": "LIB-ESC-003", "barcode": "7798001000097", "name": "Lápiz Negro Grafito HB Nº2", "category": "Escritura", "unit_price": 480.0, "stock": 75, "min_stock": 20},
    {"sku": "LIB-ESC-004", "barcode": "7798001000103", "name": "Portaminas 0.5mm con Grip", "category": "Escritura", "unit_price": 1850.0, "stock": 3, "min_stock": 5},
    {"sku": "LIB-ESC-005", "barcode": "7798001000110", "name": "Resaltador Pastel Amarillo Biselado", "category": "Escritura", "unit_price": 1250.0, "stock": 30, "min_stock": 8},
    {"sku": "LIB-ESC-006", "barcode": "7798001000127", "name": "Marcador para Pizarra Recargable Negro", "category": "Escritura", "unit_price": 1950.0, "stock": 0, "min_stock": 6},
    {"sku": "LIB-COL-001", "barcode": "7798001000134", "name": "Lápices de Colores Largos x12 Unidades", "category": "Arte y Escolar", "unit_price": 3900.0, "stock": 25, "min_stock": 6},
    {"sku": "LIB-COL-002", "barcode": "7798001000141", "name": "Marcadores Escolares Lavables x10 Colores", "category": "Arte y Escolar", "unit_price": 3450.0, "stock": 19, "min_stock": 5},
    {"sku": "LIB-COL-003", "barcode": "7798001000158", "name": "Acuarela Escolar x12 Colores con Pincel", "category": "Arte y Escolar", "unit_price": 2700.0, "stock": 14, "min_stock": 4},
    {"sku": "LIB-ADH-001", "barcode": "7798001000165", "name": "Adhesivo en Barra 21gr", "category": "Adhesivos", "unit_price": 1600.0, "stock": 40, "min_stock": 10},
    {"sku": "LIB-ADH-002", "barcode": "7798001000172", "name": "Silicona Líquida Transparente 100ml", "category": "Adhesivos", "unit_price": 2150.0, "stock": 2, "min_stock": 6},
    {"sku": "LIB-ADH-003", "barcode": "7798001000189", "name": "Cinta Adhesiva Transparente 18mm x 30m", "category": "Adhesivos", "unit_price": 980.0, "stock": 32, "min_stock": 8},
    {"sku": "LIB-ACC-001", "barcode": "7798001000196", "name": "Goma de Borrar Blanca Lápiz/Tinta", "category": "Accesorios", "unit_price": 520.0, "stock": 55, "min_stock": 15},
    {"sku": "LIB-ACC-002", "barcode": "7798001000202", "name": "Sacapuntas Metálico Simple", "category": "Accesorios", "unit_price": 600.0, "stock": 48, "min_stock": 12},
    {"sku": "LIB-ACC-003", "barcode": "7798001000219", "name": "Tijera Escolar Punta Redonda 13cm", "category": "Accesorios", "unit_price": 1750.0, "stock": 16, "min_stock": 5},
    {"sku": "LIB-GEO-001", "barcode": "7798001000226", "name": "Set Geometría 3 Piezas 20cm Irrompible", "category": "Geometría", "unit_price": 2400.0, "stock": 15, "min_stock": 4},
    {"sku": "LIB-ORG-001", "barcode": "7798001000233", "name": "Carpeta Escolar Nº3 3 Anillos Negra", "category": "Archivo", "unit_price": 4600.0, "stock": 11, "min_stock": 4},
    {"sku": "LIB-ORG-002", "barcode": "7798001000240", "name": "Abrochadora Pinza Metálica Nº10", "category": "Oficina", "unit_price": 6800.0, "stock": 0, "min_stock": 3},
]


async def seed_database() -> None:
    if not settings.seed_admin_password or not settings.seed_user_password:
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD y SEED_USER_PASSWORD deben estar definidos en .env para ejecutar el seed."
        )

    await connect_to_mongo()
    try:
        db = get_database()
        await db["users"].delete_many({"email": {"$regex": r"\.local$"}})

        user_repo = UserRepository(db)
        product_repo = ProductRepository(db)
        catalog_repo = SupplierCatalogRepository(db)

        await user_repo.ensure_indexes()
        await product_repo.ensure_indexes()
        await catalog_repo.ensure_indexes()

        user_service = UserService(user_repo)
        product_service = ProductService(
            product_repo=product_repo,
            catalog_repo=catalog_repo,
            user_repo=user_repo,
        )

        users_to_seed = [
            UserCreate(
                email=settings.seed_admin_email,
                full_name="Administración L&C",
                password=settings.seed_admin_password,
                role=UserRole.ADMIN,
                is_active=True,
            ),
            UserCreate(
                email=settings.seed_user_email,
                full_name="Mostrador Ventas L&C",
                password=settings.seed_user_password,
                role=UserRole.USER,
                is_active=True,
            ),
        ]

        admin_response: UserResponse | None = None
        for payload in users_to_seed:
            existing = await user_repo.get_by_email(payload.email)
            if existing is not None:
                logger.info("Usuario '%s' (%s) ya existe — omitiendo.", existing.email, existing.role.value)
                if existing.role == UserRole.ADMIN:
                    admin_response = UserResponse(
                        id=existing.id,
                        email=existing.email,
                        full_name=existing.full_name,
                        role=existing.role,
                        is_active=existing.is_active,
                        created_at=existing.created_at,
                        updated_at=existing.updated_at,
                    )
                continue

            created = await user_service.create_user(payload)
            logger.info("Usuario creado: '%s' con rol '%s'.", created.email, created.role.value)
            if created.role == UserRole.ADMIN:
                admin_response = created

        existing_products_count = await product_repo.count_all()
        if existing_products_count > 0:
            logger.info(
                "Colección 'products' ya cuenta con %d artículo(s) — se omite seed de productos ficticios.",
                existing_products_count,
            )
        elif admin_response is not None:
            seeded_count = 0
            for raw_prod in SAMPLE_STATIONERY_PRODUCTS:
                await product_service.create_product(ProductCreate(**raw_prod), admin_response)
                seeded_count += 1
            logger.info(
                "Se cargaron %d artículos ficticios de librería con sus movimientos iniciales en 'stock_movements'.",
                seeded_count,
            )
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed_database())
