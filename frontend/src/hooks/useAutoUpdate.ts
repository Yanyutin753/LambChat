import { useState, useEffect, useCallback, useRef } from "react";
import i18n from "i18next";
import { versionApi, buildReleaseAssetDownloadUrl } from "../services/api";
import { buildApiUrl } from "../services/api/config";
import {
  getLinuxInstallInfo,
  installLinuxPackage,
  subscribeLinuxUpdateProgress,
  type LinuxInstallSource,
} from "../services/tauri/linuxUpdate";
import {
  buildLinuxPackageAssetName,
  buildLinuxPackageDownloadUrl,
} from "../utils/linuxUpdateAssets";
import { APP_VERSION } from "../utils/appVersion";
import { bytesToBase64 } from "../utils/bytesToBase64";
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
  /** 跳过此版本：该版本不再自动提醒（手动检查仍会显示） */
  skipThisVersion: () => void;
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
  linuxInstallSource: null,
};

/** 当前 runtime 是否是 Linux 桌面（deb/rpm/AppImage 分流只在这类设备生效） */
export function isLinuxDesktopEnvironment(
  nav: { userAgent?: string; platform?: string } = typeof navigator !== "undefined"
    ? navigator
    : {},
): boolean {
  const ua = nav.userAgent ?? "";
  const platform = nav.platform ?? "";
  // Android WebView UA 含 "Linux; Android"——排除移动端
  const uaIsLinux = /linux/i.test(ua) && !/android/i.test(ua);
  return uaIsLinux || /linux/i.test(platform);
}

export function formatUpdateError(error: unknown, platform: string): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const detail = raw.trim() || "更新失败";
  if (platform === "tauri" && /permission|access denied|拒绝访问|权限|replace|rename/i.test(detail)) {
    return `${detail}。Linux 请确认 AppImage 所在目录可写，并从用户目录运行；如果安装的是 .deb/.rpm，请手动安装新版安装包。`;
  }
  return detail;
}

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

/** 「跳过此版本」持久化（标准更新器行为：该版本不再自动打扰） */
export const SKIPPED_UPDATE_VERSIONS_KEY = "lambchat:skipped-update-versions";

export function readSkippedUpdateVersions(
  storage: Pick<Storage, "getItem">,
): string[] {
  try {
    const raw = storage.getItem(SKIPPED_UPDATE_VERSIONS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v): v is string => typeof v === "string");
  } catch {
    return [];
  }
}

export function isVersionSkipped(
  version: string | null,
  skipped: string[],
): boolean {
  if (!version) return false;
  return skipped.includes(version);
}

/** 是否弹更新提示：跳过过的版本静默（手动「检查更新」除外——主动要看） */
export function shouldPromptUpdate(
  version: string | null,
  skipped: string[],
  opts: { manual: boolean },
): boolean {
  if (!version) return false;
  if (opts.manual) return true;
  return !isVersionSkipped(version, skipped);
}

function persistSkippedVersion(
  storage: Pick<Storage, "setItem" | "getItem">,
  version: string,
): void {
  const next = [...readSkippedUpdateVersions(storage), version];
  try {
    storage.setItem(SKIPPED_UPDATE_VERSIONS_KEY, JSON.stringify(next));
  } catch {
    // 存储写失败（隐私模式等）：本次会话内仍生效（调用方关闭弹窗）
  }
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
  /** Linux 安装来源（Rust 检测；null=非 Linux 桌面或检测未完成） */
  const linuxSourceRef = useRef<LinuxInstallSource | null>(null);
  /** 资产命名的 arch 段（Rust 上报；拼 deb/rpm 资产名用） */
  const linuxArchRef = useRef<string | null>(null);
  /** 检测 promise 缓存：更新检查与安装分流共用一次检测结果 */
  const linuxDetectPromiseRef = useRef<Promise<LinuxInstallSource | null> | null>(
    null,
  );

  const platform = platformRef.current;

  /**
   * 确保 Linux 安装来源已检测（一次）：更新检查时决定是否后台静默下载、
   * 安装时决定走 updater 还是 deb/rpm 包管理器路径。非 Linux 桌面返回 null。
   */
  const ensureLinuxSource = useCallback(
    async (): Promise<LinuxInstallSource | null> => {
      if (platform !== "tauri" || !isLinuxDesktopEnvironment()) return null;
      if (!linuxDetectPromiseRef.current) {
        linuxDetectPromiseRef.current = (async () => {
          const info = await getLinuxInstallInfo();
          const source: LinuxInstallSource = info?.source ?? "unknown";
          linuxSourceRef.current = source;
          linuxArchRef.current = info?.arch ?? null;
          setState((prev) => ({ ...prev, linuxInstallSource: source }));
          return source;
        })();
      }
      return linuxDetectPromiseRef.current;
    },
    [platform],
  );

  // Linux 桌面：启动即检测安装来源 + 订阅 deb/rpm 下载进度事件
  useEffect(() => {
    if (platform !== "tauri" || !isLinuxDesktopEnvironment()) return;
    void ensureLinuxSource();
    let unsub: (() => void) | null = null;
    let disposed = false;
    void subscribeLinuxUpdateProgress((p) => {
      setState((prev) => ({
        ...prev,
        downloaded: p.downloaded,
        contentLength: p.contentLength,
        progress:
          p.contentLength > 0
            ? (p.downloaded / p.contentLength) * 100
            : prev.progress,
      }));
    }).then((fn) => {
      if (disposed) {
        fn?.();
      } else {
        unsub = fn;
      }
    });
    return () => {
      disposed = true;
      unsub?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform]);

  /** Check for updates. background=true 时不打断用户：弹窗 + 系统通知（每版本一次）；
   * manual=true（设置页手动检查）无视「跳过此版本」列表 */
  const checkForUpdate = useCallback(
    async (options?: { background?: boolean; manual?: boolean }) => {
      const background = options?.background === true;
      const manual = options?.manual === true;
      if (platform === "tauri") {
        await checkTauriUpdate(background, manual);
      } else if (platform === "android" || platform === "ios") {
        await checkBackendUpdate(background, manual);
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
    await checkForUpdate({ manual: true });
    if (!stateRef.current.available && !before) {
      const { toast } = await import("react-hot-toast");
      toast.success(i18n.t("update.upToDate", "已是最新版本"));
    }
  }, [platform, checkForUpdate]);

  /** 后台静默下载更新（发现即触发）：进度进 state，完成置 readyToInstall */
  const startBackgroundDownload = useCallback(async (update: any) => {
    if (pendingUpdateRef.current) return; // 已下载或下载中
    setState((prev) =>
      prev.available ? { ...prev, downloading: true, error: null } : prev,
    );
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
            const pct =
              contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
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
    } catch {
      // 后台下载失败不弹错：用户点「立即升级」时走前台 downloadAndInstall 兜底
      pendingUpdateRef.current = null;
      setState((prev) => ({ ...prev, downloading: false }));
    }
  }, []);

  /** Check via Tauri updater plugin */
  const checkTauriUpdate = useCallback(
    async (background = false, manual = false) => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (update?.available) {
          const prompt = shouldPromptUpdate(
            update.version,
            readSkippedUpdateVersions(window.localStorage),
            { manual },
          );
          const linuxSource = await ensureLinuxSource();
          setState({
            ...INITIAL_STATE,
            available: true,
            version: update.version,
            releaseNotes: update.body ?? null,
            releaseUrl: null,
            releaseAssets: [],
            linuxInstallSource: linuxSourceRef.current,
          });
          if (prompt) {
            setShowDialog(true);
            // 自动下载：发现更新即后台静默下载（不阻塞用户），完成后一键重启安装。
            // deb/rpm 除外——updater 只会拉 AppImage 且装不上系统包，改为点击时
            // 走「下载 deb/rpm + pkexec 安装」
            if (linuxSource !== "deb" && linuxSource !== "rpm") {
              void startBackgroundDownload(update);
            }
            if (background && notifiedVersionRef.current !== update.version) {
              notifiedVersionRef.current = update.version;
              void notifyUpdateAvailable(update.version);
            }
          }
        }
      } catch {
        // Silently fail — updater may not be available in dev
      }
    },
    [startBackgroundDownload, ensureLinuxSource],
  );

  /** Check via backend /api/version endpoint（上报客户端版本，has_update 按它判断） */
  const checkBackendUpdate = useCallback(async (background = false, manual = false) => {
    try {
      const info = await versionApi.checkForUpdates(APP_VERSION);
      if (info.has_update) {
        const v = info.latest_version ?? null;
        const prompt = shouldPromptUpdate(
          v,
          readSkippedUpdateVersions(window.localStorage),
          { manual },
        );
        setState({
          ...INITIAL_STATE,
          available: true,
          version: v,
          releaseNotes: info.release_notes ?? null,
          releaseUrl: info.release_url ?? null,
          releaseAssets: info.release_assets ?? [],
        });
        if (prompt) {
          setShowDialog(true);
          if (background && v && notifiedVersionRef.current !== v) {
            notifiedVersionRef.current = v;
            void notifyUpdateAvailable(v);
          }
        }
      }
    } catch {
      // Silently fail
    }
  }, []);

  /** Start the update process */
  const startUpdate = useCallback(async () => {
    if (platform === "tauri") {
      // Linux 安装来源分流：deb/rpm 走包管理器安装；unknown 回落下载页；
      // appimage / 非 Linux 走 updater 替换重启（含后台已下载的 pending）
      const linuxSource = await ensureLinuxSource();
      if (linuxSource === "deb" || linuxSource === "rpm") {
        await installLinuxPackageUpdate(linuxSource);
        return;
      }
      if (linuxSource === "unknown") {
        openDownloadPage();
        return;
      }
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
            error: formatUpdateError(err, platform),
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

  /**
   * Linux deb/rpm 安装：同源反代下载对应安装包 → Rust 侧 pkexec
   * `apt|dnf install` 提权安装（进度经 linux-update-progress 事件）→ 成功后
   * relaunch 进新版。系统包归 root 所有，不能也不该由 updater 直接覆盖。
   */
  const installLinuxPackageUpdate = useCallback(
    async (source: "deb" | "rpm") => {
      setState((prev) => ({
        ...prev,
        downloading: true,
        error: null,
        progress: 0,
        downloaded: 0,
      }));
      try {
        const version = stateRef.current.version;
        const arch = linuxArchRef.current;
        if (!version) throw new Error("No update version known");
        if (!arch) {
          throw new Error("Unsupported Linux architecture for package update");
        }
        const assetName = buildLinuxPackageAssetName(version, arch, source);
        const url = buildLinuxPackageDownloadUrl(assetName, version);
        await installLinuxPackage(url, source);
        setState((prev) => ({ ...prev, downloading: false, progress: 100 }));
        const { relaunch } = await import("@tauri-apps/plugin-process");
        await relaunch();
      } catch (err) {
        setState((prev) => ({
          ...prev,
          downloading: false,
          error: formatUpdateError(err, platform),
        }));
      }
    },
    [platform],
  );

  /** 打开下载页（Linux unknown 来源兜底：无法判定安装方式时不盲装） */
  const openDownloadPage = useCallback(() => {
    window.open(buildApiUrl("/download"), "_blank", "noopener");
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
        error: formatUpdateError(err, platform),
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

      // 原生 DownloadManager 优先：无 CORS、不占 WebView 内存、系统断点续传
      try {
        await installAndroidUpdateViaNative(apkAsset.name);
        return;
      } catch {
        // 原生桥不可用/下载失败（旧壳、系统裁剪、瞬时网络）：
        // 回落 WebView 流式代理路径——两条链路同一代理 URL，行为一致
      }
      await installAndroidUpdateViaWebViewStream(apkAsset.name);
    } catch (err) {
      setState((prev) => ({
        ...prev,
        downloading: false,
        error:
          err instanceof TypeError
            ? i18n.t("updateDownloadNetworkError", {
                defaultValue: "下载失败，请检查网络后重试",
              })
            : err instanceof Error
              ? err.message
              : i18n.t("updateError", "更新失败"),
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.releaseAssets]);

  /** 原生 DownloadManager 下载 + 拉起安装器（progress 轮询驱动进度条） */
  const installAndroidUpdateViaNative = useCallback(
    async (assetName: string) => {
      const { UpdateDownloader } = await import(
        "../services/capacitor/updateDownloader"
      );
      const { downloadId } = await UpdateDownloader.start({
        // 同一自托管代理 URL：原生无 CORS 约束，但保住「服务端可达 GitHub」
        // 的转发语义（国内直连 GitHub release 不稳）
        url: buildReleaseAssetDownloadUrl(assetName),
        fileName: assetName,
      });

      // 轮询驱动 UI：binder 调用极轻量，400ms 粒度足够
      for (;;) {
        await new Promise((r) => setTimeout(r, 400));
        const p = await UpdateDownloader.progress({ downloadId });
        const pct = p.totalBytes > 0 ? (p.bytesSoFar / p.totalBytes) * 100 : 0;
        setState((prev) => ({
          ...prev,
          downloaded: p.bytesSoFar,
          progress: pct,
          contentLength: p.totalBytes,
        }));
        if (p.status === "success" && p.localUri) {
          const { ApkInstaller } = await import(
            "../services/capacitor/apkInstaller"
          );
          const res = await ApkInstaller.installApk({ path: p.localUri });
          if (res.status === "settings") {
            const { toast } = await import("react-hot-toast");
            toast(
              i18n.t("update.installPermissionHint", {
                defaultValue:
                  "请先允许 LambChat 安装未知应用，授权后重新点击升级",
              }),
            );
          }
          setState((prev) => ({ ...prev, downloading: false, progress: 100 }));
          return;
        }
        if (p.status === "failed") {
          throw new Error(`Native download failed (reason=${p.reason ?? "?"})`);
        }
      }
    },
    [],
  );

  /** WebView 流式代理下载（兜底）：逐块 base64 落盘避免整包驻留内存 */
  const installAndroidUpdateViaWebViewStream = useCallback(
    async (assetName: string) => {
      // 直连 GitHub browser_download_url 会被 WebView CORS 拦截
      // （Failed to fetch）：走自托管后端同源代理流式下载。
      const response = await fetch(buildReleaseAssetDownloadUrl(assetName));
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const contentLength = Number(response.headers.get("content-length") ?? 0);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      // 逐块 base64 落盘（writeFile + appendFile），避免整包 APK 在
      // WebView 内存里 Blob+base64 双份驻留导致低端机 OOM。
      const { Filesystem, Directory } = await import("@capacitor/filesystem");
      const fileName = assetName || "LambChat-update.apk";
      let wroteAny = false;
      let writtenUri: string | undefined;
      let downloaded = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value?.length) continue;
        const base64Chunk = bytesToBase64(new Uint8Array(value));
        if (!wroteAny) {
          const written = await Filesystem.writeFile({
            path: fileName,
            data: base64Chunk,
            directory: Directory.Cache,
          });
          writtenUri = written.uri;
          wroteAny = true;
        } else {
          await Filesystem.appendFile({
            path: fileName,
            data: base64Chunk,
            directory: Directory.Cache,
          });
        }
        downloaded += value.byteLength;
        const pct = contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
        setState((prev) => ({
          ...prev,
          downloaded,
          progress: pct,
          contentLength,
        }));
      }
      if (!wroteAny || !writtenUri) throw new Error("Empty download");

      // 拉起系统安装器（ACTION_VIEW + FileProvider 覆盖安装）。
      // Share（ACTION_SEND）只开分享面板装不了包。
      const { ApkInstaller } = await import(
        "../services/capacitor/apkInstaller"
      );
      const res = await ApkInstaller.installApk({ path: writtenUri });
      if (res.status === "settings") {
        // 未授予「安装未知应用」：原生已跳设置页，提示授权后重试
        const { toast } = await import("react-hot-toast");
        toast(
          i18n.t("update.installPermissionHint", {
            defaultValue: "请先允许 LambChat 安装未知应用，授权后重新点击升级",
          }),
        );
      }

      setState((prev) => ({
        ...prev,
        downloading: false,
        progress: 100,
      }));
    },
    [],
  );

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

  /** 跳过此版本：持久化后该版本不再自动提醒（手动检查仍会显示） */
  const skipThisVersion = useCallback(() => {
    const version = stateRef.current.version;
    if (version) {
      persistSkippedVersion(window.localStorage, version);
    }
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
    const periodic = setInterval(
      () => {
        if (
          lastCheckedAtRef.current &&
          shouldCheckNow(
            lastCheckedAtRef.current,
            Date.now(),
            PERIODIC_CHECK_INTERVAL_MS,
          )
        ) {
          void checkForUpdate({ background: true });
        }
      },
      30 * 60 * 1000,
    );

    // 聚焦检查（距上次 ≥1h，后台发现不打断）
    const onFocus = () => {
      if (
        !lastCheckedAtRef.current ||
        shouldCheckNow(
          lastCheckedAtRef.current,
          Date.now(),
          FOCUS_CHECK_MIN_INTERVAL_MS,
        )
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
    skipThisVersion,
    checkNow,
  };
}
