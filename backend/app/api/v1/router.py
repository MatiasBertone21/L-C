from fastapi import APIRouter
from app.api.v1 import auth, health, products, stock_movements, supplier_catalog, users

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(products.router)
api_v1_router.include_router(stock_movements.router)
api_v1_router.include_router(supplier_catalog.router)
