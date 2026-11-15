package com.lambchat.phone;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.app.KeyguardManager;
import android.content.Intent;
import android.graphics.*;
import android.os.*;
import android.view.accessibility.*;
import org.json.*;
import java.io.ByteArrayOutputStream;
import java.util.*;
import java.util.concurrent.*;

/** User-enabled screen access. Every input is pinned to a fresh session observation. */
public final class PhoneAccessibility extends AccessibilityService {
    public static volatile PhoneAccessibility instance;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<Integer, AccessibilityNodeInfo> nodes = new HashMap<>();
    private volatile String snapshot;
    private String session, app;
    private int display;
    private long observedAt;
    private volatile long generation;
    private long observedGeneration;
    private boolean observedScreenshot;

    @Override protected void onServiceConnected() { instance = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        generation++;
    }
    @Override public void onInterrupt() { invalidate(); }
    @Override public boolean onUnbind(Intent intent) { if (instance == this) instance = null; invalidate(); return super.onUnbind(intent); }
    @Override public void onDestroy() { if (instance == this) instance = null; invalidate(); super.onDestroy(); }
    public void invalidate() { snapshot = null; }
    private void clearNodes() { for (AccessibilityNodeInfo node : nodes.values()) node.recycle(); nodes.clear(); }
    static JSONObject error(String code) throws JSONException { return new JSONObject().put("error", code); }

    public synchronized JSONObject execute(String op, JSONObject args, int targetDisplay) throws Exception {
        if (getSystemService(KeyguardManager.class).isKeyguardLocked()) return error("device_locked");
        String targetApp = args.optString("name", args.optString("app", ""));
        if (targetApp.equals(getPackageName()) || targetApp.equals("com.android.settings") || targetApp.contains("permissioncontroller")) return error("local_consent_ui_protected");
        if (op.equals("state") || op.equals("windows")) return observe(args, targetDisplay, targetApp, op.equals("windows"));
        if (snapshot == null || !snapshot.equals(args.optString("snapshot_id")) || !session.equals(args.optString("session_id")) ||
                !app.equals(targetApp) || display != targetDisplay || observedGeneration != generation || SystemClock.uptimeMillis() - observedAt > 60000) return error("stale_state");
        if (args.optString("coordinate_space").equals("screenshot") && !observedScreenshot) return error("snapshot_has_no_screenshot");
        JSONObject target = args.optJSONObject("target");
        AccessibilityNodeInfo node = target == null ? null : nodes.get(target.optInt("index", -1));
        if (node != null && (!node.refresh() || !node.isVisibleToUser() || !app.contentEquals(node.getPackageName() == null ? "" : node.getPackageName()) || node.isPassword())) return error("element_unavailable");
        boolean success = false;
        if ((op.equals("set_value") || op.equals("type"))) {
            if (node == null) for (AccessibilityNodeInfo candidate : nodes.values()) if (candidate.isFocused() && candidate.isEditable()) { node = candidate; break; }
            if (node == null || node.isPassword() || !node.isEditable() || !node.refresh() || !app.contentEquals(node.getPackageName() == null ? "" : node.getPackageName())) return error("editable_element_required");
            String value = args.optString(op.equals("set_value") ? "value" : "text", "");
            if (value.length() > 16000) return error("input_too_large");
            if (op.equals("type")) {
                String previous = node.getText() == null ? "" : node.getText().toString();
                int from = node.getTextSelectionStart(), to = node.getTextSelectionEnd();
                if (from < 0 || to < from || to > previous.length()) from = to = previous.length();
                value = previous.substring(0, from) + value + previous.substring(to);
            }
            if (value.length() > 32000) return error("input_too_large");
            Bundle bundle = new Bundle(); bundle.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
            success = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, bundle);
        } else if (op.equals("click") && node != null) {
            int count = args.optInt("click_count", 1);
            if (count < 1 || count > 3) return error("invalid_click_count");
            if (count == 1) success = node.performAction(args.optString("mouse_button").equals("right") ? AccessibilityNodeInfo.ACTION_LONG_CLICK : AccessibilityNodeInfo.ACTION_CLICK);
            else {
                Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
                Path path = new Path(); path.moveTo(bounds.centerX(), bounds.centerY());
                success = gesture(path, 80, count);
            }
        } else if (op.equals("action") && node != null) {
            String action = args.optString("element_action");
            int id = action.equals("long_click") ? AccessibilityNodeInfo.ACTION_LONG_CLICK : action.equals("click") ? AccessibilityNodeInfo.ACTION_CLICK : action.equals("focus") ? AccessibilityNodeInfo.ACTION_FOCUS : 0;
            if (id == 0) return error("unsupported_action");
            success = node.performAction(id);
        } else if (op.equals("scroll") && node != null) {
            String direction = args.optString("scroll_direction", "down");
            success = node.performAction(direction.equals("up") || direction.equals("left") ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
        } else if (op.equals("click") && target != null && target.optString("type").equals("coordinate")) {
            float x = (float) target.getDouble("x"), y = (float) target.getDouble("y");
            android.view.Display screen = getSystemService(android.hardware.display.DisplayManager.class).getDisplay(display);
            if (screen == null) return error("display_unavailable");
            Point size = new Point(); screen.getRealSize(size);
            if (!Float.isFinite(x) || !Float.isFinite(y) || x < 0 || y < 0 || x >= size.x || y >= size.y) return error("invalid_coordinates");
            Path path = new Path(); path.moveTo(x, y);
            int count = args.optInt("click_count", 1);
            if (count < 1 || count > 3) return error("invalid_click_count");
            success = gesture(path, args.optString("mouse_button").equals("right") ? 650 : 80, count);
        } else if (op.equals("scroll")) {
            android.view.Display screen = getSystemService(android.hardware.display.DisplayManager.class).getDisplay(display);
            if (screen == null) return error("display_unavailable");
            Point size = new Point(); screen.getRealSize(size);
            String direction = args.optString("scroll_direction", "down");
            float x1 = size.x * .5f, x2 = x1, y1 = size.y * .7f, y2 = size.y * .3f;
            if (direction.equals("up")) { float swap = y1; y1 = y2; y2 = swap; }
            else if (direction.equals("left") || direction.equals("right")) { y1 = y2 = size.y * .5f; x1 = size.x * (direction.equals("left") ? .3f : .7f); x2 = size.x - x1; }
            Path path = new Path(); path.moveTo(x1, y1); path.lineTo(x2, y2); success = gesture(path, 350);
        } else if (op.equals("key")) {
            // Background key injection belongs to the shell helper, never the foreground global action.
            String key = args.optString("text").toLowerCase(Locale.ROOT);
            int code = key.equals("back") || key.equals("escape") ? 4 : key.equals("home") ? 3 : key.equals("enter") || key.equals("return") ? 66 : key.equals("tab") ? 61 : key.equals("backspace") ? 67 : -1;
            if (code < 0) return error("unsupported_key");
            int repeat = args.optInt("repeat", 1);
            if (repeat < 1 || repeat > 50) return error("invalid_repeat");
            for (int i = 0; i < repeat; i++) {
                if (PhoneControl.state().optBoolean("paused")) return error("phone_control_paused");
                PhoneControl.INSTANCE.key(display, code);
            }
            success = true;
        } else return error("unsupported_action");
        invalidate();
        return success ? new JSONObject().put("ok", true).put("platform", "android").put("requires_observation", true) : error("action_failed");
    }

    private boolean gesture(Path path, long duration) throws Exception { return gesture(path, duration, 1); }
    private boolean gesture(Path path, long duration, int count) throws Exception {
        CompletableFuture<Boolean> result = new CompletableFuture<>();
        GestureDescription.Builder builder = new GestureDescription.Builder().setDisplayId(display);
        for (int i = 0; i < count; i++) builder.addStroke(new GestureDescription.StrokeDescription(path, i * (duration + 100), duration));
        GestureDescription gesture = builder.build();
        main.post(() -> {
            if (PhoneControl.INSTANCE.state().optBoolean("paused")) { result.complete(false); return; }
            if (!dispatchGesture(gesture, new GestureResultCallback() {
                @Override public void onCompleted(GestureDescription description) { result.complete(true); }
                @Override public void onCancelled(GestureDescription description) { result.complete(false); }
            }, main)) result.complete(false);
        });
        return result.get(3, TimeUnit.SECONDS);
    }

    private JSONObject observe(JSONObject args, int targetDisplay, String targetApp, boolean windowsOnly) throws Exception {
        invalidate();
        clearNodes();
        if (targetApp.isEmpty()) return error("app_package_required");
        List<AccessibilityWindowInfo> windows = getWindowsOnAllDisplays().get(targetDisplay);
        JSONArray windowRows = new JSONArray(); StringBuilder tree = new StringBuilder();
        long start = SystemClock.uptimeMillis(); long before = generation;
        if (windows != null) for (AccessibilityWindowInfo window : windows) {
            AccessibilityNodeInfo root = window.getRoot();
            if (root == null) continue;
            if (!targetApp.contentEquals(root.getPackageName() == null ? "" : root.getPackageName())) { root.recycle(); continue; }
            Rect bounds = new Rect(); window.getBoundsInScreen(bounds);
            windowRows.put(new JSONObject().put("window_id", targetDisplay).put("title", String.valueOf(window.getTitle())).put("bounds", rect(bounds)).put("focused", window.isFocused()));
            walk(root, tree, 0, start);
        }
        if (windowRows.length() == 0) return error("app_not_visible_on_display");
        if (windowsOnly) return new JSONObject().put("windows", windowRows).put("platform", "android");
        snapshot = UUID.randomUUID().toString(); session = args.getString("session_id"); app = targetApp; display = targetDisplay; observedAt = SystemClock.uptimeMillis(); observedGeneration = before;
        JSONObject result = new JSONObject().put("state", tree.toString()).put("snapshot_id", snapshot).put("platform", "android").put("window_id", display).put("app", app);
        observedScreenshot = false;
        if (args.optBoolean("include_screenshot")) { result.put("screenshot", screenshot(display)); observedScreenshot = true; }
        return result;
    }

    private void walk(AccessibilityNodeInfo node, StringBuilder tree, int depth, long start) {
        if (!node.isVisibleToUser() || nodes.size() >= 350 || depth > 30 || SystemClock.uptimeMillis() - start > 3000) { node.recycle(); return; }
        int index = nodes.size(); nodes.put(index, node);
        Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
        String text = node.isPassword() ? "[protected]" : String.valueOf(node.getText() == null ? node.getContentDescription() == null ? "" : node.getContentDescription() : node.getText());
        if (text.length() > 180) text = text.substring(0, 180);
        tree.append(index).append(": ").append(node.getClassName()).append(" ").append(text.replace('\n', ' ')).append(" bounds=").append(bounds.toShortString());
        if (node.isClickable()) tree.append(" click"); if (node.isLongClickable()) tree.append(" long_click"); if (node.isEditable()) tree.append(" editable"); if (node.isScrollable()) tree.append(" scroll"); tree.append('\n');
        for (int i = 0; i < node.getChildCount(); i++) { AccessibilityNodeInfo child = node.getChild(i); if (child != null) walk(child, tree, depth + 1, start); }
    }
    private static JSONArray rect(Rect rect) { return new JSONArray(Arrays.asList(rect.left, rect.top, rect.width(), rect.height())); }

    public synchronized JSONObject captureForUser() throws Exception {
        if (getSystemService(KeyguardManager.class).isKeyguardLocked()) return error("device_locked");
        return screenshot(0);
    }

    private JSONObject screenshot(int displayId) throws Exception {
        CompletableFuture<JSONObject> result = new CompletableFuture<>();
        takeScreenshot(displayId, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult shot) {
                Bitmap hardware = null, bitmap = null;
                try {
                    hardware = Bitmap.wrapHardwareBuffer(shot.getHardwareBuffer(), shot.getColorSpace());
                    if (hardware == null) throw new IllegalStateException("empty screenshot");
                    bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false);
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                    for (int quality : new int[]{70, 50, 35}) {
                        bytes.reset(); bitmap.compress(Bitmap.CompressFormat.JPEG, quality, bytes);
                        if (bytes.size() <= 1300000) break;
                    }
                    if (bytes.size() > 1300000) throw new IllegalStateException("screenshot too large");
                    result.complete(new JSONObject().put("mime", "image/jpeg").put("width", bitmap.getWidth()).put("height", bitmap.getHeight()).put("data_b64", android.util.Base64.encodeToString(bytes.toByteArray(), android.util.Base64.NO_WRAP)));
                } catch (Exception e) { result.completeExceptionally(e); }
                finally {
                    if (bitmap != null) bitmap.recycle();
                    if (hardware != null) hardware.recycle();
                    shot.getHardwareBuffer().close();
                }
            }
            @Override public void onFailure(int errorCode) { result.completeExceptionally(new IllegalStateException("screenshot denied: " + errorCode)); }
        });
        return result.get(5, TimeUnit.SECONDS);
    }
}
