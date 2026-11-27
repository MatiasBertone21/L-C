<script>
  import { onMount } from 'svelte';
  import Button from '../lib/components/Button.svelte';
  import Badge from '../lib/components/Badge.svelte';
  import SearchInput from '../lib/components/SearchInput.svelte';
  import Pagination from '../lib/components/Pagination.svelte';
  import Modal from '../lib/components/Modal.svelte';
  import UploadPriceListModal from '../lib/components/supplier-catalog/UploadPriceListModal.svelte';
  import ImportHistoryModal from '../lib/components/supplier-catalog/ImportHistoryModal.svelte';
  import CatalogItemDetailModal from '../lib/components/supplier-catalog/CatalogItemDetailModal.svelte';
  import LoadToStockModal from '../lib/components/supplier-catalog/LoadToStockModal.svelte';
  import PriceDiffTab from '../lib/components/supplier-catalog/PriceDiffTab.svelte';
  import {
    fetchCatalogFilters,
    fetchCatalogItems,
    fetchLatestImportStatus,
    purgeDiscontinuedCatalogItems,
  } from '../lib/api/supplierCatalog.js';
  import {
    formatARS,
    formatDateTime,
    formatInt,
    formatPct,
    formatRelativeDay,
    formatShortDate,
  } from '../lib/utils/format.js';
  import { auth } from '../lib/stores/auth.svelte.js';
  import { toasts } from '../lib/stores/toast.svelte.js';

  let activeTab = $state('catalog'); // 'catalog' | 'diff'
  let diffTargetImportId = $state(null);

  // Estado de cabecera y contadores globales
  let latestStatus = $state({
    latest_import: null,
    active_catalog_count: 0,
    discontinued_catalog_count: 0,
    discontinued_alert: false,
    discontinued_threshold: 100,
    in_my_stock_count: 0,
  });
  let packagingOptions = $state([]);

  // Filtros de Tab 1 (Catálogo)
  let searchQ = $state('');
  let filterPackaging = $state('');
  let filterStatus = $state('active'); // active | discontinued | all
  let filterLiquidation = $state(false);
  let filterStockStatus = $state('all'); // all | in_stock | not_in_stock
  let filterChangedDays = $state(''); // '' | '0' | '7' | '30'
  let sortBy = $state('description');
  let page = $state(1);
  const pageSize = 50;

  let catalogItems = $state([]);
  let totalItems = $state(0);
  let totalPages = $state(1);
  let loadingCatalog = $state(false);

  // Selección múltiple para cargar al stock propio
  let selectedMap = $state({}); // { [code]: itemSnapshot }
  let selectedList = $derived(Object.values(selectedMap));

  // Modales
  let uploadModalOpen = $state(false);
  let historyModalOpen = $state(false);
  let detailModalOpen = $state(false);
  let detailItemCode = $state(null);
  let loadStockModalOpen = $state(false);
  let loadStockItems = $state([]);
  let purgeConfirmOpen = $state(false);
  let purging = $state(false);

  let catalogAbort = null;

  onMount(async () => {
    await refreshGlobalStatusAndFilters();
  });

  $effect(() => {
    if (activeTab !== 'catalog') return;
    void searchQ;
    void filterPackaging;
    void filterStatus;
    void filterLiquidation;
    void filterStockStatus;
    void filterChangedDays;
    void sortBy;
    loadCatalogPage(1);
  });

  async function refreshGlobalStatusAndFilters() {
    try {
      const [st, flt] = await Promise.all([fetchLatestImportStatus(), fetchCatalogFilters()]);
      latestStatus = st;
      packagingOptions = flt.packagings || [];
    } catch (err) {
      toasts.error(err?.message || 'No se pudo obtener el estado del catálogo.');
    }
  }

  async function loadCatalogPage(targetPage = 1) {
    if (catalogAbort) {
      catalogAbort.abort();
    }
    const controller = new AbortController();
    catalogAbort = controller;
    loadingCatalog = true;

    const params = {
      page: targetPage,
      page_size: pageSize,
      status: filterStatus,
      stock_status: filterStockStatus,
      sort: sortBy,
    };
    if (searchQ) params.q = searchQ;
    if (filterPackaging) params.packaging = filterPackaging;
    if (filterLiquidation) params.is_liquidation = true;
    if (filterChangedDays !== '') params.changed_within_days = Number(filterChangedDays);

    try {
      const resp = await fetchCatalogItems(params, { signal: controller.signal });
      catalogItems = resp.items;
      page = resp.page;
      totalItems = resp.total;
      totalPages = resp.total_pages;
    } catch (err) {
      if (err?.name !== 'AbortError') {
        toasts.error(err?.message || 'Error al cargar los artículos del catálogo.');
      }
    } finally {
      if (catalogAbort === controller) {
        loadingCatalog = false;
      }
    }
  }

  function toggleRowSelection(item, event) {
    event.stopPropagation();
    if (item.linked_product_id) return;
    const next = { ...selectedMap };
    if (next[item.code]) {
      delete next[item.code];
    } else {
      next[item.code] = item;
    }
    selectedMap = next;
  }

  function clearSelection() {
    selectedMap = {};
  }

  function openLoadStockModalFor(itemsArray) {
    loadStockItems = itemsArray;
    loadStockModalOpen = true;
  }

  function openDetail(code) {
    detailItemCode = code;
    detailModalOpen = true;
  }

  async function handleAfterMutation() {
    clearSelection();
    await refreshGlobalStatusAndFilters();
    if (activeTab === 'catalog') {
      await loadCatalogPage(page);
    }
  }

  async function confirmPurgeDiscontinued() {
    purging = true;
    try {
      const res = await purgeDiscontinuedCatalogItems();
      toasts.success(
        `Se eliminaron ${formatInt(res.deleted_count)} productos discontinuados` +
          (res.preserved_linked_count > 0
            ? ` (se conservaron ${formatInt(res.preserved_linked_count)} por estar vinculados a tu stock).`
            : '.')
      );
      purgeConfirmOpen = false;
      await handleAfterMutation();
    } catch (err) {
      toasts.error(err?.message || 'No se pudieron depurar los artículos discontinuados.');
    } finally {
      purging = false;
    }
  }
</script>

<div class="catalog-page">
  <!-- Cabecera de estado y acciones principales -->
  <section class="top-banner">
    <div class="top-banner__info">
      <div class="top-banner__title-row">
        <h1>Lista de Proveedor · Elonce Mayorista</h1>
        {#if latestStatus.in_my_stock_count > 0}
          <Badge variant="brand">
            {formatInt(latestStatus.in_my_stock_count)} en mi stock propio
          </Badge>
        {/if}
      </div>

      {#if latestStatus.latest_import}
        {@const imp = latestStatus.latest_import}
        <p class="top-banner__meta">
          Última actualización:
          <strong>{formatShortDate(imp.import_date)} (#{imp.sequence_in_day})</strong>
          <span class="muted">({formatDateTime(imp.created_at)})</span> ·
          <strong>{formatInt(latestStatus.active_catalog_count)}</strong> vigentes ·
          <span class="up">▲{formatInt(imp.price_up_count)}</span>
          <span class="down">▼{formatInt(imp.price_down_count)}</span> ·
          ✚{formatInt(imp.new_count)} ·
          ✖{formatInt(imp.discontinued_count)} ·
          <strong>{formatInt(imp.unchanged_count)}</strong> validados sin cambios
        </p>
      {:else}
        <p class="top-banner__meta">
          Aún no se cargó ninguna lista de precios del proveedor.
          {#if auth.isAdmin}Subí la primera planilla del día para inicializar el catálogo maestro.{/if}
        </p>
      {/if}
    </div>

    <div class="top-banner__actions">
      <Button variant="secondary" onclick={() => (historyModalOpen = true)}>
        🕘 Historial de cargas
      </Button>
      {#if auth.isAdmin}
        <Button variant="primary" onclick={() => (uploadModalOpen = true)}>
          ⬆ Subir lista del día
        </Button>
      {/if}
    </div>
  </section>

  <!-- Alerta cuando los productos discontinuados acumulados superan 100 -->
  {#if latestStatus.discontinued_alert}
    <div class="discontinued-alert" role="alert">
      <div>
        <strong>Atención: hay {formatInt(latestStatus.discontinued_catalog_count)} productos discontinuados acumulados</strong>
        <span>
          (supera el umbral de {latestStatus.discontinued_threshold} artículos que dejaron de venir en la lista del proveedor).
        </span>
      </div>
      <div class="discontinued-alert__actions">
        <Button
          variant="secondary"
          size="sm"
          onclick={() => {
            activeTab = 'catalog';
            filterStatus = 'discontinued';
          }}
        >
          Ver discontinuados
        </Button>
        {#if auth.isAdmin}
          <Button variant="danger" size="sm" onclick={() => (purgeConfirmOpen = true)}>
            🗑 Depurar discontinuados
          </Button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Pestañas principales -->
  <div class="main-tabs-bar">
    <div class="main-tabs" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'catalog'}
        class:active={activeTab === 'catalog'}
        onclick={() => (activeTab = 'catalog')}
      >
        Catálogo de Proveedor ({formatInt(latestStatus.active_catalog_count)})
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'diff'}
        class:active={activeTab === 'diff'}
        onclick={() => {
          diffTargetImportId = null;
          activeTab = 'diff';
        }}
      >
        Precios Diff (Variaciones)
        {#if latestStatus.latest_import && latestStatus.latest_import.mode !== 'baseline'}
          <span class="tab-pill mono-num">
            {formatInt(
              latestStatus.latest_import.changed_count +
                latestStatus.latest_import.new_count +
                latestStatus.latest_import.discontinued_count
            )}
          </span>
        {/if}
      </button>
    </div>

    <button
      type="button"
      class="discontinued-counter"
      onclick={() => {
        activeTab = 'catalog';
        filterStatus = filterStatus === 'discontinued' ? 'active' : 'discontinued';
      }}
      title="Alternar vista de productos discontinuados"
    >
      Discontinuados guardados: <strong class="mono-num">{formatInt(latestStatus.discontinued_catalog_count)}</strong>
    </button>
  </div>

  {#if activeTab === 'catalog'}
    <!-- Barra de búsqueda y filtros de Tab 1 -->
    <section class="catalog-filters">
      <div class="catalog-filters__row">
        <SearchInput
          placeholder="Buscar por código o descripción..."
          onSearch={(val) => (searchQ = val)}
        />

        <label class="filter-item">
          <span>Empaque:</span>
          <select bind:value={filterPackaging}>
            <option value="">Todos</option>
            {#each packagingOptions as opt (opt.packaging)}
              <option value={opt.packaging}>{opt.packaging} ({formatInt(opt.count)})</option>
            {/each}
          </select>
        </label>

        <label class="filter-item">
          <span>Estado:</span>
          <select bind:value={filterStatus}>
            <option value="active">Vigentes en última lista</option>
            <option value="discontinued">Discontinuados ({formatInt(latestStatus.discontinued_catalog_count)})</option>
            <option value="all">Todos</option>
          </select>
        </label>

        <label class="filter-item">
          <span>Ordenar:</span>
          <select bind:value={sortBy}>
            <option value="description">Descripción (A–Z)</option>
            <option value="code">Código</option>
            <option value="-last_price_changed_at">Modificados recientemente</option>
            <option value="price_with_vat">Menor $ C/IVA</option>
            <option value="-price_with_vat">Mayor $ C/IVA</option>
          </select>
        </label>
      </div>

      <div class="catalog-filters__row secondary-row">
        <div class="quick-checks">
          <label class="check-chip">
            <input type="checkbox" bind:checked={filterLiquidation} />
            <span>Solo liquidaciones</span>
          </label>

          <label class="filter-item">
            <span>Stock local:</span>
            <select bind:value={filterStockStatus}>
              <option value="all">Todos</option>
              <option value="in_stock">Solo en mi stock</option>
              <option value="not_in_stock">No cargados aún</option>
            </select>
          </label>

          <label class="filter-item">
            <span>Modificados:</span>
            <select bind:value={filterChangedDays}>
              <option value="">Cualquier fecha</option>
              <option value="0">Hoy</option>
              <option value="7">Últimos 7 días</option>
              <option value="30">Últimos 30 días</option>
            </select>
          </label>
        </div>

        {#if auth.isAdmin && selectedList.length > 0}
          <div class="selection-bar">
            <span><strong>{selectedList.length}</strong> seleccionado(s)</span>
            <Button variant="ghost" size="sm" onclick={clearSelection}>Limpiar</Button>
            <Button
              variant="primary"
              size="sm"
              onclick={() => openLoadStockModalFor(selectedList)}
            >
              ➕ Cargar seleccionados a mi stock
            </Button>
          </div>
        {/if}
      </div>
    </section>

    <!-- Tabla principal del catálogo -->
    {#if loadingCatalog}
      <div class="state-card">Cargando catálogo de proveedor...</div>
    {:else if catalogItems.length === 0}
      <div class="state-card">
        No se encontraron artículos con los filtros aplicados.
      </div>
    {:else}
      <div class="lc-table-wrap">
        <table class="lc-table">
          <thead>
            <tr>
              {#if auth.isAdmin}
                <th class="align-center" style="width: 38px;">Sel.</th>
              {/if}
              <th style="width: 90px;">Código</th>
              <th>Descripción y estado de validación</th>
              <th>Empaque</th>
              <th class="align-right">U×P</th>
              <th class="align-right">$ S/IVA</th>
              <th class="align-right">$ C/IVA</th>
              <th class="align-right">$ C/IVA+U. Unid.</th>
            </tr>
          </thead>
          <tbody>
            {#each catalogItems as item (item.id)}
              <tr class="catalog-row" onclick={() => openDetail(item.code)}>
                {#if auth.isAdmin}
                  <td class="align-center" onclick={(e) => toggleRowSelection(item, e)}>
                    <input
                      type="checkbox"
                      checked={Boolean(selectedMap[item.code])}
                      disabled={Boolean(item.linked_product_id)}
                      title={item.linked_product_id
                        ? 'Este artículo ya está cargado en tu stock'
                        : 'Seleccionar para cargar al stock'}
                    />
                  </td>
                {/if}
                <td class="mono-num"><strong>{item.code}</strong></td>
                <td>
                  <div class="item-desc">{item.description_clean}</div>
                  <div class="item-meta-row">
                    {#if item.linked_product_id}
                      <Badge variant="brand">En mi stock</Badge>
                    {/if}
                    {#if !item.in_latest_list}
                      <Badge variant="danger">Discontinuado</Badge>
                    {/if}
                    {#if item.price_anomaly}
                      <Badge variant="warning" title="Revisar relación S/IVA vs C/IVA en lista">
                        ⚠ Precio anómalo
                      </Badge>
                    {/if}
                    {#if item.last_change_type === 'price_up' && item.last_price_changed_at}
                      <Badge variant="danger">
                        ▲ {formatPct(item.last_change_pct)} ({formatRelativeDay(item.last_price_changed_at)})
                      </Badge>
                    {:else if item.last_change_type === 'price_down' && item.last_price_changed_at}
                      <Badge variant="brand">
                        ▼ {formatPct(item.last_change_pct)} ({formatRelativeDay(item.last_price_changed_at)})
                      </Badge>
                    {:else if item.last_change_type === 'new' && item.last_price_changed_at}
                      <Badge variant="info">
                        ✚ Nuevo ({formatRelativeDay(item.last_price_changed_at)})
                      </Badge>
                    {/if}
                    <span class="verified-label" title={`Última validación: ${formatDateTime(item.last_verified_at)}`}>
                      Validado: <strong>{formatRelativeDay(item.last_verified_at)}</strong>
                    </span>
                  </div>
                </td>
                <td>
                  <Badge variant={item.is_liquidation ? 'caution' : 'kraft'}>
                    {item.packaging}
                  </Badge>
                </td>
                <td class="align-right mono-num">{formatInt(item.units_per_package)}</td>
                <td class="align-right mono-num muted-price">{formatARS(item.price_net)}</td>
                <td class="align-right mono-num"><strong>{formatARS(item.price_with_vat)}</strong></td>
                <td class="align-right mono-num unit-highlight">
                  {formatARS(item.price_unit_with_utility)}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <Pagination
        {page}
        {pageSize}
        total={totalItems}
        {totalPages}
        onPageChange={(nextP) => loadCatalogPage(nextP)}
      />
    {/if}
  {:else}
    <!-- Tab 2: Precios Diff -->
    <PriceDiffTab
      initialImportId={diffTargetImportId}
      hasLinkedStock={latestStatus.in_my_stock_count > 0}
      onOpenItemDetail={openDetail}
    />
  {/if}
</div>

<!-- Modales -->
<UploadPriceListModal
  bind:open={uploadModalOpen}
  onUploaded={handleAfterMutation}
  onOpenDiff={(impId) => {
    diffTargetImportId = impId;
    activeTab = 'diff';
  }}
/>

<ImportHistoryModal
  bind:open={historyModalOpen}
  onMutated={handleAfterMutation}
  onSelectImportForDiff={(impId) => {
    diffTargetImportId = impId;
    activeTab = 'diff';
  }}
/>

<CatalogItemDetailModal
  bind:open={detailModalOpen}
  itemCode={detailItemCode}
  onLoadToStock={(arr) => openLoadStockModalFor(arr)}
/>

<LoadToStockModal
  bind:open={loadStockModalOpen}
  selectedItems={loadStockItems}
  onLoaded={handleAfterMutation}
/>

<Modal bind:open={purgeConfirmOpen} title="Depurar productos discontinuados" maxWidth="520px">
  <p style="margin: 0; line-height: 1.5;">
    Se eliminarán del catálogo maestro los <strong>{formatInt(latestStatus.discontinued_catalog_count)}</strong> artículos marcados como discontinuados
    que <strong>no estén cargados en tu stock propio</strong>. El historial de variaciones pasadas se conserva.
  </p>
  {#snippet footer()}
    <Button variant="secondary" onclick={() => (purgeConfirmOpen = false)} disabled={purging}>
      Cancelar
    </Button>
    <Button variant="danger" onclick={confirmPurgeDiscontinued} disabled={purging}>
      {purging ? 'Depurando...' : 'Confirmar depuración'}
    </Button>
  {/snippet}
</Modal>

<style>
  .catalog-page {
    display: grid;
    gap: 0.95rem;
  }

  .top-banner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.2rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-left: 4px solid var(--color-brand-primary);
    border-radius: var(--radius-md);
  }

  .top-banner__title-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.28rem;
  }

  .top-banner h1 {
    margin: 0;
    font-size: 1.2rem;
  }

  .top-banner__meta {
    margin: 0;
    font-size: 0.88rem;
    color: var(--color-text-secondary);
  }

  .top-banner__actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
  }

  .muted {
    color: var(--color-text-muted);
  }

  .up {
    color: var(--color-danger-text);
    font-weight: 700;
  }

  .down {
    color: var(--color-brand-primary);
    font-weight: 700;
  }

  .discontinued-alert {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.8rem 1rem;
    border-radius: var(--radius-md);
    background: var(--color-warning-bg);
    border: 1px solid var(--color-warning-border);
    color: var(--color-warning-text);
    font-size: 0.88rem;
  }

  .discontinued-alert__actions {
    display: flex;
    gap: 0.5rem;
  }

  .main-tabs-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    border-bottom: 2px solid var(--color-border);
  }

  .main-tabs {
    display: flex;
    gap: 0.35rem;
  }

  .main-tabs button {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: 1px solid transparent;
    border-bottom: none;
    background: transparent;
    padding: 0.62rem 1.05rem;
    font-weight: 700;
    font-size: 0.94rem;
    color: var(--color-text-secondary);
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    cursor: pointer;
  }

  .main-tabs button:hover {
    color: var(--color-text-primary);
    background: var(--color-surface-muted);
  }

  .main-tabs button.active {
    background: var(--color-surface);
    color: var(--color-brand-primary);
    border-color: var(--color-border);
    margin-bottom: -2px;
    border-bottom: 2px solid var(--color-surface);
  }

  .tab-pill {
    padding: 0.08rem 0.45rem;
    border-radius: 999px;
    background: var(--color-brand-soft-bg);
    color: var(--color-brand-soft-text);
    font-size: 0.76rem;
  }

  .discontinued-counter {
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text-secondary);
    border-radius: var(--radius-sm);
    padding: 0.32rem 0.65rem;
    font-size: 0.82rem;
    cursor: pointer;
    margin-bottom: 0.35rem;
  }

  .discontinued-counter:hover {
    background: var(--color-surface-muted);
  }

  .catalog-filters {
    display: grid;
    gap: 0.65rem;
    padding: 0.8rem 0.9rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .catalog-filters__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.65rem;
  }

  .secondary-row {
    justify-content: space-between;
    padding-top: 0.5rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .quick-checks {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem;
  }

  .filter-item {
    display: flex;
    align-items: center;
    gap: 0.38rem;
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  .filter-item select {
    padding: 0.4rem 0.55rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface);
    color: var(--color-text-primary);
  }

  .check-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.36rem 0.65rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface-muted);
    font-size: 0.84rem;
    font-weight: 600;
    cursor: pointer;
  }

  .selection-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.6rem;
    border-radius: var(--radius-sm);
    background: var(--color-brand-soft-bg);
    color: var(--color-brand-soft-text);
    font-size: 0.85rem;
  }

  .state-card {
    padding: 2.2rem 1rem;
    text-align: center;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    color: var(--color-text-secondary);
  }

  .catalog-row {
    cursor: pointer;
  }

  .item-desc {
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: 0.2rem;
  }

  .item-meta-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.38rem;
  }

  .verified-label {
    font-size: 0.76rem;
    color: var(--color-text-muted);
  }

  .muted-price {
    color: var(--color-text-secondary);
  }

  .unit-highlight {
    color: var(--color-brand-soft-text);
    font-weight: 700;
  }
</style>
