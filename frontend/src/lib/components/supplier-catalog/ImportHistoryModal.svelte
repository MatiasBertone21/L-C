<script>
  import Modal from '../Modal.svelte';
  import Button from '../Button.svelte';
  import Badge from '../Badge.svelte';
  import Pagination from '../Pagination.svelte';
  import {
    deleteSupplierImport,
    fetchSupplierImports,
    rollbackSupplierImport,
  } from '../../api/supplierCatalog.js';
  import { formatDateTime, formatInt, formatShortDate } from '../../utils/format.js';
  import { auth } from '../../stores/auth.svelte.js';
  import { toasts } from '../../stores/toast.svelte.js';

  let {
    open = $bindable(false),
    onMutated = undefined,
    onSelectImportForDiff = undefined,
  } = $props();

  let items = $state([]);
  let page = $state(1);
  let total = $state(0);
  let totalPages = $state(1);
  let loading = $state(false);
  let actionLoadingId = $state(null);
  let confirmAction = $state(null); // { type: 'rollback' | 'delete', item }

  $effect(() => {
    if (open) {
      loadHistory(1);
    } else {
      confirmAction = null;
    }
  });

  async function loadHistory(targetPage = 1) {
    loading = true;
    try {
      const resp = await fetchSupplierImports({ page: targetPage, page_size: 12 });
      items = resp.items;
      page = resp.page;
      total = resp.total;
      totalPages = resp.total_pages;
    } catch (err) {
      toasts.error(err?.message || 'No se pudo cargar el historial de importaciones.');
    } finally {
      loading = false;
    }
  }

  async function executeConfirmedAction() {
    if (!confirmAction) return;
    const { type, item } = confirmAction;
    actionLoadingId = item.id;
    try {
      if (type === 'rollback') {
        const res = await rollbackSupplierImport(item.id);
        toasts.success(res.message);
      } else {
        await deleteSupplierImport(item.id);
        toasts.success(`Se eliminó del historial la importación del ${formatShortDate(item.import_date)}.`);
      }
      confirmAction = null;
      await loadHistory(page);
      onMutated?.();
    } catch (err) {
      toasts.error(err?.message || 'No se pudo completar la operación.');
    } finally {
      actionLoadingId = null;
    }
  }

  function statusBadgeVariant(st) {
    if (st === 'completed') return 'brand';
    if (st === 'rolled_back') return 'caution';
    if (st === 'failed') return 'danger';
    return 'neutral';
  }

  function statusLabel(st) {
    if (st === 'completed') return 'Vigente / Completada';
    if (st === 'rolled_back') return 'Deshecha';
    if (st === 'failed') return 'Fallida';
    return 'Procesando';
  }
</script>

<Modal bind:open title="Historial de cargas de listas" maxWidth="920px">
  {#if confirmAction}
    <div class="confirm-banner" role="alert">
      {#if confirmAction.type === 'rollback'}
        <strong>¿Deshacer la última carga ({confirmAction.item.original_filename})?</strong>
        <p>
          Se revertirán todos los cambios de esta importación (precios, descripciones, empaques, altas y discontinuados)
          al estado inmediato anterior. Tu stock propio y tus precios de venta no se modifican.
        </p>
      {:else}
        <strong>¿Eliminar registro histórico ({confirmAction.item.original_filename})?</strong>
        <p>
          Se borrará el registro y sus variaciones históricas en Precios Diff. El catálogo maestro actual no sufre cambios.
        </p>
      {/if}
      <div class="confirm-banner__actions">
        <Button variant="secondary" size="sm" onclick={() => (confirmAction = null)} disabled={Boolean(actionLoadingId)}>
          Cancelar
        </Button>
        <Button
          variant="danger"
          size="sm"
          onclick={executeConfirmedAction}
          disabled={Boolean(actionLoadingId)}
        >
          {actionLoadingId ? 'Aplicando...' : confirmAction.type === 'rollback' ? 'Sí, deshacer carga' : 'Sí, eliminar registro'}
        </Button>
      </div>
    </div>
  {/if}

  {#if loading}
    <p class="empty-msg">Cargando historial...</p>
  {:else if items.length === 0}
    <p class="empty-msg">Todavía no se registraron cargas de listas de proveedor.</p>
  {:else}
    <div class="lc-table-wrap">
      <table class="lc-table">
        <thead>
          <tr>
            <th>Fecha lista</th>
            <th>Archivo</th>
            <th>Estado</th>
            <th class="align-right">Vigentes</th>
            <th class="align-right">▲ / ▼</th>
            <th class="align-right">✚ / ✖</th>
            <th>Usuario</th>
            <th class="align-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {#each items as imp (imp.id)}
            <tr>
              <td class="mono-num">
                <div>{formatShortDate(imp.import_date)} (#{imp.sequence_in_day})</div>
                <small class="muted">{formatDateTime(imp.created_at)}</small>
              </td>
              <td>
                <div class="filename">{imp.original_filename}</div>
                <small class="muted">
                  {imp.mode === 'quick_validation'
                    ? 'Validación rápida'
                    : imp.mode === 'baseline'
                      ? 'Carga inicial'
                      : imp.detected_format}
                </small>
              </td>
              <td>
                <Badge variant={statusBadgeVariant(imp.status)}>
                  {imp.is_latest_completed ? '● Última vigente' : statusLabel(imp.status)}
                </Badge>
              </td>
              <td class="align-right mono-num">{formatInt(imp.total_items)}</td>
              <td class="align-right mono-num">
                <span class="up">▲{formatInt(imp.price_up_count)}</span>
                /
                <span class="down">▼{formatInt(imp.price_down_count)}</span>
              </td>
              <td class="align-right mono-num">
                ✚{formatInt(imp.new_count)} / ✖{formatInt(imp.discontinued_count)}
              </td>
              <td>
                <small class="muted">{imp.uploaded_by?.email || '—'}</small>
              </td>
              <td class="align-right">
                <div class="row-actions">
                  {#if imp.status === 'completed' && imp.mode !== 'baseline'}
                    <Button
                      variant="ghost"
                      size="sm"
                      onclick={() => {
                        open = false;
                        onSelectImportForDiff?.(imp.id);
                      }}
                    >
                      Ver Diff
                    </Button>
                  {/if}
                  {#if auth.isAdmin}
                    {#if imp.is_latest_completed}
                      <Button
                        variant="danger"
                        size="sm"
                        onclick={() => (confirmAction = { type: 'rollback', item: imp })}
                      >
                        ↶ Deshacer
                      </Button>
                    {:else}
                      <Button
                        variant="secondary"
                        size="sm"
                        onclick={() => (confirmAction = { type: 'delete', item: imp })}
                      >
                        Eliminar
                      </Button>
                    {/if}
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <Pagination {page} pageSize={12} {total} {totalPages} onPageChange={loadHistory} />
  {/if}

  {#snippet footer()}
    <Button variant="secondary" onclick={() => (open = false)}>Cerrar</Button>
  {/snippet}
</Modal>

<style>
  .confirm-banner {
    margin-bottom: 1rem;
    padding: 0.9rem 1rem;
    border-radius: var(--radius-md);
    background: var(--color-danger-bg);
    border: 1px solid var(--color-danger-border);
    color: var(--color-danger-text);
  }

  .confirm-banner p {
    margin: 0.35rem 0 0.75rem;
    font-size: 0.88rem;
  }

  .confirm-banner__actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .empty-msg {
    color: var(--color-text-secondary);
    text-align: center;
    padding: 1.5rem 0;
  }

  .filename {
    font-weight: 600;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: 0.78rem;
  }

  .up {
    color: var(--color-danger-text);
    font-weight: 600;
  }

  .down {
    color: var(--color-brand-primary);
    font-weight: 600;
  }

  .row-actions {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
</style>
