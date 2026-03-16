/**
 * Mobile device detection and viewport utilities
 */

/**
 * Check if running on a mobile device
 */
export function isMobileDevice(): boolean {
  if (typeof window === "undefined") return false;
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent,
  );
}

/**
 * Reset mobile viewport to fix zoom issues
 * This is useful after system dialogs (like notification permission) that may cause zoom
 */
export function resetMobileViewport(): void {
  if (!isMobileDevice()) return;

  // Scroll to top to reset any scroll offset
  window.scrollTo(0, 0);

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
    }, 10);
  }
}
