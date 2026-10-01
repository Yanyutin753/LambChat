package com.lambchat.app;

import android.os.Bundle;
import android.view.View;
import android.webkit.WebView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

public class MainActivity extends BridgeActivity {

    // 最近一次系统栏 insets 生成的注入脚本；页面 reload 会清空 documentElement
    // 上的内联变量，加载完成时用它重放。
    private final AtomicReference<String> safeAreaScript =
            new AtomicReference<>(buildSafeAreaScript(0, 0, 0, 0, 0));

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 必须在 super.onCreate 之前注册：BridgeActivity.onCreate 末尾 load()
        // 即消费 bridgeBuilder 创建 bridge，晚于此注册插件不会生效
        registerPlugin(ApkInstallerPlugin.class);
        registerPlugin(UpdateDownloaderPlugin.class);
        super.onCreate(savedInstanceState);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);

        WebView webView = getBridge().getWebView();
        if (webView == null) {
            return;
        }

        // Android WebView 中 env(safe-area-inset-*) 恒为 0（即使 viewport-fit=cover），
        // edge-to-edge 下把系统栏/刘海 insets 注入为 CSS 变量，由 tokens.css 与 env() 取 max 合并。
        ViewCompat.setOnApplyWindowInsetsListener(webView, (v, windowInsets) -> {
            // 系统栏仍交给 CSS；IME 必须缩小整个 WebView，包含输入框弹层。
            // 关闭键盘时 imeBottom 为 0，恢复原来的可交互区域。
            int imeBottom = windowInsets.getInsets(WindowInsetsCompat.Type.ime()).bottom;
            View container = (View) webView.getParent();
            if (container.getPaddingBottom() != imeBottom) {
                container.setPadding(0, 0, 0, imeBottom);
            }
            Insets insets = windowInsets.getInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            float density = getResources().getDisplayMetrics().density;
            safeAreaScript.set(buildSafeAreaScript(
                    insets.top / density,
                    insets.bottom / density,
                    insets.left / density,
                    insets.right / density,
                    imeBottom / density));
            injectSafeArea(webView);
            return WindowInsetsCompat.CONSUMED;
        });
        ViewCompat.requestApplyInsets(webView);

        webView.setWebViewClient(new BridgeWebViewClient(getBridge()) {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                injectSafeArea(view);
            }
        });
    }

    private void injectSafeArea(WebView webView) {
        webView.evaluateJavascript(safeAreaScript.get(), null);
    }

    private static String buildSafeAreaScript(float top, float bottom, float left, float right, float keyboardHeight) {
        return String.format(Locale.US,
                "document.documentElement.style.setProperty('--app-native-safe-area-top','%fpx');"
                        + "document.documentElement.style.setProperty('--app-native-safe-area-bottom','%fpx');"
                        + "document.documentElement.style.setProperty('--app-native-safe-area-left','%fpx');"
                        + "document.documentElement.style.setProperty('--app-native-safe-area-right','%fpx');"
                        + "document.documentElement.style.setProperty('--app-native-keyboard-height','%fpx');",
                top, bottom, left, right, keyboardHeight);
    }
}
