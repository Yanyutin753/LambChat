import {
  PWA_SKIP_WAITING_MESSAGE,
  PWA_UPDATE_AVAILABLE_EVENT,
  isPwaUpdateReady,
  shouldRegisterPwa,
} from "./pwaGuards";

export interface LambChatPwaUpdateEventDetail {
  registration: ServiceWorkerRegistration;
}

let reloadWhenControllerChanges = false;

function notifyPwaUpdateAvailable(registration: ServiceWorkerRegistration) {
  window.dispatchEvent(
    new CustomEvent<LambChatPwaUpdateEventDetail>(PWA_UPDATE_AVAILABLE_EVENT, {
      detail: { registration },
    }),
  );
}

function watchForPwaUpdates(registration: ServiceWorkerRegistration) {
  if (registration.waiting && navigator.serviceWorker.controller) {
    notifyPwaUpdateAvailable(registration);
  }

  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;
    if (!worker) return;

    worker.addEventListener("statechange", () => {
      if (
        isPwaUpdateReady({
          hasController: Boolean(navigator.serviceWorker.controller),
          workerState: worker.state,
        })
      ) {
        notifyPwaUpdateAvailable(registration);
      }
    });
  });
}

export function activateWaitingLambChatPwaUpdate(
  registration: ServiceWorkerRegistration,
): boolean {
  if (!registration.waiting) return false;

  reloadWhenControllerChanges = true;
  registration.waiting.postMessage({ type: PWA_SKIP_WAITING_MESSAGE });
  return true;
}

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
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!reloadWhenControllerChanges) return;
      reloadWhenControllerChanges = false;
      window.location.reload();
    });

    navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .then(async (registration) => {
        watchForPwaUpdates(registration);
        // 页面加载即激活等待中的新版本：旧 controller 在跑且已有 waiting
        // worker 时立即接管并重载一次，确保用户拿到最新 bundle，
        // 而不是等提示被确认期间一直运行旧缓存
        if (
          navigator.serviceWorker.controller &&
          registration.waiting &&
          activateWaitingLambChatPwaUpdate(registration)
        ) {
          return;
        }
        await registration.update().catch(() => undefined);
      })
      .catch((error) => {
        console.warn("[PWA] Service worker registration failed:", error);
      });
  });
}
