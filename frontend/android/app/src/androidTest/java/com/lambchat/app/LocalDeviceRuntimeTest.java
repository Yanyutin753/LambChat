package com.lambchat.app;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.Assume;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

/** Run only on real Android arm64; host tests cannot certify PRoot or native loading. */
public class LocalDeviceRuntimeTest {
    @Test public void bundledRuntimeRunsPythonNodeShellAndFiles() throws Exception {
        Assume.assumeTrue(LocalDeviceRuntime.supported());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = LocalDeviceRuntime.install(context);
        String script = "set -eu; d=$(mktemp -d /lambchat/workspaces/.shared/smoke.XXXXXX); "
                + "trap 'rm -rf \"$d\"' EXIT; export D=\"$d\"; "
                + "python3 -c 'import httpx, psutil, ssl, os; from lambchat_sandbox.android import parse_pairing; open(os.environ[\"D\"]+\"/result\",\"w\").write(\"python\")'; "
                + "node -e 'require(\"fs\").appendFileSync(process.env.D+\"/result\",\"-node\")'; "
                + "test \"$(cat \"$d/result\")\" = python-node; echo local-device-ok";
        Process process = LocalDeviceRuntime.command(context, root, Arrays.asList("/bin/sh", "-c", script));
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        Thread drain = new Thread(() -> { try { byte[] buf = new byte[4096]; int n; while ((n=process.getInputStream().read(buf))!=-1) { synchronized(output) { if (output.size()<65536) output.write(buf,0,n); } } } catch (IOException ignored) { } });
        drain.start();
        try {
            assertTrue("Runtime timed out", process.waitFor(60, TimeUnit.SECONDS));
            drain.join(3000);
            assertEquals(output.toString("UTF-8"), 0, process.exitValue());
            assertTrue(output.toString("UTF-8").contains("local-device-ok"));
        } finally { process.destroyForcibly(); }
    }

    @Test public void killingLauncherStopsDescendantCommands() throws Exception {
        Assume.assumeTrue(LocalDeviceRuntime.supported());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = LocalDeviceRuntime.install(context);
        String marker = "cancel-" + java.util.UUID.randomUUID();
        File file = new File(new LocalDeviceStore(context).home(), "workspaces/.shared/" + marker);
        Process process = LocalDeviceRuntime.command(context, root, Arrays.asList("/bin/sh", "-c",
                "(sleep 4; echo leaked > /lambchat/workspaces/.shared/" + marker + ") & echo ready; wait"));
        try {
            java.util.concurrent.CompletableFuture<String> ready = java.util.concurrent.CompletableFuture.supplyAsync(() -> {
                try { return new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)).readLine(); }
                catch (IOException e) { throw new java.util.concurrent.CompletionException(e); }
            });
            assertEquals("ready", ready.get(20, TimeUnit.SECONDS));
            process.destroyForcibly();
            assertTrue(process.waitFor(5, TimeUnit.SECONDS));
            Thread.sleep(5000);
            assertFalse("Descendant outlived local device", Files.exists(file.toPath()));
        } finally { process.destroyForcibly(); Files.deleteIfExists(file.toPath()); }
    }
}
