# L&C — Sistema de Gestión de Stock y Ventas (Librería y Papelería)

Monorepo del sistema de gestión de inventario y punto de venta (POS) compuesto por:
- **Backend (`backend/`):** FastAPI + Pydantic v2 + MongoDB (`pymongo` `AsyncMongoClient`) + JWT (`admin` / `user`)
- **Frontend (`frontend/`):** Svelte 5 + Vite 6 (optimizado para PCs de bajos/medios recursos — en construcción incremental)
- **Base de Datos:** MongoDB 7.0 con volumen persistente y acceso directo desde **MongoDB Compass**

---

## Requisitos Previos

- **Docker Desktop** (Docker Engine + Docker Compose)
- *(Opcional)* **MongoDB Compass** para inspeccionar colecciones localmente

> No se requiere instalar Python, Node.js ni MongoDB globalmente en el sistema operativo.

---

## Puesta en Marcha Rápida

1. **Crear el archivo `.env` local a partir de la plantilla:**

   ```powershell
   Copy-Item .env.example .env
   ```
   Editá `.env` definiendo tus credenciales locales (`MONGO_INITDB_ROOT_PASSWORD`, `JWT_SECRET_KEY`, `SEED_ADMIN_PASSWORD`, `SEED_USER_PASSWORD`, etc.).

2. **Levantar Backend + MongoDB:**

   ```powershell
   docker compose up --build -d
   ```
   *(Nota: cuando esté habilitado el servicio de interfaz web en fases posteriores, podés incluirlo con `docker compose --profile frontend up --build -d`).*

3. **Cargar usuarios iniciales de desarrollo (`admin` y `user`):**

   ```powershell
   docker compose exec backend python -m scripts.seed
   ```

4. **Ejecutar smoke tests del backend (`pytest`):**

   ```powershell
   docker compose exec backend pytest -v
   ```

---

## URLs de Desarrollo

| Servicio | URL Local | Descripción |
| :--- | :--- | :--- |
| **Backend Healthcheck** | http://localhost:8000/health | Estado de API + ping real a MongoDB |
| **Swagger UI (OpenAPI)** | http://localhost:8000/docs | Documentación interactiva y prueba de JWT |
| **Frontend (perfil opcional)** | http://localhost:5173 | Interfaz web Svelte 5 |
| **MongoDB** | `localhost:27017` | Puerto expuesto para MongoDB Compass |

---

## Conexión desde MongoDB Compass

Abrí **MongoDB Compass**, pegá la siguiente URI reemplazando usuario y contraseña por los valores configurados en tu `.env` local y hacé clic en **Connect**:

```text
mongodb://<MONGO_INITDB_ROOT_USERNAME>:<MONGO_INITDB_ROOT_PASSWORD>@localhost:27017/lc_inventory?authSource=admin
```
