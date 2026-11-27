<script>
  import { auth } from '../stores/auth.svelte.js';

  let { currentPath = '/' } = $props();
</script>

<header class="lc-navbar">
  <div class="lc-navbar__inner">
    <a class="lc-navbar__brand" href="/supplier-catalog">
      <img src="/logo-lc.jpg" alt="Logo L&C" width="38" height="38" class="lc-navbar__logo" />
      <div class="lc-navbar__titles">
        <span class="lc-navbar__name">Librería y Papelería L&amp;C</span>
        <span class="lc-navbar__sub">Gestión de Precios y Stock</span>
      </div>
    </a>

    {#if auth.isAuthenticated}
      <nav class="lc-navbar__links" aria-label="Navegación principal">
        <a
          href="/supplier-catalog"
          class:active={currentPath.startsWith('/supplier-catalog') || currentPath === '/'}
        >
          Lista de Proveedor
        </a>
      </nav>

      <div class="lc-navbar__user">
        <div class="lc-navbar__user-meta">
          <span class="lc-navbar__email">{auth.user?.full_name || auth.user?.email}</span>
          <span class="lc-navbar__role" class:is-admin={auth.isAdmin}>{auth.roleLabel}</span>
        </div>
        <button type="button" class="lc-navbar__logout" onclick={() => auth.logout()}>
          Salir
        </button>
      </div>
    {/if}
  </div>
</header>

<style>
  /* Fondo sólido sin backdrop-filter: blur para evitar scroll jank en PCs modestas */
  .lc-navbar {
    position: sticky;
    top: 0;
    z-index: 40;
    background-color: var(--color-sidebar-bg);
    color: var(--color-sidebar-text);
    border-bottom: 3px solid var(--color-brand-primary);
  }

  .lc-navbar__inner {
    max-width: 1380px;
    margin: 0 auto;
    padding: 0.55rem 1.25rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .lc-navbar__brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    text-decoration: none;
    color: inherit;
  }

  .lc-navbar__logo {
    border-radius: var(--radius-sm);
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: #ffffff;
    object-fit: cover;
  }

  .lc-navbar__titles {
    display: flex;
    flex-direction: column;
    line-height: 1.15;
  }

  .lc-navbar__name {
    font-weight: 700;
    font-size: 0.98rem;
    color: #ffffff;
  }

  .lc-navbar__sub {
    font-size: 0.75rem;
    color: var(--color-sidebar-muted);
  }

  .lc-navbar__links {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .lc-navbar__links a {
    color: var(--color-sidebar-muted);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.42rem 0.8rem;
    border-radius: var(--radius-sm);
  }

  .lc-navbar__links a:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
  }

  .lc-navbar__links a.active {
    background-color: var(--color-brand-primary);
    color: #ffffff;
  }

  .lc-navbar__user {
    display: flex;
    align-items: center;
    gap: 0.85rem;
  }

  .lc-navbar__user-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    line-height: 1.2;
  }

  .lc-navbar__email {
    font-size: 0.84rem;
    font-weight: 600;
    color: #ffffff;
  }

  .lc-navbar__role {
    font-size: 0.72rem;
    padding: 0.05rem 0.4rem;
    border-radius: 4px;
    background-color: rgba(255, 255, 255, 0.14);
    color: var(--color-sidebar-muted);
  }

  .lc-navbar__role.is-admin {
    background-color: var(--color-brand-primary);
    color: #ffffff;
  }

  .lc-navbar__logout {
    border: 1px solid rgba(255, 255, 255, 0.25);
    background: transparent;
    color: #ffffff;
    border-radius: var(--radius-sm);
    padding: 0.35rem 0.7rem;
    font-size: 0.84rem;
    font-weight: 600;
    cursor: pointer;
  }

  .lc-navbar__logout:hover {
    background-color: rgba(255, 255, 255, 0.12);
  }

  @media (max-width: 680px) {
    .lc-navbar__sub,
    .lc-navbar__email {
      display: none;
    }
  }
</style>
