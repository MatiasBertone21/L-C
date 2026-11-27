# Backend API — L&C Stock & POS (`FastAPI` + `MongoDB`)

Servicio REST asíncrono encargado de la autenticación, control de acceso por roles, inventario trazable y registro de ventas de librería/papelería.

---

## Stack Técnico

- **Framework:** FastAPI + Pydantic v2 (`pydantic-settings`)
- **Base de datos:** MongoDB 7.0 mediante el driver asíncrono oficial `pymongo` (`AsyncMongoClient`)
- **Seguridad:** JWT (`PyJWT`, esquema `Bearer`), contraseñas hasheadas con `bcrypt` y soporte opcional `X-API-Key` en `app/core/security.py` para integraciones o scripts futuros
- **Testing:** `pytest` + `pytest-asyncio` + `httpx` (sobre base aislada `<MONGO_DB_NAME>_test`)

---

## Arquitectura en Capas

```text
backend/
├── app/
│   ├── main.py                  # Entrada FastAPI, lifespan (conexión Mongo + índices), CORS y errores
│   ├── core/                    # Configuración (.env), conexión MongoDB, seguridad JWT/API-Key y excepciones
│   ├── schemas/                 # Contratos Pydantic v2 (Create, Update, Response, InDB, PaginatedResponse)
│   ├── repositories/            # Acceso exclusivo a colecciones MongoDB e índices (sin lógica HTTP)
│   ├── services/                # Casos de uso y reglas de aplicación
│   └── api/v1/                  # Routers HTTP, validación de entrada/salida y permisos por rol
├── scripts/
│   └── seed.py                  # Carga idempotente de datos iniciales de desarrollo
└── tests/                       # Smoke tests automatizados
```

---

## Endpoints Disponibles (Entrega Incremental 1 — `health` & `auth`)

| Método | Ruta | Acceso | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` y `/api/v1/health` | Público | Verifica estado de la API y ejecuta `ping` real a MongoDB. |
| `POST` | `/api/v1/auth/login` | Público | Autentica con `email` y `password`; retorna JWT `Bearer` y datos del usuario. |
| `GET` | `/api/v1/auth/me` | `user` / `admin` | Retorna el perfil del usuario autenticado. |
| `GET` | `/api/v1/users` | Solo `admin` | Lista usuarios paginados (`page`, `page_size`) sin exponer hashes. |
| `POST` | `/api/v1/users` | Solo `admin` | Crea un usuario nuevo con rol `admin` o `user`. |
| `GET` | `/api/v1/users/{user_id}` | Solo `admin` | Obtiene detalle de un usuario por ID. |
| `PATCH` | `/api/v1/users/{user_id}` | Solo `admin` | Actualiza nombre, rol, contraseña o estado activo/inactivo. |

---

## Comandos Rápidos (vía Docker Compose)

```powershell
# Levantar MongoDB + Backend con hot-reload
docker compose up --build -d

# Sembrar usuarios iniciales (admin y user configurados en .env)
docker compose exec backend python -m scripts.seed

# Correr suite de tests
docker compose exec backend pytest -v
```
