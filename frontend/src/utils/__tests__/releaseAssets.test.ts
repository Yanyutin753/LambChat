import { expect, test } from "vitest";
import type { ReleaseAsset } from "../../types";
import {
  detectDesktopPlatform,
  formatAssetSize,
  isAndroid,
  matchAndroidApk,
  matchDaemonAssets,
  matchDesktopAssets,
  pickRecommendedAsset,
} from "../releaseAssets";

/** 以真实 release v2.8.1 的资产名为 fixture（含 .sig/.idsig/latest.json 噪音）。 */
const V281_ASSETS: ReleaseAsset[] = [
  a("LambChat-2.8.1-1.aarch64.rpm.sig"),
  a("LambChat-android-v2.8.1-signed.apk"),
  a("lambchat-daemon-aarch64-apple-darwin"),
  a("lambchat-daemon-aarch64-unknown-linux-gnu"),
  a("lambchat-daemon-x86_64-pc-windows-msvc.exe"),
  a("lambchat-daemon-x86_64-unknown-linux-gnu"),
  a("LambChat-ios-v2.8.1-unsigned-xcarchive.zip"),
  a("LambChat-v2.8.1-Linux-arm64.AppImage"),
  a("LambChat-v2.8.1-Linux-arm64.deb"),
  a("LambChat-v2.8.1-Linux-arm64.rpm"),
  a("LambChat-v2.8.1-Linux-x86_64.AppImage"),
  a("LambChat-v2.8.1-Linux-x86_64.deb"),
  a("LambChat-v2.8.1-Linux-x86_64.rpm"),
  a("LambChat-v2.8.1-macOS.dmg"),
  a("LambChat-v2.8.1-Windows-Portable.zip"),
  a("LambChat-v2.8.1-Windows.msi"),
  a("LambChat_2.8.1_amd64.AppImage.sig"),
  a("LambChat_2.8.1_x64_en-US.msi.sig"),
  a("latest.json"),
];

function a(name: string, size = 86_234_112): ReleaseAsset {
  return {
    name,
    url: `https://github.com/Yanyutin753/LambChat/releases/download/v2.8.1/${name}`,
    size,
    content_type: "application/octet-stream",
  };
}

// ---------------------------------------------------------------------------
// detectDesktopPlatform
// ---------------------------------------------------------------------------

test("detects windows / macos / linux desktop from user agents", () => {
  expect(
    detectDesktopPlatform(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    ),
  ).toBe("windows");
  expect(
    detectDesktopPlatform(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    ),
  ).toBe("macos");
  expect(
    detectDesktopPlatform("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"),
  ).toBe("linux");
});

test("mobile user agents are not desktop platforms", () => {
  expect(
    detectDesktopPlatform(
      "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36",
    ),
  ).toBeNull();
  expect(
    detectDesktopPlatform(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Safari/604.1",
    ),
  ).toBeNull();
  expect(
    detectDesktopPlatform("Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X)"),
  ).toBeNull();
});

test("unknown user agents return null", () => {
  expect(detectDesktopPlatform("")).toBeNull();
  expect(detectDesktopPlatform("curl/8.4.0")).toBeNull();
});

// ---------------------------------------------------------------------------
// matchDesktopAssets
// ---------------------------------------------------------------------------

test("groups desktop installers by platform and drops noise assets", () => {
  const group = matchDesktopAssets(V281_ASSETS);

  expect(group.windows.map((d) => d.name)).toEqual([
    "LambChat-v2.8.1-Windows.msi",
    "LambChat-v2.8.1-Windows-Portable.zip",
  ]);
  expect(group.macos.map((d) => d.name)).toEqual(["LambChat-v2.8.1-macOS.dmg"]);
  expect(group.linux.map((d) => d.name)).toEqual([
    "LambChat-v2.8.1-Linux-x86_64.AppImage",
    "LambChat-v2.8.1-Linux-x86_64.deb",
    "LambChat-v2.8.1-Linux-x86_64.rpm",
    "LambChat-v2.8.1-Linux-arm64.AppImage",
    "LambChat-v2.8.1-Linux-arm64.deb",
    "LambChat-v2.8.1-Linux-arm64.rpm",
  ]);
});

test("keeps download urls and sizes intact", () => {
  const group = matchDesktopAssets(V281_ASSETS);
  const msi = group.windows[0];
  expect(msi.url).toBe(
    "https://github.com/Yanyutin753/LambChat/releases/download/v2.8.1/LambChat-v2.8.1-Windows.msi",
  );
  expect(msi.size).toBe(86_234_112);
});

test("empty or unmatched assets yield empty groups", () => {
  const group = matchDesktopAssets([
    a("LambChat-android-v2.8.1-signed.apk"),
    a("latest.json"),
  ]);
  expect(group.windows).toEqual([]);
  expect(group.macos).toEqual([]);
  expect(group.linux).toEqual([]);
});

// ---------------------------------------------------------------------------
// matchDaemonAssets
// ---------------------------------------------------------------------------

test("collects daemon binaries in a stable platform order", () => {
  const daemons = matchDaemonAssets(V281_ASSETS);

  expect(daemons.map((d) => d.name)).toEqual([
    "lambchat-daemon-x86_64-pc-windows-msvc.exe",
    "lambchat-daemon-aarch64-apple-darwin",
    "lambchat-daemon-x86_64-unknown-linux-gnu",
    "lambchat-daemon-aarch64-unknown-linux-gnu",
  ]);
});

test("daemon matching ignores the desktop app and mobile assets", () => {
  const daemons = matchDaemonAssets(V281_ASSETS);
  expect(daemons.every((d) => d.name.startsWith("lambchat-daemon-"))).toBe(
    true,
  );
  expect(matchDaemonAssets([a("LambChat-v2.8.1-macOS.dmg")])).toEqual([]);
});

// ---------------------------------------------------------------------------
// pickRecommendedAsset
// ---------------------------------------------------------------------------

test("recommends the platform's primary installer for direct download", () => {
  const group = matchDesktopAssets(V281_ASSETS);

  expect(pickRecommendedAsset(group, "windows")?.name).toBe(
    "LambChat-v2.8.1-Windows.msi",
  );
  expect(pickRecommendedAsset(group, "macos")?.name).toBe(
    "LambChat-v2.8.1-macOS.dmg",
  );
  expect(pickRecommendedAsset(group, "linux")?.name).toBe(
    "LambChat-v2.8.1-Linux-x86_64.AppImage",
  );
});

test("returns null when a platform has no assets", () => {
  const group = matchDesktopAssets([a("LambChat-android-v2.8.1-signed.apk")]);
  expect(pickRecommendedAsset(group, "windows")).toBeNull();
  expect(pickRecommendedAsset(group, "macos")).toBeNull();
});

// ---------------------------------------------------------------------------
// isAndroid / matchAndroidApk
// ---------------------------------------------------------------------------

test("detects android user agents", () => {
  expect(
    isAndroid("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36"),
  ).toBe(true);
  expect(isAndroid("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe(false);
  expect(
    isAndroid("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)"),
  ).toBe(false);
});

test("matches the signed android apk and ignores noise", () => {
  const apk = matchAndroidApk(V281_ASSETS);
  expect(apk?.name).toBe("LambChat-android-v2.8.1-signed.apk");
  expect(apk?.url).toBe(
    "https://github.com/Yanyutin753/LambChat/releases/download/v2.8.1/LambChat-android-v2.8.1-signed.apk",
  );
});

test("returns null when no apk asset exists", () => {
  expect(matchAndroidApk([a("LambChat-v2.8.1-macOS.dmg")])).toBeNull();
  // iOS xcarchive 不是可安装包，不算 apk
  expect(
    matchAndroidApk([a("LambChat-ios-v2.8.1-unsigned-xcarchive.zip")]),
  ).toBeNull();
});

// ---------------------------------------------------------------------------
// formatAssetSize
// ---------------------------------------------------------------------------

test("formats asset sizes for humans", () => {
  expect(formatAssetSize(0)).toBe("0 B");
  expect(formatAssetSize(512)).toBe("512 B");
  expect(formatAssetSize(86_234_112)).toBe("82.2 MB");
  expect(formatAssetSize(1_400_000_000)).toBe("1.3 GB");
});

test("missing sizes format to an empty string", () => {
  expect(formatAssetSize(undefined)).toBe("");
  expect(formatAssetSize(null)).toBe("");
});
