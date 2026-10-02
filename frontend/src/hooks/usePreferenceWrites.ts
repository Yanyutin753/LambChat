import { useCallback, useLayoutEffect, useRef, useState } from "react";

export type PreferenceWriteState = "saving" | "error";
type Write = {
  request: () => Promise<unknown>;
  onSaved?: () => void;
  pending: boolean;
};

/** Keep failed preference requests for retry; ignore responses from old owners. */
export function usePreferenceWrites(owner: string | undefined) {
  const writes = useRef(new Map<string, Write>());
  const [states, setStates] = useState<Record<string, PreferenceWriteState>>(
    {},
  );
  useLayoutEffect(() => {
    setStates({});
    const current = writes.current;
    return () => current.clear();
  }, [owner]);

  const save = useCallback(
    (key: string, request: Write["request"], onSaved?: Write["onSaved"]) => {
      if (writes.current.get(key)?.pending) return false;
      const write = { request, onSaved, pending: true };
      writes.current.set(key, write);
      setStates((previous) => ({ ...previous, [key]: "saving" }));
      void Promise.resolve()
        .then(() => (writes.current.get(key) === write ? request() : undefined))
        .then(
          () => {
            if (writes.current.get(key) !== write) return;
            writes.current.delete(key);
            setStates((previous) => {
              const next = { ...previous };
              delete next[key];
              return next;
            });
            onSaved?.();
          },
          () => {
            if (writes.current.get(key) !== write) return;
            write.pending = false;
            setStates((previous) => ({ ...previous, [key]: "error" }));
          },
        );
      return true;
    },
    [],
  );
  const retry = useCallback(
    (key: string) => {
      const write = writes.current.get(key);
      if (write) save(key, write.request, write.onSaved);
    },
    [save],
  );
  return { states, save, retry };
}
