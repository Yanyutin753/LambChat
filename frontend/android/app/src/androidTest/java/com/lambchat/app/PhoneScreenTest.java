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
            shell(automation, "am start -W -n " + target + "/com.lambchat.fixture.PhoneFixtureActivity");
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
            assertTrue(state.getJSONObject("screenshot").getString("data_b64").length() > 100);
        } finally {
            shell(automation, original.equals("null") || original.isEmpty() ? "settings delete secure enabled_accessibility_services" : "settings put secure enabled_accessibility_services " + original);
            shell(automation, "settings put secure accessibility_enabled " + (enabled.equals("1") ? "1" : "0"));
        }
    }
}
