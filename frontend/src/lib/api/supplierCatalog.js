import { apiRequest } from './client.js';

export function uploadSupplierPriceList(file, { force = false } = {}) {
  const formData = new FormData();
  formData.append('file', file);
  if (force) {
    formData.append('force', 'true');
  }
  return apiRequest('/api/v1/supplier-catalog/imports', {
    method: 'POST',
    body: formData,
  });
}

export function fetchLatestImportStatus() {
  return apiRequest('/api/v1/supplier-catalog/imports/latest');
}

export function fetchSupplierImports(params = {}) {
  return apiRequest('/api/v1/supplier-catalog/imports', { query: params });
}

export function fetchSupplierImportDetail(importId) {
  return apiRequest(`/api/v1/supplier-catalog/imports/${encodeURIComponent(importId)}`);
}

export function rollbackSupplierImport(importId) {
  return apiRequest(`/api/v1/supplier-catalog/imports/${encodeURIComponent(importId)}/rollback`, {
    method: 'POST',
  });
}

export function deleteSupplierImport(importId) {
  return apiRequest(`/api/v1/supplier-catalog/imports/${encodeURIComponent(importId)}`, {
    method: 'DELETE',
  });
}

export function fetchCatalogItems(params = {}, { signal } = {}) {
  return apiRequest('/api/v1/supplier-catalog/items', { query: params, signal });
}

export function fetchCatalogFilters() {
  return apiRequest('/api/v1/supplier-catalog/items/filters');
}

export function fetchCatalogItemDetail(code) {
  return apiRequest(`/api/v1/supplier-catalog/items/${encodeURIComponent(code)}`);
}

export function purgeDiscontinuedCatalogItems() {
  return apiRequest('/api/v1/supplier-catalog/items/discontinued', {
    method: 'DELETE',
  });
}

export function loadCatalogItemsToStock(items) {
  return apiRequest('/api/v1/supplier-catalog/items/load-to-stock', {
    method: 'POST',
    body: { items },
  });
}

export function fetchPriceChanges(params = {}, { signal } = {}) {
  return apiRequest('/api/v1/supplier-catalog/price-changes', { query: params, signal });
}

export function fetchPriceChangesSummary(params = {}, { signal } = {}) {
  return apiRequest('/api/v1/supplier-catalog/price-changes/summary', { query: params, signal });
}
