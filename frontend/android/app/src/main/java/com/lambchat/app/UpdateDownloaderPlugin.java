package com.lambchat.app;

import android.app.DownloadManager;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * 更新包原生下载桥（系统 DownloadManager）。
 *
 * WebView fetch 流式代理是 CORS/内存约束下的兜底；原生下载无 CORS、
 * 不占 WebView 内存、系统级断点续传与下载通知。目标为应用专属外部目录
 * （免存储权限），FileProvider 的 external-path 已覆盖，完成后 localUri
 * 直接交给 ApkInstaller 覆盖安装。
 *
 * downloadId 以字符串往返（Long.parseLong），避开各 Capacitor 版本
 * PluginCall 数值取值 API 差异。
 */
@CapacitorPlugin(name = "UpdateDownloader")
public class UpdateDownloaderPlugin extends Plugin {

    @PluginMethod
    public void start(PluginCall call) {
        String url = call.getString("url");
        String fileName = call.getString("fileName");
        if (url == null || url.isEmpty() || fileName == null || fileName.isEmpty()) {
            call.reject("url and fileName are required");
            return;
        }
        try {
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setDestinationInExternalFilesDir(
                    getContext(), Environment.DIRECTORY_DOWNLOADS, fileName);
            // 可见通知：免 DOWNLOAD_WITHOUT_NOTIFICATION 权限，大文件下载进度
            // 对用户可见，完成后保留
            request.setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setTitle(fileName);
            DownloadManager dm = (DownloadManager) getContext()
                    .getSystemService(Context.DOWNLOAD_SERVICE);
            if (dm == null) {
                call.reject("DownloadManager unavailable");
                return;
            }
            long id = dm.enqueue(request);
            JSObject ret = new JSObject();
            ret.put("downloadId", Long.toString(id));
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("enqueue failed: " + e.getMessage());
        }
    }

    @PluginMethod
    public void progress(PluginCall call) {
        String idRaw = call.getString("downloadId", "");
        long id;
        try {
            id = Long.parseLong(idRaw);
        } catch (NumberFormatException e) {
            call.reject("invalid downloadId");
            return;
        }
        DownloadManager dm = (DownloadManager) getContext()
                .getSystemService(Context.DOWNLOAD_SERVICE);
        if (dm == null) {
            call.reject("DownloadManager unavailable");
            return;
        }
        try (Cursor c = dm.query(new DownloadManager.Query().setFilterById(id))) {
            if (c == null || !c.moveToFirst()) {
                call.reject("download not found");
                return;
            }
            int status = c.getInt(c.getColumnIndex(DownloadManager.COLUMN_STATUS));
            long soFar = c.getLong(c.getColumnIndex(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
            long total = c.getLong(c.getColumnIndex(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));

            JSObject ret = new JSObject();
            ret.put("status", mapStatus(status));
            ret.put("bytesSoFar", soFar);
            ret.put("totalBytes", total); // 服务端不回 content-length 时为 -1
            if (status == DownloadManager.STATUS_SUCCESSFUL) {
                int uriIdx = c.getColumnIndex(DownloadManager.COLUMN_LOCAL_URI);
                if (uriIdx >= 0) {
                    ret.put("localUri", c.getString(uriIdx));
                }
            }
            if (status == DownloadManager.STATUS_FAILED) {
                int reasonIdx = c.getColumnIndex(DownloadManager.COLUMN_REASON);
                ret.put("reason", reasonIdx >= 0 ? c.getInt(reasonIdx) : 0);
            }
            call.resolve(ret);
        }
    }

    private static String mapStatus(int status) {
        if (status == DownloadManager.STATUS_SUCCESSFUL) {
            return "success";
        }
        if (status == DownloadManager.STATUS_FAILED) {
            return "failed";
        }
        if (status == DownloadManager.STATUS_PAUSED) {
            return "paused";
        }
        if (status == DownloadManager.STATUS_PENDING) {
            return "pending";
        }
        return "running";
    }
}
