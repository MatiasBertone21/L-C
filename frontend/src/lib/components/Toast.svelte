<script>
  import { toasts } from '../stores/toast.svelte.js';
</script>

{#if toasts.items.length > 0}
  <div class="lc-toast-stack" aria-live="polite">
    {#each toasts.items as item (item.id)}
      <div class="lc-toast lc-toast--{item.variant}" role="status">
        <span>{item.message}</span>
        <button type="button" onclick={() => toasts.dismiss(item.id)} aria-label="Cerrar notificación">
          ✕
        </button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .lc-toast-stack {
    position: fixed;
    right: 1rem;
    bottom: 1rem;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-width: min(420px, calc(100vw - 2rem));
  }

  .lc-toast {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.7rem 0.9rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text-primary);
    font-size: 0.9rem;
    font-weight: 500;
  }

  .lc-toast--success {
    background: var(--color-brand-soft-bg);
    color: var(--color-brand-soft-text);
    border-color: var(--color-brand-primary);
  }

  .lc-toast--danger {
    background: var(--color-danger-bg);
    color: var(--color-danger-text);
    border-color: var(--color-danger-border);
  }

  .lc-toast--warning {
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
    border-color: var(--color-warning-border);
  }

  .lc-toast button {
    border: none;
    background: transparent;
    color: inherit;
    cursor: pointer;
    padding: 0 0.25rem;
    font-size: 0.85rem;
  }
</style>
