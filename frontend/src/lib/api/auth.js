import { apiRequest } from './client.js';

export function loginRequest(email, password) {
  return apiRequest('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
    skipAuth: true,
  });
}

export function fetchCurrentUser() {
  return apiRequest('/api/v1/auth/me');
}
