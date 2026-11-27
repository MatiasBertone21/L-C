export function navigateTo(path, { replace = false } = {}) {
  if (typeof window === 'undefined') return;

  const nextPath = path || '/';
  const currentPath = `${window.location.pathname}${window.location.search}`;
  if (nextPath === currentPath) return;

  if (replace) {
    window.history.replaceState({}, '', nextPath);
  } else {
    window.history.pushState({}, '', nextPath);
  }
  window.dispatchEvent(new PopStateEvent('popstate'));
}
