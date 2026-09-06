import { registerPlugin } from "@capacitor/core";

/**
 * Android 原生 APK 安装桥（MainActivity 注册的 ApkInstallerPlugin）。
 *
 * 用 ACTION_VIEW + FileProvider 拉起系统包安装器完成覆盖更新；
 * @capacitor/share 的 ACTION_SEND 只会打开分享面板，无法触发安装。
 *
 * Android 8+ 需「允许安装未知应用」授权：未授权时原生侧跳转设置页，
 * 返回 status="settings"，由前端提示用户授权后重试。
 */
export interface ApkInstallerPlugin {
  installApk(options: { path: string }): Promise<{
    status: "installer" | "settings";
  }>;
}

export const ApkInstaller = registerPlugin<ApkInstallerPlugin>("ApkInstaller");
