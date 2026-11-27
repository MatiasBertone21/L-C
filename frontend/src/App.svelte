<script>
  import { onMount } from 'svelte';
  import AppNavbar from './lib/components/AppNavbar.svelte';
  import Toast from './lib/components/Toast.svelte';
  import LoginPage from './pages/LoginPage.svelte';
  import SupplierCatalogPage from './pages/SupplierCatalogPage.svelte';
  import { auth } from './lib/stores/auth.svelte.js';
  import { navigateTo } from './lib/utils/navigation.js';

  let currentPath = $state(window.location.pathname);

  function syncLocation() {
    currentPath = window.location.pathname;
  }

  function handleGlobalLinkClick(event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!(event.target instanceof Element)) return;

    const anchor = event.target.closest('a');
    if (!anchor) return;
    if (anchor.target && anchor.target !== '_self') return;

    const href = anchor.getAttribute('href');
    if (!href || !href.startsWith('/')) return;

    event.preventDefault();
    navigateTo(href);
  }

  onMount(async () => {
    await auth.init();
  });

  $effect(() => {
    if (!auth.initialized) return;
    if (!auth.isAuthenticated && currentPath !== '/login') {
      const redirectTarget = `${window.location.pathname}${window.location.search}`;
      const loginUrl =
        redirectTarget && redirectTarget !== '/'
          ? `/login?redirect=${encodeURIComponent(redirectTarget)}`
          : '/login';
      navigateTo(loginUrl, { replace: true });
    } else if (auth.isAuthenticated && (currentPath === '/' || currentPath === '/login')) {
      navigateTo('/supplier-catalog', { replace: true });
    }
  });
</script>

<svelte:window onpopstate={syncLocation} onclick={handleGlobalLinkClick} />

<div class="app-shell">
  <AppNavbar {currentPath} />

  <main class="app-main">
    {#if !auth.initialized}
      <div class="app-loading">Verificando sesión...</div>
    {:else if !auth.isAuthenticated || currentPath === '/login'}
      <LoginPage />
    {:else if currentPath.startsWith('/supplier-catalog')}
      <SupplierCatalogPage />
    {:else}
      <section class="not-found-card">
        <h1>Página no encontrada</h1>
        <p>La ruta solicitada no existe en el sistema.</p>
        <a href="/supplier-catalog">Ir a Lista de Proveedor</a>
      </section>
    {/if}
  </main>

  <Toast />
</div>

<style>
  .app-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .app-main {
    flex: 1;
    width: 100%;
    max-width: 1380px;
    margin: 0 auto;
    padding: 1.15rem 1.25rem 2.2rem;
  }

  .app-loading {
    padding: 2.5rem 1rem;
    text-align: center;
    color: var(--color-text-secondary);
  }

  .not-found-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: 1.5rem;
  }

  .not-found-card h1 {
    margin: 0 0 0.4rem;
    font-size: 1.2rem;
  }

  .not-found-card p {
    margin: 0 0 0.9rem;
    color: var(--color-text-secondary);
  }

  .not-found-card a {
    color: var(--color-accent-blue);
    font-weight: 600;
  }
</style>
