package com.lambchat.fixture;

import android.app.Activity;
import android.os.Bundle;
import android.widget.*;

/** Deliberately separate test APK surface; never packaged in the user's application. */
public class PhoneFixtureActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        EditText text = new EditText(this); text.setHint("Phone test input"); text.setText("initial"); body.addView(text);
        TextView result = new TextView(this); result.setText("waiting"); body.addView(result);
        Button button = new Button(this); button.setText("Confirm fixture"); button.setAllCaps(false);
        button.setOnClickListener(view -> result.setText("clicked " + text.getText()));
        button.setOnLongClickListener(view -> { result.setText("long_clicked"); return true; });
        body.addView(button);
        ScrollView scroll = new ScrollView(this); LinearLayout rows = new LinearLayout(this); rows.setOrientation(LinearLayout.VERTICAL);
        for (int i = 0; i < 60; i++) { TextView row = new TextView(this); row.setText("Fixture row " + i); row.setPadding(8, 24, 8, 24); rows.addView(row); }
        scroll.addView(rows); body.addView(scroll); setContentView(body);
    }
}
