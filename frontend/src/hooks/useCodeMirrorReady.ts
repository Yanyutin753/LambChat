import { useEffect, useState, type RefObject } from "react";

/** Keep parent search actions disabled until the lazy editor has mounted. */
export function useCodeMirrorReady(
  ref: RefObject<HTMLElement | null>,
  enabled: boolean,
) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const root = enabled ? ref.current : null;
    if (!root) {
      setReady(false);
      return;
    }
    const sync = () => setReady(Boolean(root.querySelector(".cm-editor")));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [enabled, ref]);
  return enabled && ready;
}
