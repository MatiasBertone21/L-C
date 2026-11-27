<script>
  import { auth } from '../lib/stores/auth.svelte.js';
  import { toasts } from '../lib/stores/toast.svelte.js';
  import { navigateTo } from '../lib/utils/navigation.js';
  import Button from '../lib/components/Button.svelte';

  let email = $state('');
  let password = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleSubmit(event) {
    event.preventDefault();
    error = '';
    loading = true;
    try {
      const user = await auth.login(email.trim(), password);
      toasts.success(`Bienvenido/a, ${user.full_name || user.email}`);
      const params = new URLSearchParams(window.location.search);
      const redirect = params.get('redirect');
      const safeTarget =
        redirect && redirect.startsWith('/') && !redirect.startsWith('/login')
          ? redirect
          : '/supplier-catalog';
      navigateTo(safeTarget, { replace: true });
    } catch (err) {
      error = err?.message || 'Credenciales inválidas. Verificá tu correo y contraseña.';
    } finally {
      loading = false;
    }
  }
</script>

<section class="login-shell">
  <div class="login-card">
    <div class="login-brand">
      <img src="/logo-lc.jpg" alt="Librería y Papelería L&C" width="84" height="84" class="login-logo" />
      <h1>Librería y Papelería L&amp;C</h1>
      <p>Sistema de Gestión de Listas de Precios, Stock y Ventas</p>
    </div>

    <form class="login-form" onsubmit={handleSubmit}>
      <label class="field">
        <span>Correo electrónico</span>
        <input
          type="email"
          name="email"
          autocomplete="email"
          placeholder="admin@librerialc.com.ar"
          bind:value={email}
          required
        />
      </label>

      <label class="field">
        <span>Contraseña</span>
        <input
          type="password"
          name="password"
          autocomplete="current-password"
          placeholder="••••••••"
          bind:value={password}
          required
        />
      </label>

      {#if error}
        <div class="login-error" role="alert">{error}</div>
      {/if}

      <div class="login-actions">
        <Button type="submit" variant="primary" disabled={loading}>
          {loading ? 'Ingresando...' : 'Iniciar sesión'}
        </Button>
      </div>
    </form>
  </div>
</section>

<style>
  .login-shell {
    min-height: calc(100vh - 5rem);
    display: grid;
    place-items: center;
    padding: 1.5rem 1rem;
  }

  .login-card {
    width: min(100%, 420px);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-top: 4px solid var(--color-brand-primary);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .login-brand {
    padding: 1.6rem 1.5rem 1.2rem;
    text-align: center;
    background-color: var(--color-surface-muted);
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .login-logo {
    border-radius: var(--radius-md);
    border: 2px solid var(--color-inventory-cardboard);
    background: #ffffff;
    margin-bottom: 0.75rem;
  }

  .login-brand h1 {
    margin: 0 0 0.3rem;
    font-size: 1.22rem;
    color: var(--color-text-primary);
  }

  .login-brand p {
    margin: 0;
    font-size: 0.88rem;
    color: var(--color-text-secondary);
  }

  .login-form {
    display: grid;
    gap: 1rem;
    padding: 1.4rem 1.5rem 1.6rem;
  }

  .field {
    display: grid;
    gap: 0.38rem;
  }

  .field span {
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .field input {
    width: 100%;
    padding: 0.58rem 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    color: var(--color-text-primary);
  }

  .login-error {
    padding: 0.65rem 0.8rem;
    border-radius: var(--radius-sm);
    background: var(--color-danger-bg);
    border: 1px solid var(--color-danger-border);
    color: var(--color-danger-text);
    font-size: 0.88rem;
    font-weight: 500;
  }

  .login-actions :global(.lc-btn) {
    width: 100%;
    padding: 0.65rem 1rem;
  }
</style>
