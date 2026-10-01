/**
 * Mobile device detection and viewport utilities
 */

/**
 * Check if running on a mobile device
 */
export function isMobileDevice(): boolean {
  if (typeof window === "undefined") return false;
  return (
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
      navigator.userAgent,
    ) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

/**
 * Reset mobile viewport to fix zoom issues
 * This is useful after system dialogs (like notification permission) that may cause zoom
 */
export function resetMobileViewport(): void {
  if (!isMobileDevice()) return;

  const scrollX = window.scrollX ?? 0;
  const scrollY = window.scrollY ?? 0;

  // Force viewport recalculation by temporarily changing and restoring the meta tag
  const viewport = document.querySelector('meta[name="viewport"]');
  if (viewport) {
    const originalContent = viewport.getAttribute("content");
    // Temporarily set to trigger recalculation
    viewport.setAttribute("content", "width=device-width, initial-scale=1.0");
    // Restore original content after a short delay
    setTimeout(() => {
      if (originalContent) {
        viewport.setAttribute("content", originalContent);
      }
      window.scrollTo(scrollX, scrollY);
    }, 10);
  }
}

function isEditableElement(element: Element | null): element is HTMLElement {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    (element instanceof HTMLElement && element.isContentEditable)
  );
}

/**
 * Keep focused fields visible after the virtual keyboard finishes animating.
 * The repeated scrolls cover iOS Safari and Android Chrome timing differences.
 */
export function scrollFocusedInputIntoView(): void {
  if (!isMobileDevice() || typeof window === "undefined") return;

  const activeElement = document.activeElement;
  if (!isEditableElement(activeElement)) return;

  [80, 280].forEach((delay) => {
    window.setTimeout(() => {
      if (
        document.activeElement !== activeElement ||
        !activeElement.isConnected
      )
        return;
      activeElement.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        behavior: "auto",
      });
    }, delay);
  });
}

/**
 * Install mobile viewport handlers without resetting during ordinary in-page taps.
 */
export function installMobileViewportResetHandlers(): void {
  if (
    !isMobileDevice() ||
    typeof window === "undefined" ||
    typeof document === "undefined"
  ) {
    return;
  }

  let pageWasHidden = document.visibilityState === "hidden";

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      pageWasHidden = true;
      return;
    }

    if (pageWasHidden) {
      pageWasHidden = false;
      resetMobileViewport();
    }
  });

  window.addEventListener("focus", () => {
    if (!pageWasHidden) return;
    pageWasHidden = false;
    resetMobileViewport();
  });

  document.addEventListener("focusin", scrollFocusedInputIntoView);
}
