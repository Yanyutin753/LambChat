import {
  PWA_SKIP_WAITING_MESSAGE,
  PWA_UPDATE_AVAILABLE_EVENT,
  isPwaUpdateReady,
  isTauriShell,
  shouldRegisterPwa,
  shouldUnregisterTauriPwa,
} from "./pwaGuards";

export interface LambChatPwaUpdateEventDetail {
  registration: ServiceWorkerRegistration;
}

let reloadWhenControllerChanges = false;

/** 桌面壳内回收历史注册的 PWA service worker 与 Cache Storage。

 * 本修复上线前，Windows WebView2（tauri.localhost 可注册 SW）里的桌面端
 * 可能已注册过 SW：updater 换装后它仍控制页面、回放旧 index.html/旧
 * chunk（RichChatComposer 动态导入 404 的主要根因），必须主动清退。 */
async function cleanupTauriServiceWorkers(): Promise<void> {
  try {
    const registrations =
      await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((reg) => reg.unregister()));
    if ("caches" in window) {
      const cacheKeys = await caches.keys();
      await Promise.all(cacheKeys.map((key) => caches.delete(key)));
    }
  } catch (error) {
    console.warn("[PWA] Tauri shell service worker cleanup failed:", error);
  }
}

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
  const tauriShell = isTauriShell();

  // Tauri 桌面壳：更新走 updater 换装，SW 只会留一层陈旧缓存——不注册，
  // 并回收历史版本已注册的 SW 与 Cache Storage。
  if (shouldUnregisterTauriPwa({ isTauriShell: tauriShell, hasServiceWorker })) {
    void cleanupTauriServiceWorkers();
    return;
  }

  if (
    !shouldRegisterPwa({
      isProduction: import.meta.env.PROD,
      hasServiceWorker,
      isTauriShell: tauriShell,
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
