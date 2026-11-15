package com.lambchat.app;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Insets;
import android.graphics.drawable.GradientDrawable;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.*;
import android.widget.*;
import androidx.appcompat.view.ContextThemeWrapper;

/** A small non-focusable status capsule; no screen capture or accessibility access. */
final class LocalDeviceOverlay {
    private final LocalDeviceService service;
    private Context context;
    private final WindowManager windows;
    private final SharedPreferences preferences;
    private LinearLayout root;
    private LinearLayout actions;
    private TextView header;
    private TextView detail;
    private EditText taskInput;
    private String taskDraft = "";
    private Button sendTask, stopTask, approve, reject, pausePhone, resumePhone, takeoverPhone;

    private WindowManager.LayoutParams layout;
    private boolean expanded;
    private boolean left;
    private float fraction;
    private float downX, downY;
    private int startX, startY;
    private boolean dragged;
    private String state = "connecting";
    private int active;

    LocalDeviceOverlay(LocalDeviceService service) {
        this.service = service;
        context = new ContextThemeWrapper(localizedContext(service), R.style.AppTheme_NoActionBar);
        windows = service.getSystemService(WindowManager.class);
        preferences = service.getSharedPreferences("local-device-overlay", Context.MODE_PRIVATE);
        left = preferences.getBoolean("left", false);
        fraction = preferences.getFloat("position", 0.35f);
    }

    static Context localizedContext(Context context) {
        String language = context.getSharedPreferences("local-device-overlay", Context.MODE_PRIVATE).getString("language", "");
        if (!java.util.Arrays.asList("en", "zh", "ja", "ko", "ru").contains(language)) return context;
        android.content.res.Configuration config = new android.content.res.Configuration(context.getResources().getConfiguration());
        config.setLocale(java.util.Locale.forLanguageTag(language));
        return context.createConfigurationContext(config);
    }

    static boolean enabled(Context context) {
        return context.getSharedPreferences("local-device-overlay", Context.MODE_PRIVATE).getBoolean("enabled", false);
    }

    static void enable(Context context, boolean enabled) {
        context.getSharedPreferences("local-device-overlay", Context.MODE_PRIVATE).edit().putBoolean("enabled", enabled).apply();
        LocalDeviceService.refreshOverlay();
    }

    private int dp(int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }
    private int color(int attribute) {
        TypedValue value = new TypedValue();
        context.getTheme().resolveAttribute(attribute, value, true);
        return value.resourceId != 0 ? context.getColor(value.resourceId) : value.data;
    }

    void visibility(boolean visible) {
        Context localized = localizedContext(service);
        if (!context.getResources().getConfiguration().getLocales().equals(localized.getResources().getConfiguration().getLocales())) {
            hide();
            context = new ContextThemeWrapper(localized, R.style.AppTheme_NoActionBar);
        }
        if (!visible || !enabled(context) || !Settings.canDrawOverlays(context)) { hide(); return; }
        if (root != null) return;
        root = new LinearLayout(context);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(8), dp(4), dp(8), dp(4));
        GradientDrawable background = new GradientDrawable();
        background.setColor(color(android.R.attr.colorBackground));
        background.setCornerRadius(dp(12));
        root.setBackground(background);
        root.setElevation(dp(4));
        header = new TextView(context);
        header.setTextSize(14);
        header.setTextColor(color(android.R.attr.textColorPrimary));
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setMinHeight(dp(44));
        header.setMaxWidth(dp(280));
        header.setMaxLines(1);
        header.setEllipsize(android.text.TextUtils.TruncateAt.END);
        header.setPadding(dp(8), 0, dp(8), 0);
        header.setFocusable(true);
        header.setClickable(true);
        header.setOnClickListener(view -> { expanded = !expanded; render(); });
        header.setOnTouchListener(this::drag);
        root.addView(header);
        actions = new LinearLayout(context);
        actions.setOrientation(LinearLayout.VERTICAL);
        detail = new TextView(context);
        detail.setTextSize(12);
        detail.setTextColor(color(android.R.attr.textColorSecondary));
        detail.setPadding(dp(8), dp(4), dp(8), dp(8));
        detail.setText(R.string.local_device_overlay_detail);
        actions.addView(detail);
        taskInput = new EditText(context);
        taskInput.setTextSize(14); taskInput.setTextColor(color(android.R.attr.textColorPrimary));
        taskInput.setHint(R.string.phone_task_hint); taskInput.setText(taskDraft);
        taskInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        taskInput.setMinLines(2); taskInput.setMaxLines(4);
        taskInput.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(16000)});
        taskInput.setOnFocusChangeListener((view, focused) -> { if (focused && layout != null) { layout.flags &= ~WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE; windows.updateViewLayout(root, layout); } });
        actions.addView(taskInput, new LinearLayout.LayoutParams(-1, -2));
        button(R.string.phone_voice, () -> service.startActivity(new Intent(service, PhoneVoiceActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
        button(R.string.phone_screenshot, service::captureForTask);
        sendTask = button(R.string.phone_task_send, () -> send("task"));
        stopTask = button(R.string.phone_task_stop, () -> send("stop"));
        approve = button(R.string.phone_approve, () -> send("approve"));
        reject = button(R.string.phone_reject, () -> send("reject"));
        pausePhone = button(R.string.phone_pause, () -> { com.lambchat.phone.PhoneControl.pause(); refresh(); });
        resumePhone = button(R.string.phone_resume, () -> phoneAction(false));
        takeoverPhone = button(R.string.phone_takeover, () -> { com.lambchat.phone.PhoneControl.pause(); phoneAction(true); });
        LinearLayout pairing = new LinearLayout(context); pairing.setOrientation(LinearLayout.VERTICAL); pairing.setVisibility(View.GONE);
        EditText pairPort = new EditText(context); pairPort.setHint(R.string.phone_pair_port); pairPort.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        EditText pairCode = new EditText(context); pairCode.setHint(R.string.phone_pair_code); pairCode.setInputType(android.text.InputType.TYPE_CLASS_NUMBER | android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        pairPort.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(5)});
        pairCode.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(6)});
        android.view.View.OnFocusChangeListener focus = (view, focused) -> { if (focused && layout != null) { layout.flags &= ~WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE; windows.updateViewLayout(root, layout); } };
        pairPort.setOnFocusChangeListener(focus); pairCode.setOnFocusChangeListener(focus);
        pairing.addView(pairPort); pairing.addView(pairCode);
        Button pair = new Button(context); pair.setText(R.string.phone_pair); pair.setOnClickListener(view -> {
            String port = pairPort.getText().toString(), code = pairCode.getText().toString(); pairCode.setText(""); pair.setEnabled(false);
            LocalDeviceService.OPERATIONS.execute(() -> {
                boolean ok;
                try { com.lambchat.phone.PhoneControl.pair(context, Integer.parseInt(port), code); ok = true; } catch (Exception e) { ok = false; }
                final boolean success = ok;
                service.getMainExecutor().execute(() -> { pair.setEnabled(true); if (detail != null) detail.setText(success ? R.string.phone_pair_done : R.string.phone_action_failed); });
            });
        }); pairing.addView(pair);
        button(R.string.phone_pair, () -> { pairing.setVisibility(pairing.getVisibility() == View.GONE ? View.VISIBLE : View.GONE); render(); });
        actions.addView(pairing);

        button(R.string.local_device_open, () -> {
            service.startActivity(new Intent(service, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT));
            expanded = false; render();
        });
        button(R.string.local_device_stop, service::stopSelf);
        button(R.string.local_device_overlay_hide, () -> enable(context, false));
        ScrollView scroll = new ScrollView(context);
        scroll.addView(actions);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, -2));

        layout = new WindowManager.LayoutParams(WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
                PixelFormat.TRANSLUCENT);
        layout.gravity = Gravity.TOP | Gravity.LEFT;
        root.setOnTouchListener((view, event) -> {
            if (event.getAction() == MotionEvent.ACTION_OUTSIDE) { expanded = false; render(); }
            return false;
        });
        try { windows.addView(root, layout); refresh(); }
        catch (RuntimeException denied) { hide(); }
    }

    private Button button(int label, Runnable action) {
        Button button = new Button(context);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(14);
        button.setMinHeight(dp(44));
        button.setOnClickListener(view -> action.run());
        actions.addView(button, new LinearLayout.LayoutParams(-1, -2));
        return button;
    }

    private void send(String action) {
        taskDraft = taskInput.getText().toString();
        if (!LocalDevicePlugin.overlayAction(action, taskDraft)) detail.setText(R.string.phone_action_failed);
        refresh();
    }
    private void phoneAction(boolean takeover) {
        LocalDeviceService.OPERATIONS.execute(() -> {
            try { if (takeover) com.lambchat.phone.PhoneControl.takeover(); else com.lambchat.phone.PhoneControl.resume(); }
            catch (Exception e) { service.getMainExecutor().execute(() -> { if (detail != null) detail.setText(R.string.phone_action_failed); }); }
            service.getMainExecutor().execute(this::refresh);
        });
    }
    void draft(String text) {
        taskDraft = (taskDraft.isEmpty() ? "" : taskDraft + "\n") + text;
        if (taskDraft.length() > 16000) taskDraft = taskDraft.substring(0, 16000);
        if (taskInput != null) taskInput.setText(taskDraft);
        expanded = true;
        refresh();
    }
    void result(boolean accepted) {
        if (taskInput != null && accepted && "task".equals(LocalDevicePlugin.lastOverlayAction)) { taskInput.setText(""); taskDraft = ""; }
        refresh();
        if (!accepted && detail != null) detail.setText(R.string.phone_action_failed);
    }
    static String approvalMessage(Context context, String message) {
        java.util.regex.Matcher match = java.util.regex.Pattern.compile("^Computer control on machine ([a-zA-Z0-9_-]+): (.*)$", java.util.regex.Pattern.DOTALL).matcher(message);
        if (!match.matches()) return message;
        String operation = match.group(2);
        String suffix = " (includes a screenshot sent to the model)";
        boolean screenshot = operation.endsWith(suffix);
        if (screenshot) operation = operation.substring(0, operation.length() - suffix.length());
        return context.getString(R.string.phone_control_request, match.group(1), operation)
            + (screenshot ? "\n" + context.getString(R.string.phone_control_screenshot_notice) : "");
    }
    void refresh() {
        if (root == null) return;
        com.getcapacitor.JSObject task = LocalDevicePlugin.taskContext;
        boolean pending = LocalDevicePlugin.pendingOverlayId != null;
        detail.setText(task.optString("message").isEmpty() ? context.getString(R.string.phone_task_scope) : approvalMessage(context, task.optString("message")));
        sendTask.setEnabled(task.optBoolean("ready") && !pending);
        stopTask.setVisibility(task.optBoolean("running") ? View.VISIBLE : View.GONE);
        stopTask.setEnabled(!pending);
        approve.setVisibility(task.optBoolean("canApprove") ? View.VISIBLE : View.GONE);
        reject.setVisibility(task.optBoolean("canApprove") ? View.VISIBLE : View.GONE);
        approve.setEnabled(!pending); reject.setEnabled(!pending);
        org.json.JSONObject phone = com.lambchat.phone.PhoneControl.state();
        pausePhone.setVisibility(phone.optBoolean("connected") && !phone.optBoolean("paused") ? View.VISIBLE : View.GONE);
        resumePhone.setVisibility(phone.optBoolean("connected") && phone.optBoolean("paused") ? View.VISIBLE : View.GONE);
        takeoverPhone.setVisibility(phone.optBoolean("connected") && phone.optInt("display") != 0 ? View.VISIBLE : View.GONE);
        render();
    }

    void update(String state, int active) {
        this.state = state;
        this.active = active;
        render();
    }

    private String label() {
        if (LocalDevicePlugin.pendingOverlayId != null) return context.getString(R.string.phone_submitting);
        if (!LocalDevicePlugin.taskContext.optString("approvalId").isEmpty()) return context.getString(R.string.phone_waiting_approval);
        if (active == 0 && LocalDevicePlugin.taskContext.optBoolean("running")) return context.getString(R.string.phone_working);
        switch (state) {
            case "executing": return context.getString(R.string.local_device_executing, active);
            case "completed": return context.getString(R.string.local_device_completed);
            case "failed": return context.getString(R.string.local_device_failed);
            case "idle": return context.getString(R.string.local_device_idle);
            case "offline": return context.getString(R.string.local_device_offline);
            default: return context.getString(R.string.local_device_connecting);
        }
    }

    private void render() {
        if (root == null) return;
        root.setAlpha(1);
        header.setText("LambChat · " + label());
        header.setContentDescription(header.getText() + ", " + context.getString(expanded ? R.string.local_device_collapse : R.string.local_device_expand));
        ((View)actions.getParent()).setVisibility(expanded ? View.VISIBLE : View.GONE);
        if (!expanded) {
            ((android.view.inputmethod.InputMethodManager)context.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(), 0);
            layout.flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
        }
        android.view.ViewGroup.LayoutParams scrollParams = ((View)actions.getParent()).getLayoutParams();
        scrollParams.height = expanded ? Math.min(dp(400), Math.max(dp(120), area().height() - dp(60))) : 0;
        ((View)actions.getParent()).setLayoutParams(scrollParams);
        layout.width = expanded ? Math.min(dp(280), area().width()) : WindowManager.LayoutParams.WRAP_CONTENT;
        place();
    }

    private Rect area() {
        WindowMetrics metrics = windows.getCurrentWindowMetrics();
        Rect bounds = new Rect(metrics.getBounds());
        Insets inset = metrics.getWindowInsets().getInsetsIgnoringVisibility(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
        bounds.left += inset.left + dp(4); bounds.top += inset.top + dp(4);
        bounds.right -= inset.right + dp(4); bounds.bottom -= inset.bottom + dp(4);
        return bounds;
    }

    private void place() {
        if (root == null) return;
        Rect area = area();
        root.measure(View.MeasureSpec.makeMeasureSpec(area.width(), View.MeasureSpec.AT_MOST), View.MeasureSpec.makeMeasureSpec(area.height(), View.MeasureSpec.AT_MOST));
        int width = expanded ? Math.min(dp(280), area.width()) : root.getMeasuredWidth();
        layout.x = left ? area.left : Math.max(area.left, area.right - width);
        layout.y = area.top + Math.round(Math.max(0, area.height() - root.getMeasuredHeight()) * Math.max(0, Math.min(1, fraction)));
        try { windows.updateViewLayout(root, layout); } catch (RuntimeException denied) { hide(); }
    }

    private boolean drag(View view, MotionEvent event) {
        if (root == null) return false;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                root.setAlpha(1);
                downX = event.getRawX(); downY = event.getRawY(); startX = layout.x; startY = layout.y; dragged = false;
                return true;
            case MotionEvent.ACTION_MOVE:
                float dx = event.getRawX() - downX, dy = event.getRawY() - downY;
                if (Math.hypot(dx, dy) > ViewConfiguration.get(context).getScaledTouchSlop()) dragged = true;
                if (dragged) {
                    Rect area = area();
                    layout.x = Math.max(area.left, Math.min(area.right - root.getWidth(), startX + Math.round(dx)));
                    layout.y = Math.max(area.top, Math.min(area.bottom - root.getHeight(), startY + Math.round(dy)));
                    try { windows.updateViewLayout(root, layout); } catch (RuntimeException denied) { hide(); }
                }
                return true;
            case MotionEvent.ACTION_UP:
                if (!dragged) view.performClick();
                else {
                    Rect area = area();
                    left = layout.x + root.getWidth() / 2 < area.centerX();
                    fraction = Math.max(0, Math.min(1, (float)(layout.y - area.top) / Math.max(1, area.height() - root.getHeight())));
                    preferences.edit().putBoolean("left", left).putFloat("position", fraction).apply();
                    render();
                }
                return true;
            case MotionEvent.ACTION_CANCEL: render(); return true;
            default: return false;
        }
    }

    void hide() {
        if (taskInput != null) taskDraft = taskInput.getText().toString();
        if (root != null) try { windows.removeView(root); } catch (RuntimeException ignored) { }
        root = null;
    }
}
