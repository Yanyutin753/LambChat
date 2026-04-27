type Listener = () => void;

export interface SingletonStore<T> {
  get: () => T;
  set: (next: T) => void;
  subscribe: (listener: Listener) => () => void;
}

export function createSingletonStore<T>(initialState: T): SingletonStore<T> {
  let current = initialState;
  const listeners = new Set<Listener>();

  return {
    get() {
      return current;
    },
    set(next) {
      if (Object.is(current, next)) {
        return;
      }
      current = next;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
