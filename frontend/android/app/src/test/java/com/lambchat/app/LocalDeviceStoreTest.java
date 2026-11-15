package com.lambchat.app;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.File;

public class LocalDeviceStoreTest {
    @Test public void bindsCredentialsToNormalizedOrigin() throws Exception {
        assertEquals("https://chat.example", LocalDeviceStore.origin("https://CHAT.example:443/api"));
        assertEquals("http://127.0.0.1:8000", LocalDeviceStore.origin("http://127.0.0.1:8000"));
    }
    @Test public void refusesRemotePlaintextAndCredentialUrls() {
        for (String url : new String[]{"http://chat.example", "https://user:pass@chat.example", "https://chat.example?token=x", "https://chat.example#x"}) {
            assertThrows(Exception.class, () -> LocalDeviceStore.origin(url));
        }
    }
    @Test public void refusesWorkspaceTraversal() throws Exception {
        File root = new File(System.getProperty("java.io.tmpdir"), "workspace");
        assertEquals(new File(root, "report.txt"), LocalDeviceRuntime.child(root, "report.txt"));
        for (String path : new String[]{"../pat", "/absolute", "nested/../../escape", "a\\b"})
            assertThrows(Exception.class, () -> LocalDeviceRuntime.child(root, path));
    }
}
