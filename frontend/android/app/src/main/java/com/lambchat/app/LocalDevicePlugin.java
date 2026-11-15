package com.lambchat.app;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import androidx.activity.result.ActivityResult;
import androidx.core.content.ContextCompat;
import com.getcapacitor.*;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.UUID;

@CapacitorPlugin(name = "LocalDevice")
public class LocalDevicePlugin extends Plugin {
    private static volatile LocalDevicePlugin active;
    static volatile JSObject taskContext = new JSObject();
    static volatile String pendingOverlayId;
    static volatile String lastOverlayAction;
    @Override public void load() { active = this; }
    @Override protected void handleOnDestroy() { if (active == this) { active = null; taskContext = new JSObject(); pendingOverlayId = null; } }
    @PluginMethod public void setOverlayContext(PluginCall call) {
        JSObject next = call.getData();
        if (next.optString("scope").length() > 1024 || next.optString("message").length() > 16000) { call.reject("Invalid overlay context"); return; }
        taskContext = next; LocalDeviceService.refreshOverlay(); call.resolve();
    }
    @PluginMethod public void clearOverlayContext(PluginCall call) {
        if (taskContext.optString("scope").equals(call.getString("scope"))) taskContext = new JSObject();
        LocalDeviceService.refreshOverlay(); call.resolve();
    }
    @PluginMethod public void overlayResult(PluginCall call) {
        if (call.getString("id", "").equals(pendingOverlayId)) {
            pendingOverlayId = null;
            LocalDeviceService.overlayResult(Boolean.TRUE.equals(call.getBoolean("accepted")));
        }
        call.resolve();
    }
    static boolean overlayAction(String action, String text) {
        LocalDevicePlugin plugin = active;
        JSObject scope = taskContext;
        if (plugin == null || scope.optString("scope").isEmpty() || pendingOverlayId != null) return false;
        if (action.equals("task") && (!scope.optBoolean("ready") || text.trim().isEmpty() || text.length() > 16000)) return false;
        if ((action.equals("approve") || action.equals("reject")) && !scope.optBoolean("canApprove")) return false;
        String id = UUID.randomUUID().toString(); pendingOverlayId = id; lastOverlayAction = action;
        JSObject event = new JSObject().put("id", id).put("scope", scope.optString("scope")).put("action", action)
                .put("text", text).put("approvalId", scope.optString("approvalId")).put("message", scope.optString("message"));
        plugin.notifyListeners("overlayAction", event);
        new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> {
            if (id.equals(pendingOverlayId)) { pendingOverlayId = null; LocalDeviceService.overlayResult(false); }
        }, 15000);
        return true;
    }

    @Override protected void handleOnResume() { LocalDeviceService.setAppVisible(true); }
    @Override protected void handleOnPause() { LocalDeviceService.setAppVisible(false); }

    private JSObject overlayState() {
        JSObject state = new JSObject();
        state.put("enabled", LocalDeviceOverlay.enabled(getContext()));
        state.put("granted", android.provider.Settings.canDrawOverlays(getContext()));
        return state;
    }

    @PluginMethod public void phoneState(PluginCall call) { try { call.resolve(JSObject.fromJSONObject(com.lambchat.phone.PhoneControl.state())); } catch (Exception e) { call.reject("Cannot read phone state", e); } }

    @PluginMethod public void phoneDiscover(PluginCall call) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try { call.resolve(JSObject.fromJSONObject(com.lambchat.phone.PhoneDiscovery.discover(getContext()))); }
            catch (Exception e) { call.reject("Cannot discover local debugging ports", e); }
        });
    }
    @PluginMethod public void phonePair(PluginCall call) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try { com.lambchat.phone.PhoneControl.pair(getContext(), call.getInt("port", 0), call.getString("code", "")); call.resolve(); }
            catch (Exception e) { call.reject("Phone pairing failed", e); }
        });
    }

    @PluginMethod public void phoneConnect(PluginCall call) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try { com.lambchat.phone.PhoneControl.connect(getContext(), call.getInt("port", 0), Boolean.TRUE.equals(call.getBoolean("background", true))); call.resolve(JSObject.fromJSONObject(com.lambchat.phone.PhoneControl.state())); }
            catch (Exception e) { call.reject("Phone connection failed", e); }
        });
    }

    @PluginMethod public void phoneAction(PluginCall call) {
        String action = call.getString("action", "");
        if (action.equals("accessibility") || action.equals("debugging")) {
            try { getActivity().startActivity(new Intent(action.equals("accessibility") ? android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS : android.provider.Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)); call.resolve(); }
            catch (Exception e) { call.reject("Cannot open Android settings", e); }
            return;
        }
        if (action.equals("pause")) com.lambchat.phone.PhoneControl.pause();
        LocalDeviceService.OPERATIONS.execute(() -> {
            try {
                switch (action) {
                    case "pause": break;
                    case "resume": com.lambchat.phone.PhoneControl.resume(); break;
                    case "takeover": com.lambchat.phone.PhoneControl.takeover(); break;
                    case "disconnect": com.lambchat.phone.PhoneControl.disconnect(); break;
                    default: throw new IllegalArgumentException("Unknown phone action");
                }
                call.resolve(JSObject.fromJSONObject(com.lambchat.phone.PhoneControl.state()));
            } catch (Exception e) { call.reject("Phone control action failed", e); }
        });
    }

    @PluginMethod public void overlayStatus(PluginCall call) { call.resolve(overlayState()); }

    @PluginMethod public void setOverlayEnabled(PluginCall call) {
        boolean enabled = Boolean.TRUE.equals(call.getBoolean("enabled"));
        if (enabled && !LocalDeviceRuntime.supported()) { call.reject("Unsupported device"); return; }
        if (enabled && !android.provider.Settings.canDrawOverlays(getContext())) {
            try {
                Intent intent = new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getContext().getPackageName()));
                startActivityForResult(call, intent, "overlayPermissionResult");
            } catch (Exception e) { call.reject("Cannot open overlay permission settings", e); }
            return;
        }
        LocalDeviceOverlay.enable(getContext(), enabled);
        call.resolve(overlayState());
    }

    @ActivityCallback private void overlayPermissionResult(PluginCall call, ActivityResult result) {
        if (call == null) return;
        LocalDeviceOverlay.enable(getContext(), android.provider.Settings.canDrawOverlays(getContext()));
        call.resolve(overlayState());
    }

    @PluginMethod public void invoke(PluginCall call) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try {
                String command = call.getString("command", "");
                JSObject args = call.getObject("args", new JSObject());
                LocalDeviceStore store = new LocalDeviceStore(getContext());
                Object value = JSONObject.NULL;
                switch (command) {
                    case "daemon_process_status":
                        value = LocalDeviceService.status();
                        if ("stopped".equals(value) && store.read() != null) value = "paired";
                        break;
                    case "read_machine_id": value = store.machineId(); break;
                    case "read_pairing_pat": {
                        JSONObject data = store.read();
                        if (data != null && LocalDeviceStore.origin(data.getString("serverUrl")).equals(LocalDeviceStore.origin(args.getString("serverUrl"))))
                            value = data.getString("pat");
                        break;
                    }
                    case "save_pairing":
                        if (!LocalDeviceRuntime.supported()) throw new IllegalStateException("Unsupported device");
                        LocalDeviceService.stopProcess();
                        store.save(new JSONObject(args.toString()));
                        break;
                    case "write_confirm_policy": {
                        JSONObject data = store.read();
                        if (data == null) throw new IllegalStateException("Device is not paired");
                        String policy = args.getString("policy"); LocalDeviceStore.policy(policy);
                        data.put("confirmPolicy", policy); store.save(data); break;
                    }
                    case "clear_pairing":
                        LocalDeviceService.stopProcess(); store.clear();
                        getContext().stopService(new Intent(getContext(), LocalDeviceService.class)); break;
                    case "restart_daemon":
                        if (!LocalDeviceRuntime.supported() || store.read() == null) throw new IllegalStateException("Device is not ready");
                        getActivity().runOnUiThread(() -> {
                            try { ContextCompat.startForegroundService(getContext(), new Intent(getContext(), LocalDeviceService.class)); call.resolve(); }
                            catch (Exception e) { call.reject("Cannot start local device", e); }
                        });
                        return;
                    default: throw new IllegalArgumentException("Unsupported local device operation");
                }
                JSObject result = new JSObject(); result.put("value", value); call.resolve(result);
            } catch (Exception e) { call.reject("Local device operation failed", e); }
        });
    }

    private File shared() throws Exception {
        File root = new File(new LocalDeviceStore(getContext()).home(), "workspaces/.shared");
        root.mkdirs();
        if (Files.isSymbolicLink(root.toPath()) || Files.isSymbolicLink(root.getParentFile().toPath()))
            throw new IOException("Invalid shared workspace");
        return root;
    }

    @PluginMethod public void listFiles(PluginCall call) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try {
                File[] files = shared().listFiles();
                JSONArray entries = new JSONArray();
                if (files != null) {
                    Arrays.sort(files, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));
                    for (File file : files) {
                        if (entries.length() >= 200) break;
                        if (Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS) && !file.getName().startsWith("."))
                            entries.put(new JSONObject().put("name", file.getName()).put("size", file.length()));
                    }
                }
                JSObject result = new JSObject(); result.put("files", entries); call.resolve(result);
            } catch (Exception e) { call.reject("Cannot list device files", e); }
        });
    }

    @PluginMethod public void importFile(PluginCall call) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        startActivityForResult(call, intent, "importResult");
    }

    @ActivityCallback private void importResult(PluginCall call, ActivityResult result) {
        if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null) { call.resolve(); return; }
        Uri uri = result.getData().getData();
        if (uri == null) { call.reject("No file selected"); return; }
        LocalDeviceService.OPERATIONS.execute(() -> {
            File pending = null;
            try {
                String name = "file";
                try (Cursor cursor = getContext().getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                    if (cursor != null && cursor.moveToFirst() && cursor.getString(0) != null) name = cursor.getString(0);
                }
                name = name.replaceAll("[\\\\/\\p{Cntrl}]", "_");
                if (name.length() > 100) name = name.substring(name.length() - 100);
                name = UUID.randomUUID().toString().substring(0, 8) + "-" + name;
                File root = shared();
                File target = LocalDeviceRuntime.child(root, name);
                pending = File.createTempFile(".import-", ".tmp", root);
                try (InputStream input = getContext().getContentResolver().openInputStream(uri);
                     OutputStream output = Files.newOutputStream(pending.toPath(), StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                    if (input == null) throw new IOException("Cannot open selected file");
                    copy(input, output);
                }
                Files.move(pending.toPath(), target.toPath());
                JSObject response = new JSObject(); response.put("name", name); call.resolve(response);
            } catch (Exception e) { call.reject("Cannot import device file", e); }
            finally { if (pending != null) pending.delete(); }
        });
    }

    @PluginMethod public void exportFile(PluginCall call) {
        try {
            File file = LocalDeviceRuntime.child(shared(), call.getString("name", ""));
            if (!Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS)) throw new IOException("File unavailable");
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, file.getName());
            startActivityForResult(call, intent, "exportResult");
        } catch (Exception e) { call.reject("Cannot export device file", e); }
    }

    @ActivityCallback private void exportResult(PluginCall call, ActivityResult result) {
        if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null) { call.resolve(); return; }
        Uri uri = result.getData().getData();
        if (uri == null) { call.reject("No destination selected"); return; }
        LocalDeviceService.OPERATIONS.execute(() -> {
            try {
                File file = LocalDeviceRuntime.child(shared(), call.getString("name", ""));
                try (InputStream input = Files.newInputStream(file.toPath(), LinkOption.NOFOLLOW_LINKS);
                     OutputStream output = getContext().getContentResolver().openOutputStream(uri, "wt")) {
                    if (output == null) throw new IOException("Cannot open destination");
                    copy(input, output);
                }
                call.resolve();
            } catch (Exception e) { call.reject("Cannot export device file", e); }
        });
    }

    private static void copy(InputStream input, OutputStream output) throws IOException {
        byte[] buffer = new byte[65536]; long total = 0; int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > 512L * 1024 * 1024) throw new IOException("File exceeds 512 MiB limit");
            output.write(buffer, 0, count);
        }
    }
}
