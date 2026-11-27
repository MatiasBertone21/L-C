<script>
  import Modal from '../Modal.svelte';
  import Button from '../Button.svelte';
  import Badge from '../Badge.svelte';
  import { uploadSupplierPriceList } from '../../api/supplierCatalog.js';
  import { formatInt } from '../../utils/format.js';
  import { toasts } from '../../stores/toast.svelte.js';

  let {
    open = $bindable(false),
    onUploaded = undefined,
    onOpenDiff = undefined,
  } = $props();

  let selectedFile = $state(null);
  let forceIncomplete = $state(false);
  let loading = $state(false);
  let errorMsg = $state('');
  let resultSummary = $state(null);

  function resetState() {
    selectedFile = null;
    forceIncomplete = false;
    loading = false;
    errorMsg = '';
    resultSummary = null;
  }

  function handleFileChange(event) {
    const file = event.currentTarget.files?.[0] || null;
    selectedFile = file;
    errorMsg = '';
    resultSummary = null;
  }

  async function handleUpload() {
    if (!selectedFile) {
      errorMsg = 'Seleccioná un archivo .xls, .xlsx o .csv del proveedor.';
      return;
    }
    loading = true;
    errorMsg = '';
    try {
      const summary = await uploadSupplierPriceList(selectedFile, { force: forceIncomplete });
      resultSummary = summary;
      toasts.success(summary.message || 'Lista procesada correctamente.');
      onUploaded?.(summary);
    } catch (err) {
      errorMsg = err?.message || 'No se pudo procesar el archivo subido.';
    } finally {
      loading = false;
    }
  }

  function handleClose() {
    open = false;
    resetState();
  }

  function handleGoToDiff() {
    const impId = resultSummary?.id;
    handleClose();
    onOpenDiff?.(impId);
  }
</script>

<Modal bind:open title="Subir lista de precios del día" maxWidth="580px" onClose={resetState}>
  {#if !resultSummary}
    <div class="upload-body">
      <p class="upload-hint">
        Seleccioná el archivo descargado del proveedor (<strong>.xls</strong>, <strong>.xlsx</strong> o <strong>.csv</strong>).
        El sistema normalizará los datos, actualizará los artículos que variaron de precio y validará con fecha de hoy los que se mantienen iguales.
      </p>

      <label class="file-drop">
        <span class="file-drop__title">Archivo de lista mayorista</span>
        <input
          type="file"
          accept=".xls,.xlsx,.csv"
          onchange={handleFileChange}
          disabled={loading}
        />
        {#if selectedFile}
          <span class="file-drop__selected mono-num">
            {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
          </span>
        {/if}
      </label>

      <label class="force-check">
        <input type="checkbox" bind:checked={forceIncomplete} disabled={loading} />
        <span>Forzar carga aunque traiga muchos menos artículos que el catálogo actual</span>
      </label>

      {#if errorMsg}
        <div class="upload-alert" role="alert">{errorMsg}</div>
      {/if}

      {#if loading}
        <div class="upload-progress">
          Procesando planilla y comparando contra el catálogo maestro... aguardá unos segundos.
        </div>
      {/if}
    </div>
  {:else}
    <div class="summary-box">
      <div class="summary-head">
        <Badge variant="brand">
          {resultSummary.mode === 'quick_validation'
            ? 'Validación rápida sin cambios'
            : resultSummary.mode === 'baseline'
              ? 'Carga inicial'
              : `Lista #${resultSummary.sequence_in_day} del día`}
        </Badge>
        <span class="mono-num summary-time">{(resultSummary.duration_ms / 1000).toFixed(2)} s</span>
      </div>

      <p class="summary-msg">{resultSummary.message}</p>

      <div class="summary-grid">
        <div class="stat-item">
          <span class="stat-label">Artículos leídos</span>
          <strong class="mono-num">{formatInt(resultSummary.total_items)}</strong>
        </div>
        <div class="stat-item stat-up">
          <span class="stat-label">▲ Subieron</span>
          <strong class="mono-num">{formatInt(resultSummary.price_up_count)}</strong>
        </div>
        <div class="stat-item stat-down">
          <span class="stat-label">▼ Bajaron</span>
          <strong class="mono-num">{formatInt(resultSummary.price_down_count)}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">Validados sin cambio</span>
          <strong class="mono-num">{formatInt(resultSummary.unchanged_count)}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">✚ Nuevos / Reactiv.</span>
          <strong class="mono-num">{formatInt(resultSummary.new_count)}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">✖ Discontinuados</span>
          <strong class="mono-num">{formatInt(resultSummary.discontinued_count)}</strong>
        </div>
      </div>
    </div>
  {/if}

  {#snippet footer()}
    {#if !resultSummary}
      <Button variant="secondary" onclick={handleClose} disabled={loading}>Cancelar</Button>
      <Button variant="primary" onclick={handleUpload} disabled={loading || !selectedFile}>
        {loading ? 'Procesando...' : 'Procesar lista'}
      </Button>
    {:else}
      <Button variant="secondary" onclick={handleClose}>Cerrar</Button>
      {#if resultSummary.changed_count > 0 || resultSummary.new_count > 0 || resultSummary.discontinued_count > 0}
        <Button variant="primary" onclick={handleGoToDiff}>Ver variaciones en Precios Diff</Button>
      {/if}
    {/if}
  {/snippet}
</Modal>

<style>
  .upload-body {
    display: grid;
    gap: 1rem;
  }

  .upload-hint {
    margin: 0;
    color: var(--color-text-secondary);
    font-size: 0.9rem;
  }

  .file-drop {
    display: grid;
    gap: 0.5rem;
    padding: 1rem;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-surface-muted);
  }

  .file-drop__title {
    font-weight: 600;
    font-size: 0.88rem;
  }

  .file-drop__selected {
    font-size: 0.84rem;
    color: var(--color-brand-soft-text);
    font-weight: 600;
  }

  .force-check {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
  }

  .upload-alert {
    padding: 0.7rem 0.85rem;
    border-radius: var(--radius-sm);
    background: var(--color-danger-bg);
    border: 1px solid var(--color-danger-border);
    color: var(--color-danger-text);
    font-size: 0.88rem;
  }

  .upload-progress {
    padding: 0.7rem 0.85rem;
    border-radius: var(--radius-sm);
    background: var(--color-accent-blue-soft);
    color: var(--color-accent-blue);
    font-size: 0.88rem;
    font-weight: 600;
  }

  .summary-box {
    display: grid;
    gap: 0.9rem;
  }

  .summary-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .summary-time {
    font-size: 0.82rem;
    color: var(--color-text-muted);
  }

  .summary-msg {
    margin: 0;
    font-size: 0.94rem;
    font-weight: 500;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.65rem;
  }

  .stat-item {
    padding: 0.65rem 0.75rem;
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-sm);
    background: var(--color-surface-muted);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .stat-label {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .stat-item strong {
    font-size: 1.08rem;
  }

  .stat-up strong {
    color: var(--color-danger-text);
  }

  .stat-down strong {
    color: var(--color-brand-primary);
  }
</style>
