package com.lambchat.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.speech.RecognizerIntent;
import java.util.ArrayList;

/** User-initiated system dictation; the recognized draft is never sent automatically. */
public final class PhoneVoiceActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LocalDeviceService.setAppVisible(true);
        if (state != null) return;
        try {
            startActivityForResult(new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                    .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1), 1);
        } catch (Exception e) { LocalDeviceService.overlayResult(false); finish(); }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 1 && result == RESULT_OK && data != null) {
            ArrayList<String> words = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (words != null && !words.isEmpty()) LocalDeviceService.overlayDraft(words.get(0));
        }
        finish();
    }
    @Override protected void onDestroy() { LocalDeviceService.setAppVisible(false); super.onDestroy(); }
}
