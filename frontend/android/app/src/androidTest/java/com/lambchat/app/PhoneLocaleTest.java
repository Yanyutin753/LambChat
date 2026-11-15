package com.lambchat.app;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import static org.junit.Assert.*;

public class PhoneLocaleTest {
    @Test public void approvalTranslationPreservesOperationAndScreenshotDisclosure() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String operation = "{\"action\":\"state\",\"name\":\"test.app\"}";
        String rendered = LocalDeviceOverlay.approvalMessage(context, "Computer control on machine abc: " + operation + " (includes a screenshot sent to the model)");
        assertTrue(rendered.contains(operation));
        assertTrue(rendered.contains(context.getString(R.string.phone_control_screenshot_notice)));
        assertEquals("Custom approval", LocalDeviceOverlay.approvalMessage(context, "Custom approval"));
    }
    @Test public void floatingResourcesFollowSavedAppLanguage() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.content.SharedPreferences prefs = context.getSharedPreferences("local-device-overlay", Context.MODE_PRIVATE);
        String previous = prefs.getString("language", "");
        try {
            String[] languages = {"zh", "ja", "ko", "ru", "en"};
            String[] labels = {"批准", "承認", "승인", "Подтвердить", "Approve"};
            for (int i=0; i<languages.length; i++) {
                prefs.edit().putString("language", languages[i]).commit();
                assertEquals(labels[i], LocalDeviceOverlay.localizedContext(context).getString(R.string.phone_approve));
            }
        } finally { prefs.edit().putString("language", previous).commit(); }
    }
}
