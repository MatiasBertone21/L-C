<script>
  let {
    type = 'button',
    variant = 'primary',
    size = 'md',
    disabled = false,
    onclick = undefined,
    title = undefined,
    children,
  } = $props();
</script>

<button
  {type}
  {disabled}
  {title}
  class="lc-btn lc-btn--{variant} lc-btn--{size}"
  {onclick}
>
  {@render children?.()}
</button>

<style>
  .lc-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    line-height: 1.2;
  }

  .lc-btn--sm {
    padding: 0.35rem 0.65rem;
    font-size: 0.84rem;
  }

  .lc-btn--md {
    padding: 0.52rem 0.95rem;
    font-size: 0.92rem;
  }

  .lc-btn--primary {
    background-color: var(--color-brand-primary);
    color: #ffffff;
  }

  .lc-btn--primary:hover:not(:disabled) {
    background-color: var(--color-brand-primary-hover);
  }

  .lc-btn--primary:active:not(:disabled) {
    background-color: var(--color-brand-primary-active);
  }

  .lc-btn--secondary {
    background-color: var(--color-surface);
    color: var(--color-text-primary);
    border-color: var(--color-border);
  }

  .lc-btn--secondary:hover:not(:disabled) {
    background-color: var(--color-surface-muted);
  }

  .lc-btn--danger {
    background-color: var(--color-danger-solid);
    color: #ffffff;
  }

  .lc-btn--danger:hover:not(:disabled) {
    background-color: var(--color-danger-solid-hover);
  }

  .lc-btn--ghost {
    background-color: transparent;
    color: var(--color-text-secondary);
  }

  .lc-btn--ghost:hover:not(:disabled) {
    background-color: var(--color-surface-muted);
    color: var(--color-text-primary);
  }

  .lc-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
</style>
