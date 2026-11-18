package com.lambchat.app;

import android.app.UiAutomation;
import android.content.Context;
import android.os.ParcelFileDescriptor;
import androidx.test.platform.app.InstrumentationRegistry;
import com.lambchat.phone.PhoneAccessibility;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.regex.*;

public class PhoneScreenTest {
    private String shell(UiAutomation automation, String command) throws Exception {
        try (ParcelFileDescriptor fd = automation.executeShellCommand(command);
             InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(fd);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192]; int n; while ((n = input.read(buf)) != -1) out.write(buf, 0, n);
            return out.toString("UTF-8").trim();
        }
    }
    private int index(JSONObject state, String token) throws Exception {
        Matcher matcher = Pattern.compile("(?m)^(\\d+): .*" + Pattern.quote(token) + ".*$").matcher(state.getString("state"));
        assertTrue(state.toString(), matcher.find()); return Integer.parseInt(matcher.group(1));
    }
    @Test public void backgroundSnapshotSurvivesMainDisplayInteraction() throws Exception {
        String port = InstrumentationRegistry.getArguments().getString("connectPort");
        org.junit.Assume.assumeTrue(port != null);
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String target = InstrumentationRegistry.getInstrumentation().getContext().getPackageName();
        UiAutomation automation = InstrumentationRegistry.getInstrumentation().getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        String original = shell(automation, "settings get secure enabled_accessibility_services");
        String enabled = shell(automation, "settings get secure accessibility_enabled");
        com.lambchat.phone.PhoneControl.startBridge(context);
        try {
            shell(automation, "settings delete secure enabled_accessibility_services");
            Thread.sleep(300);
            shell(automation, "settings put secure enabled_accessibility_services " + context.getPackageName() + "/com.lambchat.phone.PhoneAccessibility");
            shell(automation, "settings put secure accessibility_enabled 1");
            for (int i=0; i<50 && PhoneAccessibility.instance == null; i++) Thread.sleep(100);
            assertNotNull(PhoneAccessibility.instance);
            com.lambchat.phone.PhoneControl.connect(context, Integer.parseInt(port), true);
            int display = com.lambchat.phone.PhoneControl.state().getInt("display");
            shell(automation, "am start -W --display " + display + " -n " + target + "/com.lambchat.fixture.PhoneFixtureActivity");
            Thread.sleep(700);
            JSONObject args = new JSONObject().put("name", target).put("session_id", "background-observation");
            JSONObject state = PhoneAccessibility.instance.execute("state", args, display);
            assertFalse(state.toString(), state.has("error"));
            shell(automation, "am start -W --display 0 -n com.android.settings/.Settings");
            Thread.sleep(500);
            JSONObject edit = new JSONObject(args.toString()).put("snapshot_id", state.getString("snapshot_id"))
                .put("target", new JSONObject().put("type", "element").put("index", index(state, "editable"))).put("value", "background-stable");
            JSONObject result = PhoneAccessibility.instance.execute("set_value", edit, display);
            assertTrue(result.toString(), result.optBoolean("ok"));
            assertEquals("stale_state", PhoneAccessibility.instance.execute("set_value", edit, display).getString("error"));
        } finally {
            com.lambchat.phone.PhoneControl.stopBridge();
            shell(automation, original.equals("null") || original.isEmpty() ? "settings delete secure enabled_accessibility_services" : "settings put secure enabled_accessibility_services " + original);
            shell(automation, "settings put secure accessibility_enabled " + (enabled.equals("1") ? "1" : "0"));
        }
    }
    @Test public void readsEditsClicksAndRejectsAReusedObservation() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String target = InstrumentationRegistry.getInstrumentation().getContext().getPackageName();
        UiAutomation automation = InstrumentationRegistry.getInstrumentation().getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        String original = shell(automation, "settings get secure enabled_accessibility_services");
        String enabled = shell(automation, "settings get secure accessibility_enabled");
        try {
            shell(automation, "settings delete secure enabled_accessibility_services");
            shell(automation, "settings put secure accessibility_enabled 0");
            Thread.sleep(500);
            shell(automation, "settings put secure enabled_accessibility_services " + context.getPackageName() + "/com.lambchat.phone.PhoneAccessibility");
            shell(automation, "settings put secure accessibility_enabled 1");
            shell(automation, "am start -W --display 0 -n " + target + "/com.lambchat.fixture.PhoneFixtureActivity");
            for (int i = 0; i < 100 && PhoneAccessibility.instance == null; i++) Thread.sleep(100);
            assertNotNull("Accessibility service did not connect: " + shell(automation, "dumpsys accessibility"), PhoneAccessibility.instance);
            Thread.sleep(700);
            JSONObject args = new JSONObject().put("name", target).put("session_id", "native-phone-test");
            JSONObject state = PhoneAccessibility.instance.execute("state", args, 0);
            assertFalse(state.toString(), state.has("error"));
            assertFalse("Offscreen rows must not become actionable", state.getString("state").contains("Fixture row 59"));
            JSONObject edit = new JSONObject(args.toString()).put("snapshot_id", state.getString("snapshot_id"))
                    .put("target", new JSONObject().put("type", "element").put("index", index(state, "editable"))).put("value", "安卓输入测试");
            assertTrue(PhoneAccessibility.instance.execute("set_value", edit, 0).optBoolean("ok"));
            assertEquals("stale_state", PhoneAccessibility.instance.execute("set_value", edit, 0).getString("error"));
            Thread.sleep(300);
            state = PhoneAccessibility.instance.execute("state", args, 0);
            assertTrue(state.toString(), state.getString("state").contains("安卓输入测试"));
            JSONObject click = new JSONObject(args.toString()).put("snapshot_id", state.getString("snapshot_id"))
                    .put("target", new JSONObject().put("type", "element").put("index", index(state, "Confirm fixture")));
            assertTrue(PhoneAccessibility.instance.execute("click", click, 0).optBoolean("ok"));
            Thread.sleep(300);
            state = PhoneAccessibility.instance.execute("state", new JSONObject(args.toString()).put("include_screenshot", true), 0);
            assertTrue(state.toString(), state.getString("state").contains("clicked 安卓输入测试"));
            byte[] pixels = android.util.Base64.decode(state.getJSONObject("screenshot").getString("data_b64"), android.util.Base64.DEFAULT);
            android.graphics.Bitmap frame = android.graphics.BitmapFactory.decodeByteArray(pixels, 0, pixels.length);
            assertNotNull("Screenshot could not be decoded", frame);
            try {
                // Sample inside the app content: system bars can look valid over a blank target.
                int reference = frame.getPixel(frame.getWidth() / 2, frame.getHeight() / 2);
                boolean hasContent = false;
                for (int y = frame.getHeight() / 4; y < 3 * frame.getHeight() / 4 && !hasContent; y += 3) {
                    for (int x = frame.getWidth() / 10; x < 9 * frame.getWidth() / 10; x += 3) {
                        if (frame.getPixel(x, y) != reference) { hasContent = true; break; }
                    }
                }
                assertTrue("Target app screenshot is blank", hasContent);
            } finally { frame.recycle(); }
        } finally {
            shell(automation, original.equals("null") || original.isEmpty() ? "settings delete secure enabled_accessibility_services" : "settings put secure enabled_accessibility_services " + original);
            shell(automation, "settings put secure accessibility_enabled " + (enabled.equals("1") ? "1" : "0"));
        }
    }
}
