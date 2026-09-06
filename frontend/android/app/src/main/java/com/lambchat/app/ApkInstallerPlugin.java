package com.lambchat.app;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;

/**
 * APK 覆盖安装：ACTION_VIEW + FileProvider 拉起系统包安装器。
 * Share（ACTION_SEND）只会打开分享面板，无法触发安装，故走专用插件。
 */
@CapacitorPlugin(name = "ApkInstaller")
public class ApkInstallerPlugin extends Plugin {

    @PluginMethod
    public void installApk(PluginCall call) {
        String path = call.getString("path");
        if (path == null || path.isEmpty()) {
            call.reject("path is required");
            return;
        }
        File apk = new File(Uri.parse(path).getPath());
        if (!apk.exists()) {
            call.reject("APK file not found: " + path);
            return;
        }
        Context context = getContext();
        Uri contentUri = FileProvider.getUriForFile(
                context, context.getPackageName() + ".fileprovider", apk);

        // Android 8+ 需「允许安装未知应用」授权；未授权先带用户去设置页，
        // 返回 status="settings" 由前端提示授权后重试
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !context.getPackageManager().canRequestPackageInstalls()) {
            Intent settings = new Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + context.getPackageName()));
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(settings);
            resolve(call, "settings");
            return;
        }

        Intent install = new Intent(Intent.ACTION_VIEW);
        install.setDataAndType(contentUri, "application/vnd.android.package-archive");
        install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        install.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(install);
        resolve(call, "installer");
    }

    private static void resolve(PluginCall call, String status) {
        JSObject ret = new JSObject();
        ret.put("status", status);
        call.resolve(ret);
    }
}
