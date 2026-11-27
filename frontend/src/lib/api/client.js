export const AUTH_TOKEN_KEY = 'lc_auth_token';
export const AUTH_USER_KEY = 'lc_auth_user';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

let unauthorizedHandler = null;

export function setOnUnauthorized(callback) {
  unauthorizedHandler = callback;
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'api_error', payload = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.payload = payload;
  }
}

export function buildQueryString(params = {}) {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null && item !== '') {
          sp.append(key, String(item));
        }
      }
    } else {
      sp.set(key, String(value));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

export async function apiRequest(
  path,
  { method = 'GET', query = null, body = undefined, signal = undefined, skipAuth = false } = {}
) {
  const url = `${API_BASE_URL}${path}${query ? buildQueryString(query) : ''}`;
  const headers = {
    Accept: 'application/json',
  };

  if (!skipAuth && typeof window !== 'undefined') {
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let serializedBody = body;
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && body !== null && !isFormData) {
    headers['Content-Type'] = 'application/json';
    serializedBody = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: serializedBody,
      signal,
    });
  } catch (err) {
    if (err && err.name === 'AbortError') {
      throw err;
    }
    throw new ApiError(
      'No se pudo conectar con el servidor. Verificá que el backend esté en ejecución.',
      { status: 0, code: 'network_error' }
    );
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get('content-type') || '';
  let payload = null;
  if (contentType.includes('application/json')) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  } else {
    const text = await response.text();
    payload = text || null;
  }

  if (!response.ok) {
    if (response.status === 401 && !skipAuth && typeof unauthorizedHandler === 'function') {
      unauthorizedHandler();
    }

    let message = 'Ocurrió un error al procesar la solicitud.';
    let code = 'api_error';
    if (payload && typeof payload === 'object') {
      if (typeof payload.detail === 'string') {
        message = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        message = payload.detail.map((d) => d.msg || JSON.stringify(d)).join(' · ');
      }
      if (typeof payload.code === 'string') {
        code = payload.code;
      }
    } else if (typeof payload === 'string' && payload.trim()) {
      message = payload;
    }

    if (response.status === 403 && message === 'Ocurrió un error al procesar la solicitud.') {
      message = 'No tenés permisos suficientes para realizar esta acción.';
    }

    throw new ApiError(message, {
      status: response.status,
      code,
      payload,
    });
  }

  return payload;
}
