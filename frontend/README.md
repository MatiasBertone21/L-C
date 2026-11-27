# Frontend Web — L&C Stock & POS (`Svelte 5` + `Vite 6`)

Interfaz web liviana orientada a mostrador / punto de venta (POS) y gestión de inventario para librería y papelería.

---

## Principios de Diseño y Rendimiento

El frontend está diseñado específicamente para operar con fluidez en **computadoras de recursos bajos y medios**:

- **Stack minimalista:** Svelte 5 + Vite 6 sin frameworks pesados de componentes ni librerías de animación costosas.
- **Estilos nativos:** CSS con Custom Properties centralizadas (`src/lib/styles/tokens.css`) alineadas a la paleta institucional del logo L&C y con contraste accesible (WCAG AA/AAA).
- **Renderizado eficiente:** Tablas HTML semánticas con paginación en backend, búsqueda con `debounce` y flujos de mostrador operables por teclado (`Enter`, `Tab`, `Esc`).
- **Cliente API centralizado:** Comunicación desacoplada en `src/lib/api/` con inyección automática de JWT y manejo unificado de sesión (`401` / `403`).

---

## Estado Actual del Módulo

Esta carpeta se publica inicialmente con su documentación base mientras se completan de forma incremental los módulos del backend (`auth` → `products` & `stock_movements` → `sales`).

Una vez integradas las vistas definitivas de Login, Inventario y Mostrador POS, el contenedor de desarrollo con HMR se levanta mediante Docker Compose en `http://localhost:5173`.
