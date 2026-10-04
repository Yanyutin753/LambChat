import { registerPlugin } from "@capacitor/core";

/**
 * Android 系统下载器桥（MainActivity 注册的 UpdateDownloaderPlugin）。
 *
 * 更新包 APK 走 DownloadManager 原生下载：无 CORS、不占 WebView 内存、
 * 系统级断点续传与下载通知。downloadId 以字符串往返（原生侧 Long.parseLong），
 * 规避各 Capacitor 版本 PluginCall 数值取值 API 差异。
 *
 * 版本化缓存语义（对齐主流移动客户端）：资产名带版本号即缓存键——
 * `status` 查到完整文件后直接 `ApkInstaller.installApk`，绝不重复下载；
 * `cleanup` 清掉旧版本残留包。
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

  /** 查目标文件是否已完整下载（应用专属 Downloads 目录，按文件名）。 */
  status(options: {
    fileName: string;
  }): Promise<{
    exists: boolean;
    size: number;
    /** 绝对路径（可直接交给 ApkInstaller.installApk） */
    path?: string;
  }>;

  /** 删除目录里其它残留 APK（keepFileName 保留当前目标版本）。 */
  cleanup(options: { keepFileName?: string }): Promise<{ removed: number }>;
}

export const UpdateDownloader =
  registerPlugin<UpdateDownloaderPlugin>("UpdateDownloader");
