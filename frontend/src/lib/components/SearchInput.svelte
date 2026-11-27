<script>
  let {
    value = $bindable(''),
    placeholder = 'Buscar por código o descripción...',
    debounceMs = 300,
    onSearch = undefined,
    ariaLabel = 'Buscar',
  } = $props();

  let timer = null;

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function handleInput(event) {
    value = event.currentTarget.value;
    clearTimer();
    timer = setTimeout(() => {
      onSearch?.(value.trim());
    }, debounceMs);
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      clearTimer();
      onSearch?.(value.trim());
    } else if (event.key === 'Escape' && value) {
      event.preventDefault();
      clearTimer();
      value = '';
      onSearch?.('');
    }
  }

  function handleClear() {
    clearTimer();
    value = '';
    onSearch?.('');
  }
</script>

<div class="search-box">
  <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <circle cx="11" cy="11" r="8"></circle>
    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
  </svg>
  <input
    type="search"
    {value}
    {placeholder}
    aria-label={ariaLabel}
    oninput={handleInput}
    onkeydown={handleKeyDown}
  />
  {#if value}
    <button type="button" class="clear-btn" onclick={handleClear} title="Limpiar búsqueda (Esc)">
      ✕
    </button>
  {/if}
</div>

<style>
  .search-box {
    position: relative;
    display: flex;
    align-items: center;
    min-width: 240px;
    flex: 1 1 260px;
  }

  .search-icon {
    position: absolute;
    left: 0.7rem;
    color: var(--color-text-muted);
    pointer-events: none;
  }

  input {
    width: 100%;
    padding: 0.48rem 2rem 0.48rem 2.15rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-surface);
    color: var(--color-text-primary);
  }

  .clear-btn {
    position: absolute;
    right: 0.4rem;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.8rem;
  }

  .clear-btn:hover {
    background-color: var(--color-surface-muted);
    color: var(--color-text-primary);
  }
</style>
