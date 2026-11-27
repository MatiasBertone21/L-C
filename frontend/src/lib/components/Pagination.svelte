<script>
  import { formatInt } from '../utils/format.js';
  import Button from './Button.svelte';

  let {
    page = 1,
    pageSize = 50,
    total = 0,
    totalPages = 1,
    onPageChange = undefined,
  } = $props();

  let fromItem = $derived(total === 0 ? 0 : (page - 1) * pageSize + 1);
  let toItem = $derived(Math.min(page * pageSize, total));
</script>

<div class="lc-pagination">
  <span class="lc-pagination__summary">
    {#if total > 0}
      Mostrando <strong>{formatInt(fromItem)}–{formatInt(toItem)}</strong> de <strong>{formatInt(total)}</strong>
    {:else}
      Sin resultados
    {/if}
  </span>

  <div class="lc-pagination__controls">
    <Button
      variant="secondary"
      size="sm"
      disabled={page <= 1}
      onclick={() => onPageChange?.(page - 1)}
    >
      ‹ Anterior
    </Button>
    <span class="lc-pagination__page mono-num">
      Página {formatInt(page)} de {formatInt(Math.max(totalPages, 1))}
    </span>
    <Button
      variant="secondary"
      size="sm"
      disabled={page >= totalPages}
      onclick={() => onPageChange?.(page + 1)}
    >
      Siguiente ›
    </Button>
  </div>
</div>

<style>
  .lc-pagination {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.7rem 0.2rem;
    color: var(--color-text-secondary);
    font-size: 0.88rem;
  }

  .lc-pagination__controls {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  .lc-pagination__page {
    font-size: 0.86rem;
    color: var(--color-text-primary);
  }
</style>
