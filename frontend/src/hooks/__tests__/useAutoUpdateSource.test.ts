import { existsSync, readFileSync } from "node:fs";

/**
 * Source-string tests for the mobile auto-update chain:
 * 客户端版本上报 → APK 下载 → 原生 ACTION_VIEW 安装（Share 分享面板装不了包）。
 */

function readRepoFile(path: string): string {
  const url = new URL(`../../../../${path}`, import.meta.url);
  if (!existsSync(url)) {
    throw new Error(`repo file not found: ${path}`);
  }
  return readFileSync(url, "utf8");
}

test("version service reports the bundled client version on update checks", () => {
  const service = readRepoFile("frontend/src/services/api/version.ts");
  expect(service).toMatch(/client_version/);
  expect(service).toMatch(/checkForUpdates\(clientVersion/);

  // 客户端版本来自构建期打包的 package.json（与 versionName 同源）
  const appVersion = readRepoFile("frontend/src/utils/appVersion.ts");
  expect(appVersion).toMatch(/package\.json/);
  expect(appVersion).toMatch(/APP_VERSION/);
});

test("useAutoUpdate checks updates with the client version and installs via native installer", () => {
  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  // 上报客户端版本而非依赖服务端版本
  expect(hook).toMatch(/checkForUpdates\(APP_VERSION\)/);
  // 安装走原生 ApkInstaller，不再用 Share（ACTION_SEND 只开分享面板）
  expect(hook).not.toMatch(/@capacitor\/share/);
  expect(hook).toMatch(/ApkInstaller/);
  expect(hook).toMatch(/installApk/);
  // 未授予「安装未知应用」时原生返回 settings 状态，前端要提示授权
  expect(hook).toMatch(/installPermissionHint/);
});

test("ApkInstaller bridge registers the native Capacitor plugin", () => {
  const bridge = readRepoFile("frontend/src/services/capacitor/apkInstaller.ts");
  expect(bridge).toMatch(/registerPlugin/);
  expect(bridge).toMatch(/"ApkInstaller"/);
  expect(bridge).toMatch(/installApk/);
});

test("MainActivity registers ApkInstallerPlugin before the bridge loads", () => {
  const main = readRepoFile(
    "frontend/android/app/src/main/java/com/lambchat/app/MainActivity.java",
  );
  expect(main).toMatch(/registerPlugin\(ApkInstallerPlugin\.class\);/);
  // BridgeActivity.onCreate 末尾 load() 即消费 bridgeBuilder，注册必须在其之前
  const registerIdx = main.indexOf("registerPlugin(ApkInstallerPlugin.class);");
  const superIdx = main.indexOf("super.onCreate(");
  expect(registerIdx).toBeGreaterThan(-1);
  expect(superIdx).toBeGreaterThan(registerIdx);
});

test("ApkInstallerPlugin opens the system installer via ACTION_VIEW", () => {
  const plugin = readRepoFile(
    "frontend/android/app/src/main/java/com/lambchat/app/ApkInstallerPlugin.java",
  );
  expect(plugin).toMatch(/Intent\.ACTION_VIEW/);
  expect(plugin).toMatch(/application\/vnd\.android\.package-archive/);
  expect(plugin).toMatch(/FileProvider\.getUriForFile/);
  expect(plugin).toMatch(/canRequestPackageInstalls/);
  expect(plugin).toMatch(/ACTION_MANAGE_UNKNOWN_APP_SOURCES/);
  expect(plugin).toMatch(/"settings"/);
  expect(plugin).toMatch(/"installer"/);
});

test("Android manifest keeps the install permission for in-app updates", () => {
  const manifest = readRepoFile("frontend/android/app/src/main/AndroidManifest.xml");
  expect(manifest).toMatch(/REQUEST_INSTALL_PACKAGES/);
});

test("install permission hint copy exists in all five locales", () => {
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const data = JSON.parse(
      readRepoFile(`frontend/src/i18n/locales/${locale}.json`),
    ) as { update: Record<string, string> };
    expect(data.update.installPermissionHint, locale).toBeTruthy();
  }
});
