<script>
  import Modal from '../Modal.svelte';
  import Button from '../Button.svelte';
  import { loadCatalogItemsToStock } from '../../api/supplierCatalog.js';
  import { formatARS, formatInt } from '../../utils/format.js';
  import { toasts } from '../../stores/toast.svelte.js';

  let {
    open = $bindable(false),
    selectedItems = [],
    onLoaded = undefined,
  } = $props();

  let draftRows = $state([]);
  let defaultCategory = $state('Librería');
  let saving = $state(false);
  let errorMsg = $state('');

  $effect(() => {
    if (open) {
      errorMsg = '';
      draftRows = selectedItems.map((it) => ({
        code: it.code,
        description_clean: it.description_clean,
        packaging: it.packaging,
        units_per_package: it.units_per_package,
        price_net: it.price_net,
        price_with_vat: it.price_with_vat,
        price_unit_with_utility: it.price_unit_with_utility,
        initial_stock: 1,
        min_stock: 1,
        sale_price: Number((it.price_unit_with_utility || it.price_with_vat || 100).toFixed(2)),
      }));
    }
  });

  async function handleSubmit() {
    errorMsg = '';
    for (const r of draftRows) {
      if (!r.sale_price || Number(r.sale_price) <= 0) {
        errorMsg = `Ingresá un precio de venta mayor a $0 para el artículo ${r.code}.`;
        return;
      }
      if (Number(r.initial_stock) < 0 || Number(r.min_stock) < 0) {
        errorMsg = `El stock no puede ser negativo en el artículo ${r.code}.`;
        return;
      }
    }

    saving = true;
    try {
      const payload = draftRows.map((r) => ({
        code: r.code,
        initial_stock: Math.trunc(Number(r.initial_stock) || 0),
        min_stock: Math.trunc(Number(r.min_stock) || 0),
        sale_price: Number(r.sale_price),
        category: defaultCategory.trim() || 'Librería',
      }));

      const res = await loadCatalogItemsToStock(payload);
      if (res.created_count > 0) {
        toasts.success(
          `Se incorporaron ${res.created_count} artículo(s) a tu stock propio${
            res.skipped_count > 0 ? ` (${res.skipped_count} omitidos por ya existir)` : ''
          }.`
        );
      } else {
        toasts.warning('Los artículos seleccionados ya se encontraban cargados en tu stock.');
      }
      open = false;
      onLoaded?.(res);
    } catch (err) {
      errorMsg = err?.message || 'No se pudieron cargar los artículos al stock.';
    } finally {
      saving = false;
    }
  }
</script>

<Modal bind:open title={`Cargar al stock propio (${draftRows.length})`} maxWidth="880px">
  <div class="stock-modal-body">
    <div class="stock-top-bar">
      <p>
        Definí el stock inicial y el precio de venta de tu local. Se muestran como referencia los importes informados por el proveedor.
      </p>
      <label class="cat-field">
        <span>Categoría inicial:</span>
        <input type="text" bind:value={defaultCategory} maxlength="80" />
      </label>
    </div>

    {#if errorMsg}
      <div class="stock-error" role="alert">{errorMsg}</div>
    {/if}

    <div class="lc-table-wrap">
      <table class="lc-table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Artículo</th>
            <th class="align-right">U×P</th>
            <th class="align-right">$ C/IVA Paq.</th>
            <th class="align-right">$ C/IVA+Util. Unid.</th>
            <th class="align-right">Stock inicial</th>
            <th class="align-right">Stock mín.</th>
            <th class="align-right">Mi precio venta ($)</th>
          </tr>
        </thead>
        <tbody>
          {#each draftRows as row (row.code)}
            <tr>
              <td class="mono-num">{row.code}</td>
              <td>
                <div class="item-name">{row.description_clean}</div>
                <small class="muted">{row.packaging}</small>
              </td>
              <td class="align-right mono-num">{formatInt(row.units_per_package)}</td>
              <td class="align-right mono-num">{formatARS(row.price_with_vat)}</td>
              <td class="align-right mono-num">{formatARS(row.price_unit_with_utility)}</td>
              <td class="align-right">
                <input
                  type="number"
                  min="0"
                  step="1"
                  class="num-input mono-num"
                  bind:value={row.initial_stock}
                />
              </td>
              <td class="align-right">
                <input
                  type="number"
                  min="0"
                  step="1"
                  class="num-input mono-num"
                  bind:value={row.min_stock}
                />
              </td>
              <td class="align-right">
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  class="price-input mono-num"
                  bind:value={row.sale_price}
                />
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  {#snippet footer()}
    <Button variant="secondary" onclick={() => (open = false)} disabled={saving}>Cancelar</Button>
    <Button variant="primary" onclick={handleSubmit} disabled={saving || draftRows.length === 0}>
      {saving ? 'Guardando...' : 'Confirmar alta en mi stock'}
    </Button>
  {/snippet}
</Modal>

<style>
  .stock-modal-body {
    display: grid;
    gap: 0.9rem;
  }

  .stock-top-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .stock-top-bar p {
    margin: 0;
    font-size: 0.88rem;
    color: var(--color-text-secondary);
    max-width: 500px;
  }

  .cat-field {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.86rem;
    font-weight: 600;
  }

  .cat-field input {
    padding: 0.35rem 0.6rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    width: 150px;
  }

  .stock-error {
    padding: 0.65rem 0.8rem;
    border-radius: var(--radius-sm);
    background: var(--color-danger-bg);
    border: 1px solid var(--color-danger-border);
    color: var(--color-danger-text);
    font-size: 0.86rem;
  }

  .item-name {
    font-weight: 600;
    font-size: 0.86rem;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: 0.76rem;
  }

  .num-input {
    width: 74px;
    padding: 0.32rem 0.45rem;
    text-align: right;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }

  .price-input {
    width: 112px;
    padding: 0.32rem 0.45rem;
    text-align: right;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
</style>
