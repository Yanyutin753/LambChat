package com.lambchat.app;

import android.content.Context;
import android.os.Bundle;
import androidx.test.platform.app.InstrumentationRegistry;
import com.lambchat.phone.PhoneControl;
import org.junit.Test;
import static org.junit.Assert.*;

/** Opt-in test against the system's live wireless-debugging pairing dialog. */
public class PhonePairingTest {
    @Test public void pairsWithSystemAdbAndConnectsUsingSavedIdentity() throws Exception {
        Bundle args = InstrumentationRegistry.getArguments();
        org.junit.Assume.assumeTrue(args.containsKey("pairPort"));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PhoneControl.pair(context, Integer.parseInt(args.getString("pairPort")), args.getString("pairCode"));
        PhoneControl.startBridge(context);
        try {
            PhoneControl.connect(context, Integer.parseInt(args.getString("connectPort")), true);
            assertTrue(PhoneControl.state().getBoolean("connected"));
            assertTrue(PhoneControl.state().getInt("display") > 0);
            PhoneControl.disconnect();
            PhoneControl.connect(context, Integer.parseInt(args.getString("connectPort")), false);
            assertTrue(PhoneControl.state().getBoolean("connected"));
            assertEquals(0, PhoneControl.state().getInt("display"));
        } finally { PhoneControl.stopBridge(); }
    }
}
