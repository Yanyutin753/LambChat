import { registerPlugin } from "@capacitor/core";

/**
 * Android 系统下载器桥（MainActivity 注册的 UpdateDownloaderPlugin）。
 *
 * 更新包 APK 走 DownloadManager 原生下载：无 CORS、不占 WebView 内存、
 * 系统级断点续传与下载通知。downloadId 以字符串往返（原生侧 Long.parseLong），
 * 规避各 Capacitor 版本 PluginCall 数值取值 API 差异。
 */
export interface UpdateDownloaderPlugin {
  start(options: {
    url: string;
    fileName: string;
  }): Promise<{ downloadId: string }>;

  progress(options: { downloadId: string }): Promise<{
    status: "pending" | "running" | "paused" | "success" | "failed";
    bytesSoFar: number;
    totalBytes: number; // 服务端不回 content-length 时为 -1
    localUri?: string;
    reason?: number;
  }>;
}

export const UpdateDownloader =
  registerPlugin<UpdateDownloaderPlugin>("UpdateDownloader");
