<script>
  import Modal from '../Modal.svelte';
  import Button from '../Button.svelte';
  import Badge from '../Badge.svelte';
  import { fetchCatalogItemDetail } from '../../api/supplierCatalog.js';
  import {
    formatARS,
    formatDateTime,
    formatInt,
    formatPct,
    formatShortDate,
  } from '../../utils/format.js';
  import { auth } from '../../stores/auth.svelte.js';
  import { toasts } from '../../stores/toast.svelte.js';

  let {
    open = $bindable(false),
    itemCode = null,
    onLoadToStock = undefined,
  } = $props();

  let detail = $state(null);
  let loading = $state(false);

  $effect(() => {
    if (open && itemCode) {
      loadDetail(itemCode);
    } else if (!open) {
      detail = null;
    }
  });

  async function loadDetail(code) {
    loading = true;
    try {
      detail = await fetchCatalogItemDetail(code);
    } catch (err) {
      toasts.error(err?.message || 'No se pudo cargar el detalle del artículo.');
      open = false;
    } finally {
      loading = false;
    }
  }
</script>

<Modal bind:open title={detail ? `Artículo #${detail.code}` : 'Detalle de artículo'} maxWidth="740px">
  {#if loading || !detail}
    <p class="loading-msg">Cargando ficha del artículo...</p>
  {:else}
    <div class="detail-layout">
      <div class="detail-top">
        <div>
          <h3 class="detail-title">{detail.description_clean}</h3>
          <p class="detail-raw">Descripción original en lista: <span class="mono-num">{detail.description}</span></p>
        </div>
        <div class="detail-badges">
          <Badge variant={detail.is_liquidation ? 'caution' : 'kraft'}>
            {detail.packaging}
            {#if detail.liquidation_tag && detail.liquidation_tag !== 'LIQUIDA'}
              ({detail.liquidation_tag})
            {/if}
          </Badge>
          {#if !detail.in_latest_list}
            <Badge variant="danger">Discontinuado</Badge>
          {:else}
            <Badge variant="brand">Vigente</Badge>
          {/if}
          {#if detail.price_anomaly}
            <Badge variant="warning">Precio anómalo del proveedor</Badge>
          {/if}
        </div>
      </div>

      <div class="prices-grid">
        <div class="price-box">
          <span>$ S/IVA (Paquete)</span>
          <strong class="mono-num">{formatARS(detail.price_net)}</strong>
        </div>
        <div class="price-box">
          <span>$ C/IVA (Paquete)</span>
          <strong class="mono-num">{formatARS(detail.price_with_vat)}</strong>
        </div>
        <div class="price-box">
          <span>Utilidad % proveedor</span>
          <strong class="mono-num">{detail.supplier_utility_pct}%</strong>
        </div>
        <div class="price-box">
          <span>$ C/IVA y Util. Paquete</span>
          <strong class="mono-num">{formatARS(detail.price_pack_with_utility)}</strong>
        </div>
        <div class="price-box">
          <span>Unidades por Paquete</span>
          <strong class="mono-num">{formatInt(detail.units_per_package)}</strong>
        </div>
        <div class="price-box highlight">
          <span>$ C/IVA y Util. Unidad</span>
          <strong class="mono-num">{formatARS(detail.price_unit_with_utility)}</strong>
        </div>
      </div>

      <div class="meta-strip">
        <span>Última validación: <strong>{formatDateTime(detail.last_verified_at)}</strong></span>
        <span>
          Último cambio de precio:
          <strong>{detail.last_price_changed_at ? formatDateTime(detail.last_price_changed_at) : 'Sin variaciones desde el alta'}</strong>
        </span>
        <span>Empaque original: <strong>{detail.packaging_raw || '—'}</strong></span>
        {#if detail.image_source_url}
          <a href={detail.image_source_url} target="_blank" rel="noopener noreferrer">
            Ver imagen de referencia del proveedor ↗
          </a>
        {/if}
      </div>

      {#if detail.linked_product}
        <div class="linked-card">
          <div>
            <strong>En tu stock propio ({detail.linked_product.sku})</strong>
            <p>
              Stock actual: <strong class="mono-num">{formatInt(detail.linked_product.stock)}</strong> u. ·
              Precio de venta local: <strong class="mono-num">{formatARS(detail.linked_product.unit_price)}</strong>
            </p>
          </div>
        </div>
      {/if}

      <div class="history-section">
        <h4>Historial reciente de variaciones</h4>
        {#if detail.recent_changes.length === 0}
          <p class="muted">No registra cambios de precio posteriores a su carga inicial.</p>
        {:else}
          <div class="lc-table-wrap">
            <table class="lc-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Evento</th>
                  <th class="align-right">$ C/IVA Anterior</th>
                  <th class="align-right">$ C/IVA Nuevo</th>
                  <th class="align-right">Variación</th>
                </tr>
              </thead>
              <tbody>
                {#each detail.recent_changes as ch (ch.id)}
                  <tr>
                    <td class="mono-num">{formatShortDate(ch.import_date)}</td>
                    <td>
                      {#if ch.change_type === 'price_up'}
                        <Badge variant="danger">▲ Subió</Badge>
                      {:else if ch.change_type === 'price_down'}
                        <Badge variant="brand">▼ Bajó</Badge>
                      {:else if ch.change_type === 'new'}
                        <Badge variant="info">✚ Alta / Reactiv.</Badge>
                      {:else}
                        <Badge variant="neutral">✖ Quitado</Badge>
                      {/if}
                    </td>
                    <td class="align-right mono-num">{formatARS(ch.old_price_with_vat)}</td>
                    <td class="align-right mono-num">{formatARS(ch.new_price_with_vat)}</td>
                    <td class="align-right mono-num">{formatPct(ch.diff_pct)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="secondary" onclick={() => (open = false)}>Cerrar</Button>
    {#if auth.isAdmin && detail && !detail.linked_product_id}
      <Button
        variant="primary"
        onclick={() => {
          const snapshot = detail;
          open = false;
          onLoadToStock?.([snapshot]);
        }}
      >
        ➕ Cargar a mi stock
      </Button>
    {/if}
  {/snippet}
</Modal>

<style>
  .loading-msg,
  .muted {
    color: var(--color-text-secondary);
    font-size: 0.9rem;
  }

  .detail-layout {
    display: grid;
    gap: 1.05rem;
  }

  .detail-top {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .detail-title {
    margin: 0 0 0.25rem;
    font-size: 1.08rem;
  }

  .detail-raw {
    margin: 0;
    font-size: 0.82rem;
    color: var(--color-text-muted);
  }

  .detail-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .prices-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.6rem;
  }

  .price-box {
    padding: 0.65rem 0.75rem;
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-sm);
    background: var(--color-surface-muted);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .price-box.highlight {
    background: var(--color-brand-soft-bg);
    border-color: #b7e2ce;
  }

  .price-box span {
    font-size: 0.77rem;
    color: var(--color-text-secondary);
  }

  .price-box strong {
    font-size: 1rem;
  }

  .meta-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem 1.2rem;
    font-size: 0.83rem;
    color: var(--color-text-secondary);
    padding: 0.65rem 0.8rem;
    background: var(--color-surface-muted);
    border-radius: var(--radius-sm);
  }

  .meta-strip a {
    color: var(--color-accent-blue);
    font-weight: 600;
    text-decoration: none;
  }

  .meta-strip a:hover {
    text-decoration: underline;
  }

  .linked-card {
    padding: 0.75rem 0.9rem;
    border-radius: var(--radius-sm);
    background: var(--color-brand-soft-bg);
    border: 1px solid var(--color-brand-primary);
    color: var(--color-brand-soft-text);
    font-size: 0.88rem;
  }

  .linked-card p {
    margin: 0.25rem 0 0;
  }

  .history-section h4 {
    margin: 0 0 0.5rem;
    font-size: 0.95rem;
  }

  @media (max-width: 640px) {
    .prices-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
