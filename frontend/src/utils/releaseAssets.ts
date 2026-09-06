/**
 * GitHub Release 资产匹配（纯函数，独立于 React 便于测试）。
 *
 * 下载页/引导卡从 `/api/version` 拿最新 release 的 `release_assets`，按
 * 文件名模式拆出「桌面端安装包」与「独立 daemon 二进制」——发新版后链接
 * 自动跟随最新 release，无需在前端维护版本号。
 */

import type { ReleaseAsset } from "../types";

export type DesktopPlatform = "windows" | "macos" | "linux";

export interface DownloadLink {
  name: string;
  url: string;
  size?: number;
}

export interface DesktopDownloadGroup {
  windows: DownloadLink[];
  macos: DownloadLink[];
  linux: DownloadLink[];
}

/** 签名/元数据噪音资产不参与下载列表。 */
function isNoiseAsset(name: string): boolean {
  return /\.(sig|idsig)$/i.test(name) || name === "latest.json";
}

/** 平台检测（下载页高亮推荐包用）：只认桌面系统，移动端返回 null。 */
export function detectDesktopPlatform(
  userAgent: string,
): DesktopPlatform | null {
  // 移动检测必须先于 macOS/iPadOS（iPhone/iPad UA 都含 "Mac OS X" 字样）
  if (/Android|iPhone|iPad|iPod/i.test(userAgent)) return null;
  if (/Windows/i.test(userAgent)) return "windows";
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "macos";
  if (/Linux|X11/i.test(userAgent)) return "linux";
  return null;
}

/**
 * 把桌面端安装包分组。匹配规则对齐 app-release.yml 的资产命名：
 * - Windows：`*-Windows.msi`（安装版）、`*-Windows-Portable.zip`（便携版）
 * - macOS：`*.dmg`
 * - Linux：`*.AppImage` / `*.deb` / `*.rpm`（x86_64 在前、arm64 在后）
 */
export function matchDesktopAssets(
  assets: ReleaseAsset[],
): DesktopDownloadGroup {
  const group: DesktopDownloadGroup = { windows: [], macos: [], linux: [] };
  for (const asset of assets) {
    if (isNoiseAsset(asset.name)) continue;
    const name = asset.name;
    const link: DownloadLink = {
      name,
      url: asset.url,
      ...(asset.size != null ? { size: asset.size } : {}),
    };
    if (/Windows\.msi$/i.test(name)) {
      group.windows.push(link);
    } else if (/Windows-Portable\.zip$/i.test(name)) {
      group.windows.push(link);
    } else if (/\.dmg$/i.test(name)) {
      group.macos.push(link);
    } else if (
      /\.(AppImage|deb|rpm)$/i.test(name) &&
      /linux|amd64|arm64/i.test(name)
    ) {
      group.linux.push(link);
    }
  }
  // 同平台内保持稳定顺序：安装版在前便携在后；x86_64 在前 arm64 在后
  const windowsRank = (n: string) => (/Portable/i.test(n) ? 1 : 0);
  group.windows.sort(
    (x, y) =>
      windowsRank(x.name) - windowsRank(y.name) || x.name.localeCompare(y.name),
  );
  group.macos.sort((x, y) => x.name.localeCompare(y.name));
  group.linux.sort((x, y) => {
    const arch = (n: string) => (/arm64|aarch64/i.test(n) ? 1 : 0);
    return arch(x.name) - arch(y.name) || x.name.localeCompare(y.name);
  });
  return group;
}

/**
 * 平台主推安装包（下载页「立即下载 xx 版」直链用）：取该平台分组首位——
 * Windows 为 .msi 安装版、macOS 为 .dmg、Linux 为 x86_64 AppImage。
 * 分组为空（该平台无资产）返回 null，由调用方回退到分区选择。
 */
export function pickRecommendedAsset(
  group: DesktopDownloadGroup,
  platform: DesktopPlatform,
): DownloadLink | null {
  return group[platform][0] ?? null;
}

/** Android UA 检测（Hero 直下 APK 用）。 */
export function isAndroid(userAgent: string): boolean {
  return /Android/i.test(userAgent);
}

/** 签名 APK（Android 原生应用直装包）；.idsig 签名与 iOS xcarchive 不算。 */
export function matchAndroidApk(assets: ReleaseAsset[]): DownloadLink | null {
  for (const asset of assets) {
    if (/LambChat-android-.*-signed\.apk$/i.test(asset.name)) {
      return {
        name: asset.name,
        url: asset.url,
        ...(asset.size != null ? { size: asset.size } : {}),
      };
    }
  }
  return null;
}

/** daemon 二进制的稳定展示顺序（Windows → macOS → Linux x64 → Linux arm64）。 */
const DAEMON_TRIPLE_ORDER = [
  "x86_64-pc-windows-msvc",
  "aarch64-apple-darwin",
  "x86_64-unknown-linux-gnu",
  "aarch64-unknown-linux-gnu",
];

/** 独立 daemon 二进制（服务器/无桌面场景），按平台稳定排序。 */
export function matchDaemonAssets(assets: ReleaseAsset[]): DownloadLink[] {
  const daemons: DownloadLink[] = [];
  for (const asset of assets) {
    if (isNoiseAsset(asset.name)) continue;
    if (!/^lambchat-daemon-/i.test(asset.name)) continue;
    daemons.push({
      name: asset.name,
      url: asset.url,
      ...(asset.size != null ? { size: asset.size } : {}),
    });
  }
  const tripleOf = (name: string) =>
    DAEMON_TRIPLE_ORDER.find((triple) => name.toLowerCase().includes(triple)) ??
    "__unknown__";
  daemons.sort(
    (x, y) =>
      DAEMON_TRIPLE_ORDER.indexOf(tripleOf(x.name)) -
        DAEMON_TRIPLE_ORDER.indexOf(tripleOf(y.name)) ||
      x.name.localeCompare(y.name),
  );
  return daemons;
}

/** 资产大小人性化显示（无大小时返回空串，由 UI 决定占位）。 */
export function formatAssetSize(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = "B";
  for (const next of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${unit}`;
}
