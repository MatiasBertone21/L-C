<script>
  let {
    open = $bindable(false),
    title = '',
    maxWidth = '640px',
    onClose = undefined,
    children,
    footer = undefined,
  } = $props();

  let dialogEl = $state(null);

  $effect(() => {
    if (!dialogEl) return;
    if (open && !dialogEl.open) {
      dialogEl.showModal();
    } else if (!open && dialogEl.open) {
      dialogEl.close();
    }
  });

  function closeModal() {
    open = false;
    onClose?.();
  }

  function handleDialogClose() {
    if (open) {
      open = false;
      onClose?.();
    }
  }

  function handleBackdropClick(event) {
    if (event.target === dialogEl) {
      closeModal();
    }
  }
</script>

<dialog
  bind:this={dialogEl}
  class="lc-dialog"
  style="--modal-max-width: {maxWidth}"
  onclose={handleDialogClose}
  onclick={handleBackdropClick}
>
  {#if open}
    <div class="lc-dialog__panel">
      <header class="lc-dialog__header">
        <h2>{title}</h2>
        <button type="button" class="lc-dialog__close" onclick={closeModal} aria-label="Cerrar ventana">
          ✕
        </button>
      </header>
      <div class="lc-dialog__body">
        {@render children?.()}
      </div>
      {#if footer}
        <footer class="lc-dialog__footer">
          {@render footer()}
        </footer>
      {/if}
    </div>
  {/if}
</dialog>

<style>
  .lc-dialog {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: 0;
    width: min(94vw, var(--modal-max-width, 640px));
    max-height: 90vh;
    background: var(--color-surface);
    color: var(--color-text-primary);
  }

  .lc-dialog::backdrop {
    background: rgba(15, 23, 42, 0.48);
  }

  .lc-dialog__panel {
    display: flex;
    flex-direction: column;
    max-height: 88vh;
  }

  .lc-dialog__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.95rem 1.2rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background-color: var(--color-surface-muted);
  }

  .lc-dialog__header h2 {
    margin: 0;
    font-size: 1.05rem;
    color: var(--color-text-primary);
  }

  .lc-dialog__close {
    border: none;
    background: transparent;
    color: var(--color-text-secondary);
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-sm);
    font-size: 1rem;
  }

  .lc-dialog__close:hover {
    background-color: var(--color-border-subtle);
    color: var(--color-text-primary);
  }

  .lc-dialog__body {
    padding: 1.15rem 1.2rem;
    overflow-y: auto;
  }

  .lc-dialog__footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.65rem;
    padding: 0.85rem 1.2rem;
    border-top: 1px solid var(--color-border-subtle);
    background-color: var(--color-surface-muted);
  }
</style>
