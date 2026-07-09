import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type RefObject,
} from "react";

/**
 * Dynamically tracks a trigger element's position and returns the
 * dropdown/popover CSSProperties, updating smoothly on resize, scroll,
 * and visualViewport changes.
 *
 * @param triggerRef  - Ref to the trigger element that anchors the dropdown.
 * @param isOpen      - Whether the dropdown is currently shown.
 * @param getPosition - Pure function that turns the trigger's bounding rect
 *                      into the desired CSSProperties for the dropdown.
 */
export function useStickyDropdownPosition<T extends HTMLElement = HTMLElement>(
  triggerRef: RefObject<T | null>,
  isOpen: boolean,
  getPosition: (rect: DOMRect) => CSSProperties,
): CSSProperties {
  const [style, setStyle] = useState<CSSProperties>({});
  const posFnRef = useRef(getPosition);
  posFnRef.current = getPosition;

  const updatePositionNow = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setStyle(posFnRef.current(rect));
    }
  }, [triggerRef]);

  useLayoutEffect(() => {
    if (!isOpen) {
      setStyle({});
      return;
    }

    updatePositionNow();
  }, [isOpen, triggerRef, updatePositionNow]);

  useEffect(() => {
    if (!isOpen) return;

    let raf = 0;
    const update = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        updatePositionNow();
      });
    };

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [isOpen, triggerRef, updatePositionNow]);

  return style;
}
