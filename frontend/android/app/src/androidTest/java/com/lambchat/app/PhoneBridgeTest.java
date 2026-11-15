package com.lambchat.app;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import com.lambchat.phone.PhoneControl;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

public class PhoneBridgeTest {
    @Test public void bridgeRequiresSecretAndReportsDisconnectedWithoutExecuting() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PhoneControl.startBridge(context);
        File path = new File(context.getNoBackupFilesDir(), "local-device/phone-bridge.json");
        try {
            JSONObject config = new JSONObject(new String(Files.readAllBytes(path.toPath()), StandardCharsets.UTF_8));
            try (Socket socket = new Socket("127.0.0.1", config.getInt("port"))) {
                socket.setSoTimeout(3000);
                socket.getOutputStream().write((new JSONObject().put("token", "wrong").put("op", "cua_apps").put("payload", new JSONObject()).toString()+"\n").getBytes(StandardCharsets.UTF_8));
                assertEquals(-1, socket.getInputStream().read());
            }
            try (Socket socket = new Socket("127.0.0.1", config.getInt("port"))) {
                socket.setSoTimeout(3000);
                socket.getOutputStream().write((new JSONObject().put("token", config.getString("token")).put("op", "cua_apps").put("payload", new JSONObject().put("session_id", "test")).toString()+"\n").getBytes(StandardCharsets.UTF_8));
                JSONObject result = new JSONObject(new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8)).readLine());
                assertEquals("phone_control_paused_or_disconnected", result.getString("error"));
            }
        } finally { PhoneControl.stopBridge(); }
        assertFalse(path.exists());
    }
}
