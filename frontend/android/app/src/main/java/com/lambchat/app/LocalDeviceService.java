package com.lambchat.app;

import android.app.*;
import android.content.Intent;
import android.os.IBinder;
import androidx.core.app.NotificationCompat;
import org.json.JSONObject;
import java.io.InputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** Owns one daemon; Android task removal and explicit disconnect stop its process tree. */
public class LocalDeviceService extends Service {
    static final ExecutorService OPERATIONS = Executors.newSingleThreadExecutor();
    private static volatile Process process;
    private static volatile LocalDeviceService instance;
    private static volatile boolean appVisible = true;
    private final android.os.Handler main = new android.os.Handler(android.os.Looper.getMainLooper());
    private LocalDeviceOverlay overlay;

    static void overlayDraft(String text) {
        LocalDeviceService current = instance;
        if (current != null) current.main.post(() -> { if (current.overlay != null) current.overlay.draft(text); });
    }
    void captureForTask() {
        if (overlay != null) overlay.hide();
        main.postDelayed(() -> OPERATIONS.execute(() -> {
            try {
                com.lambchat.phone.PhoneAccessibility screen = com.lambchat.phone.PhoneAccessibility.instance;
                if (screen == null) throw new IllegalStateException("Screen access required");
                JSONObject shot = screen.captureForUser();
                java.io.File root = new java.io.File(new LocalDeviceStore(this).home(), "workspaces/.shared");
                root.mkdirs();
                if (java.nio.file.Files.isSymbolicLink(root.toPath()) || java.nio.file.Files.isSymbolicLink(root.getParentFile().toPath())) throw new java.io.IOException("Invalid workspace");
                String name = "phone-screen-" + java.util.UUID.randomUUID() + ".jpg";
                java.io.File file = LocalDeviceRuntime.child(root, name);
                java.nio.file.Files.write(file.toPath(), android.util.Base64.decode(shot.getString("data_b64"), android.util.Base64.DEFAULT), java.nio.file.StandardOpenOption.CREATE_NEW);
                overlayDraft(getString(R.string.phone_screenshot_path, "/workspace/.shared/" + name));
            } catch (Exception e) { overlayResult(false); }
            finally { refreshOverlay(); }
        }), 200);
    }
    static void overlayResult(boolean accepted) {
        LocalDeviceService current = instance;
        if (current != null) current.main.post(() -> { if (current.overlay != null) current.overlay.result(accepted); });
    }
    static void setAppVisible(boolean visible) { appVisible = visible; refreshOverlay(); }
    static void refreshOverlay() {
        LocalDeviceService current = instance;
        if (current != null) current.main.post(() -> {
            if (instance == current && current.overlay != null) { current.overlay.visibility(!appVisible && !stopping); current.overlay.refresh(); }
        });
    }

    private void activity(String line, Process current, int run) {
        if (!line.startsWith("LAMBCHAT_DEVICE_STATE ")) return;
        try {
            JSONObject state = new JSONObject(line.substring("LAMBCHAT_DEVICE_STATE ".length()));
            String kind = state.getString("state"); int active = state.getInt("active");
            if (!java.util.Arrays.asList("connecting", "offline", "idle", "executing", "completed", "failed").contains(kind) || active < 0 || active > 64) return;
            main.post(() -> { if (process == current && generation == run && overlay != null) overlay.update(kind, active); });
        } catch (Exception ignored) { /* Only bounded status frames are displayable. */ }
    }
    private static volatile boolean preparing;
    private static volatile boolean stopping;
    private static volatile boolean failed;
    private static volatile int generation;
    private android.net.ConnectivityManager.NetworkCallback networkCallback;
    private volatile java.io.File runtimeRoot;
    private static final int NOTIFICATION = 417;
    private static final String CHANNEL = "local-device";

    static String status() {
        if (!LocalDeviceRuntime.supported()) return "unsupported";
        if (failed) return "error";
        Process current = process;
        return preparing ? "starting" : current != null && current.isAlive() ? "running" : "stopped";
    }

    static void stopProcess() throws Exception {
        com.lambchat.phone.PhoneControl.pause();
        generation++;
        Process old = process; process = null;
        if (old != null) {
            old.destroy();
            if (!old.waitFor(3, TimeUnit.SECONDS)) {
                old.destroyForcibly();
                if (!old.waitFor(3, TimeUnit.SECONDS)) throw new IllegalStateException("Device runtime did not stop");
            }
        }
    }

    @Override public void onCreate() {
        super.onCreate();
        instance = this;
        com.lambchat.phone.PhoneControl.startBridge(this);
        overlay = new LocalDeviceOverlay(this);
        networkCallback = new android.net.ConnectivityManager.NetworkCallback() {
            @Override public void onLinkPropertiesChanged(android.net.Network network, android.net.LinkProperties properties) {
                OPERATIONS.execute(() -> {
                    java.io.File root = runtimeRoot;
                    if (root != null) try { LocalDeviceRuntime.configureDns(LocalDeviceService.this, root); }
                    catch (Exception ignored) { /* Existing daemon reconnects when the network returns. */ }
                });
            }
        };
        getSystemService(android.net.ConnectivityManager.class).registerDefaultNetworkCallback(networkCallback);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        stopping = false;
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, getString(R.string.local_device_title), NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, LocalDeviceService.class).setAction("stop"), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        startForeground(NOTIFICATION, new NotificationCompat.Builder(this, CHANNEL)
                .setSmallIcon(R.mipmap.ic_launcher).setContentTitle(getString(R.string.local_device_title))
                .setContentText(getString(R.string.local_device_notification)).setContentIntent(open).setOngoing(true)
                .addAction(0, getString(R.string.local_device_stop), stop).build());
        if (intent != null && "stop".equals(intent.getAction())) {
            stopping = true;
            OPERATIONS.execute(() -> { try { stopProcess(); } catch (Exception e) { failed = true; } stopSelf(startId); });
            return START_NOT_STICKY;
        }
        preparing = true;
        if (overlay != null) overlay.update("connecting", 0);
        refreshOverlay();
        OPERATIONS.execute(() -> {
            try {
                failed = false;
                stopProcess();
                if (!LocalDeviceRuntime.supported()) throw new IllegalStateException("Unsupported device");
                JSONObject pairing = new LocalDeviceStore(this).read();
                if (pairing == null) throw new IllegalStateException("Device is not paired");
                java.io.File root = LocalDeviceRuntime.install(this);
                if (stopping) return;
                LocalDeviceRuntime.configureDns(this, root);
                runtimeRoot = root;
                Process current = LocalDeviceRuntime.start(this, root, pairing);
                process = current;
                final int run = generation;
                // Drain bounded chunks; no credential-bearing process output is persisted.
                new Thread(() -> {
                    try (InputStream output = current.getInputStream()) {
                        byte[] buffer = new byte[8192];
                        java.io.ByteArrayOutputStream line = new java.io.ByteArrayOutputStream();
                        boolean overflow = false; int count;
                        while ((count = output.read(buffer)) != -1) for (int i = 0; i < count; i++) {
                            if (buffer[i] == '\n') {
                                if (!overflow) activity(line.toString("UTF-8"), current, run);
                                line.reset(); overflow = false;
                            } else if (line.size() < 4096) line.write(buffer[i]);
                            else overflow = true;
                        }
                        int exit = current.waitFor();
                        if (process == current && generation == run) { process = null; failed = exit != 0; stopSelf(startId); }
                    } catch (Exception e) { if (process == current) { failed = true; current.destroyForcibly(); process = null; stopSelf(startId); } }
                }, "local-device-output").start();
            } catch (Exception e) { failed = true; stopSelf(startId); }
            finally { preparing = false; }
        });
        return START_NOT_STICKY;
    }

    @Override public void onConfigurationChanged(android.content.res.Configuration configuration) {
        super.onConfigurationChanged(configuration);
        if (overlay != null) { overlay.hide(); refreshOverlay(); }
    }

    @Override public void onTaskRemoved(Intent intent) { stopSelf(); }
    @Override public void onDestroy() {
        stopping = true;
        com.lambchat.phone.PhoneControl.stopBridge();
        if (instance == this) instance = null;
        if (overlay != null) overlay.hide();
        main.removeCallbacksAndMessages(null);
        runtimeRoot = null;
        if (networkCallback != null) getSystemService(android.net.ConnectivityManager.class).unregisterNetworkCallback(networkCallback);
        Process current = process;
        if (current != null) current.destroy();
        OPERATIONS.execute(() -> { if (process == current) try { stopProcess(); } catch (Exception e) { failed = true; } });
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
