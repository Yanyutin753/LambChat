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
  const bridge = readRepoFile(
    "frontend/src/services/capacitor/apkInstaller.ts",
  );
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
  const manifest = readRepoFile(
    "frontend/android/app/src/main/AndroidManifest.xml",
  );
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

test("installAndroidUpdate tries native downloader before WebView fallback", () => {
  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  const nativeCall = hook.indexOf("installAndroidUpdateViaNative(");
  const webviewCall = hook.indexOf("installAndroidUpdateViaWebViewStream(");
  // 原生优先、WebView 兜底——旧壳/系统裁剪下原生桥不可用时兼容网仍在
  expect(nativeCall).toBeGreaterThan(-1);
  expect(webviewCall).toBeGreaterThan(nativeCall);
  // 两条链路共用同一自托管代理 URL（保住服务端可达 GitHub 的转发语义）
  expect(
    hook.match(/buildReleaseAssetDownloadUrl\(/g)?.length,
  ).toBeGreaterThanOrEqual(2);
});

test("UpdateDownloader bridge polls progress with string downloadId", () => {
  const bridge = readRepoFile(
    "frontend/src/services/capacitor/updateDownloader.ts",
  );
  expect(bridge).toMatch(/registerPlugin/);
  expect(bridge).toMatch(/"UpdateDownloader"/);
  // downloadId 字符串往返：规避各 Capacitor 版本 PluginCall 数值取值差异
  expect(bridge).toMatch(/downloadId: string/);

  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  expect(hook).toMatch(/UpdateDownloader\.progress\(\{ downloadId \}\)/);
});

test("MainActivity registers UpdateDownloaderPlugin before the bridge loads", () => {
  const main = readRepoFile(
    "frontend/android/app/src/main/java/com/lambchat/app/MainActivity.java",
  );
  expect(main).toMatch(/registerPlugin\(UpdateDownloaderPlugin\.class\);/);
  const registerIdx = main.indexOf(
    "registerPlugin(UpdateDownloaderPlugin.class);",
  );
  const superIdx = main.indexOf("super.onCreate(");
  expect(registerIdx).toBeGreaterThan(-1);
  expect(superIdx).toBeGreaterThan(registerIdx);
});

test("UpdateDownloaderPlugin downloads to app-private external dir via DownloadManager", () => {
  const plugin = readRepoFile(
    "frontend/android/app/src/main/java/com/lambchat/app/UpdateDownloaderPlugin.java",
  );
  // 应用专属外部目录：免存储权限，且 FileProvider external-path 已覆盖
  expect(plugin).toMatch(/setDestinationInExternalFilesDir/);
  expect(plugin).toMatch(/DownloadManager\.COLUMN_STATUS/);
  expect(plugin).toMatch(/COLUMN_LOCAL_URI/);
  // 原生侧 Long.parseLong 消费字符串 id
  expect(plugin).toMatch(/Long\.parseLong/);
});

test("tauri updater keeps proxy fallback endpoint for manifest fetch", () => {
  // 桌面更新器清单拉取：GitHub 直连不稳（国内）时回退自托管同源代理。
  // 端点按序尝试是 tauri-plugin-updater 的内建语义。
  const conf = readRepoFile("frontend/src-tauri/tauri.conf.json");
  const endpoints = /"endpoints":\s*\[([\s\S]*?)\]/.exec(conf)?.[1] ?? "";
  expect(endpoints).toMatch(
    /github\.com\/Yanyutin753\/LambChat\/releases\/latest\/download\/latest\.json/,
  );
  expect(endpoints).toMatch(
    /lambchat\.com\/api\/version\/assets\/latest\.json\/download/,
  );
});

test("linux package update flow routes deb/rpm through the package manager path", () => {
  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  // 来源检测 → 分流：deb/rpm 走「下载 + pkexec 安装」而非 updater
  expect(hook).toMatch(/getLinuxInstallInfo/);
  expect(hook).toMatch(/installLinuxPackage\(/);
  expect(hook).toMatch(/buildLinuxPackageAssetName/);
  expect(hook).toMatch(/buildLinuxPackageDownloadUrl/);
  // deb/rpm 不进 updater 后台静默下载——它只会拉 AppImage 且装不上系统包
  expect(hook).toMatch(/linuxSource !== "deb" && linuxSource !== "rpm"/);
  // unknown 来源不盲装，回落下载页
  expect(hook).toMatch(/buildApiUrl\("\/download"\)/);
});

test("linux update service bridges the rust commands and progress event", () => {
  const service = readRepoFile("frontend/src/services/tauri/linuxUpdate.ts");
  expect(service).toMatch(/get_linux_install_source/);
  expect(service).toMatch(/install_linux_package/);
  expect(service).toMatch(/linux-update-progress/);
});

test("rust side detects install source and installs deb/rpm via pkexec", () => {
  const rust = readRepoFile("frontend/src-tauri/src/linux_update.rs");
  // 检测序：AppImage 扩展名 → dpkg/rpm 包归属反查 → 系统前缀启发式
  expect(rust).toMatch(/is_appimage_path/);
  expect(rust).toMatch(/"dpkg", "-S"/);
  expect(rust).toMatch(/"rpm", "-qf"/);
  expect(rust).toMatch(/fallback_install_source/);
  // deb → apt、rpm → dnf，pkexec 提权
  expect(rust).toMatch(/"apt"/);
  expect(rust).toMatch(/"dnf"/);
  expect(rust).toMatch(/"pkexec"/);
  // 命令注册进 invoke handler（缺注册前端 invoke 直接挂）
  const lib = readRepoFile("frontend/src-tauri/src/lib.rs");
  expect(lib).toMatch(/linux_update::get_linux_install_source/);
  expect(lib).toMatch(/linux_update::install_linux_package/);
});

test("download-and-install copy exists in all five locales", () => {
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const data = JSON.parse(
      readRepoFile(`frontend/src/i18n/locales/${locale}.json`),
    ) as Record<string, string>;
    expect(data.updateDownloadAndInstall, locale).toBeTruthy();
  }
});

test("release workflow asset naming keeps the deb/rpm contract", () => {
  // CI 收集产物名 LambChat-${RELEASE_TAG}-Linux-${arch}.deb|.rpm 必须与
  // buildLinuxPackageAssetName 拼出的名字一致（数值用例见 linuxUpdateAssets.test.ts）
  const wf = readRepoFile(".github/workflows/app-release.yml");
  expect(wf).toMatch(/LambChat-\$\{RELEASE_TAG\}-Linux-\$\{arch\}\.deb/);
  expect(wf).toMatch(/LambChat-\$\{RELEASE_TAG\}-Linux-\$\{arch\}\.rpm/);
});

test("update flow is single-flight: downloads guarded by in-flight flag, re-checks preserve progress", () => {
  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  // 在飞标志存在且三条下载路径（后台/AppImage 前台/Linux 包管理器）都先查它
  expect(hook).toMatch(/const downloadInFlightRef = useRef\(false\)/);
  const guards = hook.match(/if \(downloadInFlightRef\.current\) return/g) ?? [];
  expect(guards.length).toBe(2); // installTauriUpdate + installLinuxPackageUpdate
  // 后台下载卫兵 = pending(已完成) + inFlight(进行中) 双查——单查完成标志
  // 会在下载中放行第二条下载（多进度条/并发下载根因）
  expect(hook).toMatch(
    /if \(pendingUpdateRef\.current \|\| downloadInFlightRef\.current\) return/,
  );
  // 失败路径必须复位在飞标志（否则一次失败永久卡死后续下载）
  const resets = hook.match(/downloadInFlightRef\.current = false/g) ?? [];
  expect(resets.length).toBeGreaterThanOrEqual(4);
  // 复检不能清掉进行中下载/待安装态（进度条中途消失重来的来源）
  expect(hook).toMatch(/const preserve =\n\s+downloadInFlightRef\.current \|\| pendingUpdateRef\.current !== null/);
  // 迟到的 Linux 进度事件不污染非下载态
  expect(hook).toMatch(/if \(!prev\.downloading\) return prev/);
});

test("manual update check distinguishes failure from up-to-date", () => {
  const hook = readRepoFile("frontend/src/hooks/useAutoUpdate.ts");
  // 检查失败不得伪装成「已是最新」；两条检查路径都返回成败
  expect(hook).toMatch(/updateCheckFailed/);
  expect(hook).toMatch(/ok = await checkTauriUpdate\(background, manual\)/);
  expect(hook).toMatch(/ok = await checkBackendUpdate\(background, manual\)/);

  // 失败文案五语齐
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const data = JSON.parse(
      readRepoFile(`frontend/src/i18n/locales/${locale}.json`),
    ) as Record<string, string>;
    expect(data.updateCheckFailed, locale).toBeTruthy();
  }
});
