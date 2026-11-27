let items = $state([]);
let nextId = 1;

export const toasts = {
  get items() {
    return items;
  },

  push(message, { variant = 'info', durationMs = 4200 } = {}) {
    const id = nextId++;
    items = [...items, { id, message, variant }];
    if (durationMs > 0 && typeof window !== 'undefined') {
      window.setTimeout(() => {
        toasts.dismiss(id);
      }, durationMs);
    }
    return id;
  },

  success(message, durationMs = 3800) {
    return toasts.push(message, { variant: 'success', durationMs });
  },

  error(message, durationMs = 5500) {
    return toasts.push(message, { variant: 'danger', durationMs });
  },

  warning(message, durationMs = 4800) {
    return toasts.push(message, { variant: 'warning', durationMs });
  },

  dismiss(id) {
    items = items.filter((item) => item.id !== id);
  },
};
