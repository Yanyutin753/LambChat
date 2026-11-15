package com.lambchat.app;

import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.view.accessibility.*;
import androidx.test.platform.app.InstrumentationRegistry;
import com.getcapacitor.JSObject;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;

public class PhoneOverlayTest {
    private String shell(UiAutomation ui, String command) throws Exception {
        try (ParcelFileDescriptor descriptor = ui.executeShellCommand(command); InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(descriptor); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int size; while ((size = input.read(buffer)) != -1) output.write(buffer, 0, size);
            return output.toString("UTF-8").trim();
        }
    }
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node, String text) {
        if (node == null) return null;
        if (String.valueOf(node.getText()).contains(text) || String.valueOf(node.getContentDescription()).contains(text) || String.valueOf(node.getHintText()).contains(text)) return node;
        for (int i=0; i<node.getChildCount(); i++) { AccessibilityNodeInfo found = find(node.getChild(i), text); if (found != null) return found; }
        return null;
    }
    private AccessibilityNodeInfo scrollable(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (node.isScrollable()) return node;
        for (int i=0; i<node.getChildCount(); i++) { AccessibilityNodeInfo found = scrollable(node.getChild(i)); if (found != null) return found; }
        return null;
    }
    private AccessibilityNodeInfo find(UiAutomation ui, String text) {
        for (AccessibilityWindowInfo window : ui.getWindows()) { AccessibilityNodeInfo node = find(window.getRoot(), text); if (node != null) return node; }
        return null;
    }
    @Test public void floatingControlsExpandAcceptDraftAndHideWithoutStoppingRuntime() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String fixture = InstrumentationRegistry.getInstrumentation().getContext().getPackageName();
        UiAutomation ui = InstrumentationRegistry.getInstrumentation().getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        AccessibilityServiceInfo info = ui.getServiceInfo(); info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS; ui.setServiceInfo(info);
        LocalDeviceStore store = new LocalDeviceStore(context); JSONObject previous = store.read();
        boolean overlayWasEnabled = LocalDeviceOverlay.enabled(context);
        try {
            shell(ui, "appops set " + context.getPackageName() + " SYSTEM_ALERT_WINDOW allow");
            shell(ui, "am start -W -n " + context.getPackageName() + "/com.lambchat.app.MainActivity");
            store.save(new JSONObject().put("serverUrl", "http://127.0.0.1:9").put("pat", "phone-test-only").put("confirmPolicy", "all"));
            context.startForegroundService(new Intent(context, LocalDeviceService.class));
            for (int i=0; i<100 && !LocalDeviceService.status().equals("running"); i++) Thread.sleep(100);
            assertEquals("running", LocalDeviceService.status());
            LocalDevicePlugin.taskContext = new JSObject().put("scope", "overlay-test").put("ready", true);
            LocalDeviceOverlay.enable(context, true);
            shell(ui, "am start -W -n " + fixture + "/com.lambchat.fixture.PhoneFixtureActivity");
            LocalDeviceService.setAppVisible(false);
            AccessibilityNodeInfo header = null;
            for (int i=0; i<50 && header == null; i++) { Thread.sleep(100); header = find(ui, "LambChat ·"); }
            assertNotNull("Floating window missing", header);
            assertTrue(header.performAction(AccessibilityNodeInfo.ACTION_CLICK)); Thread.sleep(300);
            assertNotNull(find(ui, LocalDeviceOverlay.localizedContext(context).getString(R.string.phone_task_send)));
            AccessibilityNodeInfo field = find(ui, LocalDeviceOverlay.localizedContext(context).getString(R.string.phone_task_hint));
            assertNotNull("Task input missing", field);
            field.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
            Bundle value = new Bundle(); value.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "overlay-draft");
            assertTrue(field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, value));
            Thread.sleep(200); assertNotNull(find(ui, "overlay-draft"));
            AccessibilityNodeInfo hide = find(ui, LocalDeviceOverlay.localizedContext(context).getString(R.string.local_device_overlay_hide));
            for (int i=0; i<5 && (hide == null || !hide.isVisibleToUser()); i++) {
                for (AccessibilityWindowInfo window : ui.getWindows()) {
                    AccessibilityNodeInfo root = window.getRoot();
                    if (find(root, "LambChat ·") != null) {
                        AccessibilityNodeInfo scroll = scrollable(root);
                        if (scroll != null) scroll.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                    }
                }
                Thread.sleep(200); hide = find(ui, LocalDeviceOverlay.localizedContext(context).getString(R.string.local_device_overlay_hide));
            }
            assertNotNull(hide); assertTrue(hide.isVisibleToUser()); assertTrue(hide.performAction(AccessibilityNodeInfo.ACTION_CLICK)); Thread.sleep(300);
            assertNull(find(ui, "LambChat ·"));
            assertEquals("running", LocalDeviceService.status());
        } finally {
            LocalDevicePlugin.taskContext = new JSObject();
            LocalDeviceOverlay.enable(context, overlayWasEnabled);
            context.stopService(new Intent(context, LocalDeviceService.class));
            if (previous == null) store.clear(); else store.save(previous);
            shell(ui, "appops set " + context.getPackageName() + " SYSTEM_ALERT_WINDOW default");
        }
    }
}
