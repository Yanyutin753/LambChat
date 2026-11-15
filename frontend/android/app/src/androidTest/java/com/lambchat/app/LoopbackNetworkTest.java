package com.lambchat.app;

import android.security.NetworkSecurityPolicy;
import org.junit.Test;
import static org.junit.Assert.*;

public class LoopbackNetworkTest {
    @Test public void permitsLocalDevelopmentServerButRejectsRemoteCleartext() {
        NetworkSecurityPolicy policy = NetworkSecurityPolicy.getInstance();
        assertTrue(policy.isCleartextTrafficPermitted("127.0.0.1"));
        assertTrue(policy.isCleartextTrafficPermitted("localhost"));
        assertFalse(policy.isCleartextTrafficPermitted("example.com"));
        assertFalse(policy.isCleartextTrafficPermitted("192.168.1.1"));
    }
}
