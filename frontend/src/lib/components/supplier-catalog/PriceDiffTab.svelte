<script>
  import Badge from '../Badge.svelte';
  import SearchInput from '../SearchInput.svelte';
  import Pagination from '../Pagination.svelte';
  import {
    fetchPriceChanges,
    fetchPriceChangesSummary,
    fetchSupplierImports,
  } from '../../api/supplierCatalog.js';
  import {
    formatARS,
    formatInt,
    formatPct,
    formatShortDate,
  } from '../../utils/format.js';
  import { toasts } from '../../stores/toast.svelte.js';

  let {
    initialImportId = null,
    hasLinkedStock = false,
    onOpenItemDetail = undefined,
  } = $props();

  let periodMode = $state('latest'); // latest | import | today | last_7_days | last_30_days | custom
  let selectedImportId = $state('');
  let dateFrom = $state('');
  let dateTo = $state('');
  let onlyMyStock = $state(false);
  let activeChangeType = $state(''); // '' | price_up | price_down | new | discontinued
  let minPct = $state('');
  let searchQuery = $state('');
  let sortOrder = $state('-abs_diff_pct');
  let page = $state(1);
  const pageSize = 50;

  let recentImports = $state([]);
  let items = $state([]);
  let total = $state(0);
  let totalPages = $state(1);
  let summary = $state({
    price_up: 0,
    price_down: 0,
    new: 0,
    discontinued: 0,
    total: 0,
    in_my_stock_changed: 0,
    period_label: '',
  });
  let loading = $state(false);

  let activeAbort = null;

  $effect(() => {
    if (initialImportId) {
      periodMode = 'import';
      selectedImportId = initialImportId;
    }
  });

  $effect(() => {
    loadRecentImports();
    if (hasLinkedStock) {
      onlyMyStock = true;
    }
  });

  $effect(() => {
    // Reactividad explícita ante cambios de filtros
    void periodMode;
    void selectedImportId;
    void dateFrom;
    void dateTo;
    void onlyMyStock;
    void activeChangeType;
    void minPct;
    void searchQuery;
    void sortOrder;
    loadDiffData(1);
  });

  async function loadRecentImports() {
    try {
      const resp = await fetchSupplierImports({ page: 1, page_size: 25, status: 'completed' });
      recentImports = resp.items;
    } catch {
      recentImports = [];
    }
  }

  function buildPeriodParams() {
    const p = {};
    if (periodMode === 'import' && selectedImportId) {
      p.import_id = selectedImportId;
    } else if (periodMode === 'today' || periodMode === 'last_7_days' || periodMode === 'last_30_days') {
      p.preset = periodMode;
    } else if (periodMode === 'custom') {
      if (dateFrom) p.date_from = dateFrom;
      if (dateTo) p.date_to = dateTo;
    } else {
      p.preset = 'latest';
    }
    if (onlyMyStock) p.only_my_stock = true;
    if (minPct !== '' && Number(minPct) > 0) p.min_pct = Number(minPct);
    if (searchQuery) p.q = searchQuery;
    return p;
  }

  async function loadDiffData(targetPage = 1) {
    if (periodMode === 'custom' && dateFrom && dateTo && dateFrom > dateTo) {
      return;
    }
    if (activeAbort) {
      activeAbort.abort();
    }
    const controller = new AbortController();
    activeAbort = controller;
    loading = true;

    const baseParams = buildPeriodParams();
    const listParams = {
      ...baseParams,
      page: targetPage,
      page_size: pageSize,
      sort: sortOrder,
    };
    if (activeChangeType) {
      listParams.change_type = [activeChangeType];
    }

    try {
      const [sumResp, listResp] = await Promise.all([
        fetchPriceChangesSummary(baseParams, { signal: controller.signal }),
        fetchPriceChanges(listParams, { signal: controller.signal }),
      ]);
      summary = sumResp;
      items = listResp.items;
      page = listResp.page;
      total = listResp.total;
      totalPages = listResp.total_pages;
    } catch (err) {
      if (err?.name !== 'AbortError') {
        toasts.error(err?.message || 'No se pudieron consultar las variaciones de precios.');
      }
    } finally {
      if (activeAbort === controller) {
        loading = false;
      }
    }
  }

  function toggleTypeKpi(type) {
    activeChangeType = activeChangeType === type ? '' : type;
  }
</script>

<div class="diff-panel">
  <div class="period-bar">
    <div class="period-tabs" role="group" aria-label="Período de comparación">
      <button
        type="button"
        class:active={periodMode === 'latest'}
        onclick={() => (periodMode = 'latest')}
      >
        Última carga
      </button>
      <button
        type="button"
        class:active={periodMode === 'today'}
        onclick={() => (periodMode = 'today')}
      >
        Hoy
      </button>
      <button
        type="button"
        class:active={periodMode === 'last_7_days'}
        onclick={() => (periodMode = 'last_7_days')}
      >
        Últ. 7 días
      </button>
      <button
        type="button"
        class:active={periodMode === 'last_30_days'}
        onclick={() => (periodMode = 'last_30_days')}
      >
        Últ. 30 días
      </button>
      <button
        type="button"
        class:active={periodMode === 'custom'}
        onclick={() => (periodMode = 'custom')}
      >
        Rango fechas
      </button>
    </div>

    {#if recentImports.length > 0}
      <label class="import-picker">
        <span>Carga puntual:</span>
        <select
          value={periodMode === 'import' ? selectedImportId : ''}
          onchange={(e) => {
            const val = e.currentTarget.value;
            if (val) {
              selectedImportId = val;
              periodMode = 'import';
            } else {
              periodMode = 'latest';
            }
          }}
        >
          <option value="">— Última carga vigente —</option>
          {#each recentImports as imp (imp.id)}
            <option value={imp.id}>
              {formatShortDate(imp.import_date)} (#{imp.sequence_in_day}) · {imp.original_filename}
            </option>
          {/each}
        </select>
      </label>
    {/if}
  </div>

  {#if periodMode === 'custom'}
    <div class="custom-dates">
      <label>
        <span>Desde:</span>
        <input type="date" bind:value={dateFrom} />
      </label>
      <label>
        <span>Hasta:</span>
        <input type="date" bind:value={dateTo} />
      </label>
    </div>
  {/if}

  <div class="kpi-row">
    <button
      type="button"
      class="kpi-card kpi-up"
      class:selected={activeChangeType === 'price_up'}
      onclick={() => toggleTypeKpi('price_up')}
    >
      <span class="kpi-label">▲ Subieron</span>
      <strong class="mono-num">{formatInt(summary.price_up)}</strong>
    </button>

    <button
      type="button"
      class="kpi-card kpi-down"
      class:selected={activeChangeType === 'price_down'}
      onclick={() => toggleTypeKpi('price_down')}
    >
      <span class="kpi-label">▼ Bajaron</span>
      <strong class="mono-num">{formatInt(summary.price_down)}</strong>
    </button>

    <button
      type="button"
      class="kpi-card kpi-new"
      class:selected={activeChangeType === 'new'}
      onclick={() => toggleTypeKpi('new')}
    >
      <span class="kpi-label">✚ Nuevos</span>
      <strong class="mono-num">{formatInt(summary.new)}</strong>
    </button>

    <button
      type="button"
      class="kpi-card kpi-disc"
      class:selected={activeChangeType === 'discontinued'}
      onclick={() => toggleTypeKpi('discontinued')}
    >
      <span class="kpi-label">✖ Quitados</span>
      <strong class="mono-num">{formatInt(summary.discontinued)}</strong>
    </button>

    <label class="my-stock-toggle">
      <input type="checkbox" bind:checked={onlyMyStock} />
      <span>
        Solo productos en mi stock
        <strong class="mono-num">({formatInt(summary.in_my_stock_changed)})</strong>
      </span>
    </label>
  </div>

  <div class="filters-bar">
    <SearchInput
      placeholder="Filtrar variación por código o descripción..."
      onSearch={(q) => (searchQuery = q)}
    />

    <label class="inline-filter">
      <span>Tipo:</span>
      <select bind:value={activeChangeType}>
        <option value="">Todos ({formatInt(summary.total)})</option>
        <option value="price_up">▲ Subieron</option>
        <option value="price_down">▼ Bajaron</option>
        <option value="new">✚ Nuevos</option>
        <option value="discontinued">✖ Quitados</option>
      </select>
    </label>

    <label class="inline-filter">
      <span>% mín.:</span>
      <input
        type="number"
        min="0"
        step="0.5"
        placeholder="0"
        class="pct-input mono-num"
        bind:value={minPct}
      />
    </label>

    <label class="inline-filter">
      <span>Orden:</span>
      <select bind:value={sortOrder}>
        <option value="-abs_diff_pct">Mayor impacto %</option>
        <option value="-diff_pct">Mayor suba %</option>
        <option value="diff_pct">Mayor baja %</option>
        <option value="-created_at">Más recientes</option>
        <option value="code">Código</option>
      </select>
    </label>
  </div>

  {#if loading}
    <div class="state-box">Consultando variaciones de precios...</div>
  {:else if items.length === 0}
    <div class="state-box">
      No se registran variaciones de precios para los filtros seleccionados
      {#if summary.period_label}({summary.period_label}){/if}.
    </div>
  {:else}
    <div class="lc-table-wrap">
      <table class="lc-table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Descripción</th>
            <th>Cambio</th>
            <th class="align-right">$ C/IVA Anterior</th>
            <th class="align-right">$ C/IVA Nuevo</th>
            <th class="align-right">Dif. $</th>
            <th class="align-right">Dif. %</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {#each items as row (row.id)}
            <tr class="clickable-row" onclick={() => onOpenItemDetail?.(row.code)}>
              <td class="mono-num"><strong>{row.code}</strong></td>
              <td>
                <div class="desc-text">{row.description_snapshot}</div>
                <div class="sub-badges">
                  <Badge variant="kraft">{row.packaging_snapshot}</Badge>
                  {#if row.in_my_stock}
                    <Badge variant="brand">
                      En mi stock · Mi venta: {formatARS(row.my_sale_price)}
                    </Badge>
                  {/if}
                </div>
              </td>
              <td>
                {#if row.change_type === 'price_up'}
                  <Badge variant="danger">▲ Subió</Badge>
                {:else if row.change_type === 'price_down'}
                  <Badge variant="brand">▼ Bajó</Badge>
                {:else if row.change_type === 'new'}
                  <Badge variant="info">{row.is_reactivation ? '✚ Reactivado' : '✚ Nuevo'}</Badge>
                {:else}
                  <Badge variant="neutral">✖ Quitado</Badge>
                {/if}
              </td>
              <td class="align-right mono-num">{formatARS(row.old_price_with_vat)}</td>
              <td class="align-right mono-num"><strong>{formatARS(row.new_price_with_vat)}</strong></td>
              <td
                class="align-right mono-num"
                class:text-up={row.change_type === 'price_up'}
                class:text-down={row.change_type === 'price_down'}
              >
                {row.diff_amount !== null && row.diff_amount !== undefined
                  ? `${row.diff_amount > 0 ? '+' : ''}${formatARS(row.diff_amount)}`
                  : '—'}
              </td>
              <td
                class="align-right mono-num"
                class:text-up={row.change_type === 'price_up'}
                class:text-down={row.change_type === 'price_down'}
              >
                <strong>{formatPct(row.diff_pct)}</strong>
              </td>
              <td class="mono-num">{formatShortDate(row.import_date)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <Pagination {page} {pageSize} {total} {totalPages} onPageChange={(p) => loadDiffData(p)} />
  {/if}
</div>

<style>
  .diff-panel {
    display: grid;
    gap: 0.9rem;
  }

  .period-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .period-tabs {
    display: inline-flex;
    flex-wrap: wrap;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    overflow: hidden;
  }

  .period-tabs button {
    border: none;
    border-right: 1px solid var(--color-border-subtle);
    background: transparent;
    padding: 0.45rem 0.8rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .period-tabs button:last-child {
    border-right: none;
  }

  .period-tabs button.active {
    background: var(--color-brand-primary);
    color: #ffffff;
  }

  .import-picker {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
  }

  .import-picker select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    max-width: 290px;
  }

  .custom-dates {
    display: flex;
    flex-wrap: wrap;
    gap: 0.85rem;
    padding: 0.65rem 0.85rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    font-size: 0.86rem;
  }

  .custom-dates label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-weight: 600;
  }

  .custom-dates input {
    padding: 0.35rem 0.55rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }

  .kpi-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(110px, 1fr)) auto;
    gap: 0.65rem;
    align-items: stretch;
  }

  .kpi-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.2rem;
    padding: 0.7rem 0.85rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    cursor: pointer;
    text-align: left;
  }

  .kpi-card.selected {
    outline: 2px solid var(--color-accent-blue);
  }

  .kpi-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  .kpi-card strong {
    font-size: 1.25rem;
  }

  .kpi-up strong {
    color: var(--color-danger-text);
  }

  .kpi-down strong {
    color: var(--color-brand-primary);
  }

  .kpi-new strong {
    color: var(--color-accent-blue);
  }

  .my-stock-toggle {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.7rem 1rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-brand-primary);
    background: var(--color-brand-soft-bg);
    color: var(--color-brand-soft-text);
    font-weight: 600;
    font-size: 0.88rem;
    cursor: pointer;
  }

  .filters-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.65rem;
    padding: 0.75rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .inline-filter {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  .inline-filter select,
  .pct-input {
    padding: 0.44rem 0.55rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    color: var(--color-text-primary);
  }

  .pct-input {
    width: 76px;
  }

  .state-box {
    padding: 2rem 1rem;
    text-align: center;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    color: var(--color-text-secondary);
  }

  .clickable-row {
    cursor: pointer;
  }

  .desc-text {
    font-weight: 600;
    margin-bottom: 0.22rem;
  }

  .sub-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }

  .text-up {
    color: var(--color-danger-text);
  }

  .text-down {
    color: var(--color-brand-primary);
  }

  @media (max-width: 900px) {
    .kpi-row {
      grid-template-columns: repeat(2, 1fr);
    }

    .my-stock-toggle {
      grid-column: 1 / -1;
    }
  }
</style>
