import { shouldRegisterPwa } from "./pwaGuards";

export function registerLambChatPwa(): void {
  const hasServiceWorker =
    typeof navigator !== "undefined" && "serviceWorker" in navigator;

  if (
    !shouldRegisterPwa({
      isProduction: import.meta.env.PROD,
      hasServiceWorker,
    })
  ) {
    return;
  }

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch((error) => {
        console.warn("[PWA] Service worker registration failed:", error);
      });
  });
}
