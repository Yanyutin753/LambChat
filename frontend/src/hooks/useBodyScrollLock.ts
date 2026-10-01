import { useEffect } from "react";

let locks = 0;
let previousOverflow = "";
let inertLocks = 0;
let inertTargets: [HTMLElement, boolean][] = [];

export function useBodyScrollLock(locked: boolean, inertBackground = false) {
  useEffect(() => {
    if (!locked) return;
    if (locks++ === 0) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    if (inertBackground && inertLocks++ === 0) {
      inertTargets = Array.from(
        document.querySelectorAll<HTMLElement>(
          "#root, body > [data-chat-composer-host]",
        ),
      ).map((element) => {
        const previous = element.inert ?? false;
        element.inert = true;
        return [element, previous];
      });
    }
    return () => {
      if (--locks === 0) document.body.style.overflow = previousOverflow;
      if (inertBackground && --inertLocks === 0) {
        for (const [element, previous] of inertTargets)
          element.inert = previous;
        inertTargets = [];
      }
    };
  }, [locked, inertBackground]);
}
