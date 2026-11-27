import { AUTH_TOKEN_KEY, AUTH_USER_KEY, setOnUnauthorized } from '../api/client.js';
import { fetchCurrentUser, loginRequest } from '../api/auth.js';
import { navigateTo } from '../utils/navigation.js';

function readStoredUser() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readStoredToken() {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

let token = $state(readStoredToken());
let user = $state(readStoredUser());
let initialized = $state(false);

function persist(nextToken, nextUser) {
  token = nextToken;
  user = nextUser;
  if (typeof window === 'undefined') return;
  if (nextToken) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, nextToken);
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  }
  if (nextUser) {
    window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(nextUser));
  } else {
    window.localStorage.removeItem(AUTH_USER_KEY);
  }
}

setOnUnauthorized(() => {
  persist(null, null);
  navigateTo('/login', { replace: true });
});

export const auth = {
  get token() {
    return token;
  },
  get user() {
    return user;
  },
  get isAuthenticated() {
    return Boolean(token && user);
  },
  get isAdmin() {
    return Boolean(user && user.role === 'admin');
  },
  get roleLabel() {
    if (!user) return '';
    return user.role === 'admin' ? 'Administrador' : 'Ventas';
  },
  get initialized() {
    return initialized;
  },

  async init() {
    if (initialized) return;
    if (!token) {
      initialized = true;
      return;
    }
    try {
      const freshUser = await fetchCurrentUser();
      persist(token, freshUser);
    } catch {
      persist(null, null);
    } finally {
      initialized = true;
    }
  },

  async login(email, password) {
    const response = await loginRequest(email, password);
    persist(response.access_token, response.user);
    return response.user;
  },

  logout() {
    persist(null, null);
    navigateTo('/login', { replace: true });
  },
};
