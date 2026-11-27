<script>
  let { variant = 'neutral', title = undefined, children } = $props();
</script>

<span class="lc-badge lc-badge--{variant}" {title}>
  {@render children?.()}
</span>

<style>
  .lc-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.14rem 0.48rem;
    border-radius: var(--radius-sm);
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.3;
    border: 1px solid transparent;
    white-space: nowrap;
  }

  .lc-badge--neutral {
    background-color: var(--color-surface-muted);
    color: var(--color-text-secondary);
    border-color: var(--color-border-subtle);
  }

  .lc-badge--brand {
    background-color: var(--color-brand-soft-bg);
    color: var(--color-brand-soft-text);
    border-color: #b7e2ce;
  }

  .lc-badge--kraft {
    background-color: var(--color-inventory-kraft-bg);
    color: var(--color-inventory-text);
    border-color: var(--color-inventory-cardboard);
  }

  .lc-badge--warning {
    background-color: var(--color-warning-bg);
    color: var(--color-warning-text);
    border-color: var(--color-warning-border);
  }

  .lc-badge--danger {
    background-color: var(--color-danger-bg);
    color: var(--color-danger-text);
    border-color: var(--color-danger-border);
  }

  .lc-badge--caution {
    background-color: var(--color-caution-bg);
    color: var(--color-caution-text);
    border-color: var(--color-caution-border);
  }

  .lc-badge--info {
    background-color: var(--color-accent-blue-soft);
    color: var(--color-accent-blue);
    border-color: #93c5fd;
  }
</style>
