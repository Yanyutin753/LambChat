import { useState, useEffect, useCallback, useRef } from "react";
import i18n from "i18next";
import { versionApi } from "../services/api";
import type { UpdateState, ReleaseAsset } from "../types";

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Detect current runtime platform */
function detectPlatform(): "tauri" | "android" | "ios" | "web" {
  if (typeof window === "undefined") return "web";
  const win = window as any;
  if (win.__TAURI__ || win.__TAURI_INTERNALS__) return "tauri";
  if (typeof win.Capacitor !== "undefined") {
    const p = win.Capacitor.getPlatform();
    if (p === "android") return "android";
    if (p === "ios") return "ios";
  }
  return "web";
}

/** Find the best APK asset from the release assets list */
function findApkAsset(assets: ReleaseAsset[]): ReleaseAsset | null {
  // Prefer signed APK, fall back to any APK
  const signed = assets.find(
    (a) => a.name.endsWith(".apk") && a.name.includes("signed"),
  );
  if (signed) return signed;
  const anyApk = assets.find((a) => a.name.endsWith(".apk"));
  return anyApk ?? null;
}

export interface UseAutoUpdateReturn {
  state: UpdateState;
  showDialog: boolean;
  setShowDialog: (v: boolean) => void;
  startUpdate: () => Promise<void>;
  skipUpdate: () => void;
  /** 手动检查（设置页事件触发）：无更新时提示「已是最新」 */
  checkNow: () => Promise<void>;
}

const INITIAL_STATE: UpdateState = {
  available: false,
  version: null,
  releaseNotes: null,
  releaseUrl: null,
  releaseAssets: [],
  publishedAt: null,
  downloading: false,
  progress: 0,
  contentLength: 0,
  downloaded: 0,
  readyToInstall: false,
  error: null,
};

/** Debounce delay (ms) before checking for updates on startup */
const CHECK_DELAY_MS = 5000;

/** 周期检查间隔与聚焦检查最小间隔（纯函数见 shouldCheckNow，供测试） */
export const PERIODIC_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000;
export const FOCUS_CHECK_MIN_INTERVAL_MS = 60 * 60 * 1000;

/** 是否应发起一次检查：启动首查；聚焦距上次 ≥1h；周期 ≥12h */
export function shouldCheckNow(
  lastCheckedAt: number,
  now: number,
  minIntervalMs: number,
): boolean {
  return now - lastCheckedAt >= minIntervalMs;
}

/** 后台发现新版本时的系统通知（每版本一次；桌面托盘/系统通知） */
async function notifyUpdateAvailable(version: string | null): Promise<void> {
  try {
    const { appNotificationService } = await import(
      "../services/notifications/appNotificationService"
    );
    await appNotificationService.notify({
      type: "message",
      title: i18n.t("update.notificationTitle", "发现新版本"),
      body: i18n.t("update.notificationBody", {
        defaultValue: "新版本 {{version}} 已发布，点击「检查更新」安装",
        version: version ?? "",
      }),
      dedupeKey: `update-available:${version ?? "unknown"}`,
      importance: "normal",
    });
  } catch {
    // 通知尽力而为，失败不阻断
  }
}

export function useAutoUpdate(): UseAutoUpdateReturn {
  const [state, setState] = useState<UpdateState>(INITIAL_STATE);
  const [showDialog, setShowDialog] = useState(false);
  const platformRef = useRef(detectPlatform());
  const checkedRef = useRef(false);
  const lastCheckedAtRef = useRef(0);
  const notifiedVersionRef = useRef<string | null>(null);
  /** 已后台下载完成的 Tauri 更新对象（待用户确认安装重启） */
  const pendingUpdateRef = useRef<{
    install: () => Promise<void>;
  } | null>(null);

  const platform = platformRef.current;

  /** Check for updates. background=true 时不打断用户：弹窗 + 系统通知（每版本一次） */
  const checkForUpdate = useCallback(
    async (options?: { background?: boolean }) => {
      const background = options?.background === true;
      if (platform === "tauri") {
        await checkTauriUpdate(background);
      } else if (platform === "android" || platform === "ios") {
        await checkBackendUpdate(background);
      }
      lastCheckedAtRef.current = Date.now();
      // web: no-op
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [platform],
  );

  /** 手动「检查更新」（设置页事件触发）：无更新给「已是最新」提示 */
  const checkNow = useCallback(async () => {
    if (platform === "web") return;
    const before = stateRef.current.available;
    await checkForUpdate();
    if (!stateRef.current.available && !before) {
      const { toast } = await import("react-hot-toast");
      toast.success(i18n.t("update.upToDate", "已是最新版本"));
    }
  }, [platform, checkForUpdate]);

  /** Check via Tauri updater plugin */
  const checkTauriUpdate = useCallback(async (background = false) => {
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (update?.available) {
        setState({
          ...INITIAL_STATE,
          available: true,
          version: update.version,
          releaseNotes: update.body ?? null,
          releaseUrl: null,
          releaseAssets: [],
        });
        setShowDialog(true);
        // 自动下载：发现更新即后台静默下载（不阻塞用户），完成后一键重启安装
        void startBackgroundDownload(update);
        if (background && notifiedVersionRef.current !== update.version) {
          notifiedVersionRef.current = update.version;
          void notifyUpdateAvailable(update.version);
        }
      }
    } catch {
      // Silently fail — updater may not be available in dev
    }
  }, []);

  /** Check via backend /api/version endpoint */
  const checkBackendUpdate = useCallback(async (background = false) => {
    try {
      const info = await versionApi.checkForUpdates();
      if (info.has_update) {
        setState({
          ...INITIAL_STATE,
          available: true,
          version: info.latest_version ?? null,
          releaseNotes: info.release_notes ?? null,
          releaseUrl: info.release_url ?? null,
          releaseAssets: info.release_assets ?? [],
        });
        setShowDialog(true);
        const v = info.latest_version ?? null;
        if (background && v && notifiedVersionRef.current !== v) {
          notifiedVersionRef.current = v;
          void notifyUpdateAvailable(v);
        }
      }
    } catch {
      // Silently fail
    }
  }, []);

  /** Start the update process */
  const startUpdate = useCallback(async () => {
    if (platform === "tauri") {
      const pending = pendingUpdateRef.current;
      if (pending) {
        // 后台已下载完成：直接安装 + 重启
        try {
          await pending.install();
          const { relaunch } = await import("@tauri-apps/plugin-process");
          await relaunch();
        } catch (err) {
          setState((prev) => ({
            ...prev,
            error:
              err instanceof Error ? err.message : i18n.t("updateError", "更新失败"),
          }));
        }
        return;
      }
      await installTauriUpdate();
    } else if (platform === "android") {
      await installAndroidUpdate();
    } else if (platform === "ios") {
      openReleasePage();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, state]);

  /** 后台静默下载更新（发现即触发）：进度进 state，完成置 readyToInstall */
  const startBackgroundDownload = useCallback(async (update: any) => {
    if (pendingUpdateRef.current) return; // 已下载或下载中
    setState((prev) => (prev.available ? { ...prev, downloading: true, error: null } : prev));
    try {
      let downloaded = 0;
      let contentLength = 0;
      await update.download((event: any) => {
        switch (event.event) {
          case "Started":
            contentLength = event.data.contentLength ?? 0;
            setState((prev) => ({ ...prev, contentLength }));
            break;
          case "Progress": {
            downloaded += event.data.chunkLength;
            const pct = contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
            setState((prev) => ({ ...prev, downloaded, progress: pct }));
            break;
          }
          case "Finished":
            setState((prev) => ({ ...prev, progress: 100 }));
            break;
        }
      });
      pendingUpdateRef.current = { install: () => update.install() };
      setState((prev) => ({
        ...prev,
        downloading: false,
        readyToInstall: true,
      }));
    } catch (err) {
      // 后台下载失败不弹错：用户点「立即升级」时走前台 downloadAndInstall 兜底
      pendingUpdateRef.current = null;
      setState((prev) => ({ ...prev, downloading: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Install via Tauri updater (download + install + relaunch) */
  const installTauriUpdate = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      downloading: true,
      error: null,
      progress: 0,
    }));
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      const update = await check();
      if (!update) throw new Error("No update found");

      let downloaded = 0;
      let contentLength = 0;

      await update.downloadAndInstall((event: any) => {
        switch (event.event) {
          case "Started":
            contentLength = event.data.contentLength ?? 0;
            setState((prev) => ({ ...prev, contentLength }));
            break;
          case "Progress": {
            downloaded += event.data.chunkLength;
            const pct =
              contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
            setState((prev) => ({
              ...prev,
              downloaded,
              progress: pct,
            }));
            break;
          }
          case "Finished":
            setState((prev) => ({ ...prev, progress: 100 }));
            break;
        }
      });

      // Download and install complete, relaunch
      await relaunch();
    } catch (err) {
      setState((prev) => ({
        ...prev,
        downloading: false,
        error:
          err instanceof Error
            ? err.message
            : i18n.t("updateError", "更新失败"),
      }));
    }
  }, []);

  /** Download APK and trigger Android install intent */
  const installAndroidUpdate = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      downloading: true,
      error: null,
      progress: 0,
    }));
    try {
      const apkAsset = findApkAsset(state.releaseAssets);
      if (!apkAsset) throw new Error("No APK found in release assets");

      const response = await fetch(apkAsset.url);
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const contentLength = Number(response.headers.get("content-length") ?? 0);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      // Stream download into a Blob — avoids loading entire APK in memory as an array
      const chunks: BlobPart[] = [];
      let downloaded = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(new Uint8Array(value));
        downloaded += value.byteLength;
        const pct = contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
        setState((prev) => ({
          ...prev,
          downloaded,
          progress: pct,
          contentLength,
        }));
      }

      const blob = new Blob(chunks, {
        type: apkAsset.content_type,
      });

      // Use Capacitor Filesystem to write the APK, then open it
      const { Filesystem, Directory } = await import("@capacitor/filesystem");
      const base64 = await blobToBase64(blob);
      const fileName = apkAsset.name || "LambChat-update.apk";
      const result = await Filesystem.writeFile({
        path: fileName,
        data: base64,
        directory: Directory.Cache,
      });

      // Use Capacitor Share to open the APK file (triggers install)
      const { Share } = await import("@capacitor/share");
      await Share.share({
        path: result.uri,
      });

      setState((prev) => ({
        ...prev,
        downloading: false,
        progress: 100,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        downloading: false,
        error:
          err instanceof Error
            ? err.message
            : i18n.t("updateError", "更新失败"),
      }));
    }
  }, [state.releaseAssets]);

  /** Open release page in browser (iOS) */
  const openReleasePage = useCallback(() => {
    if (state.releaseUrl) {
      window.open(state.releaseUrl, "_blank", "noopener");
    }
  }, [state.releaseUrl]);

  /** Skip this update */
  const skipUpdate = useCallback(() => {
    setShowDialog(false);
  }, []);

  // 最新 state 供 checkNow 读取（避免闭包旧值）
  const stateRef = useRef(state);
  stateRef.current = state;

  // Auto-check on mount with delay
  useEffect(() => {
    if (platform === "web") return;
    if (checkedRef.current) return;
    checkedRef.current = true;

    const timer = setTimeout(() => {
      void checkForUpdate();
    }, CHECK_DELAY_MS);

    // 周期检查（12h，后台发现 → 弹窗 + 系统通知）
    const periodic = setInterval(() => {
      if (
        lastCheckedAtRef.current &&
        shouldCheckNow(lastCheckedAtRef.current, Date.now(), PERIODIC_CHECK_INTERVAL_MS)
      ) {
        void checkForUpdate({ background: true });
      }
    }, 30 * 60 * 1000);

    // 聚焦检查（距上次 ≥1h，后台发现不打断）
    const onFocus = () => {
      if (
        !lastCheckedAtRef.current ||
        shouldCheckNow(lastCheckedAtRef.current, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS)
      ) {
        void checkForUpdate({ background: true });
      }
    };
    window.addEventListener("focus", onFocus);

    // 设置页「检查更新」入口（lambchat:check-update 事件）
    const onManualCheck = () => {
      void checkNow();
    };
    window.addEventListener("lambchat:check-update", onManualCheck);

    return () => {
      clearTimeout(timer);
      clearInterval(periodic);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("lambchat:check-update", onManualCheck);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform]);

  return {
    state,
    showDialog,
    setShowDialog,
    startUpdate,
    skipUpdate,
    checkNow,
  };
}

/** Convert a Blob to base64 string */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Remove data URL prefix: "data:...;base64,"
      const base64 = result.split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
