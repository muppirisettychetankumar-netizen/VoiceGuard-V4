package com.voiceguard.android;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.*;
import android.graphics.Color;

public class MainActivity extends Activity {
    static final int REQ=42;
    EditText url;
    TextView status;
    @Override public void onCreate(Bundle b){super.onCreate(b);
        LinearLayout box=new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(36,50,36,36); box.setBackgroundColor(Color.rgb(7,9,13));
        TextView title=new TextView(this); title.setText("VoiceGuard"); title.setTextColor(Color.rgb(115,224,180)); title.setTextSize(30); title.setGravity(Gravity.CENTER); box.addView(title);
        TextView sub=new TextView(this); sub.setText("SIH2614 • Android Call Protection Prototype"); sub.setTextColor(Color.LTGRAY); sub.setGravity(Gravity.CENTER); box.addView(sub);
        url=new EditText(this); url.setHint("https://your-service.onrender.com/ws/live"); url.setTextColor(Color.WHITE); url.setHintTextColor(Color.GRAY); url.setSingleLine(true); box.addView(url);
        Button save=new Button(this); save.setText("Save server URL"); box.addView(save);
        Button perms=new Button(this); perms.setText("Grant microphone permission"); box.addView(perms);
        Button test=new Button(this); test.setText("Start microphone test"); box.addView(test);
        status=new TextView(this); status.setTextColor(Color.LTGRAY); status.setPadding(0,30,0,0); box.addView(status);
        TextView info=new TextView(this); info.setText("Call detection uses Android Telecom/InCallService when the app is eligible. Audio capture of the remote cellular/VoIP party is OS/OEM restricted; this prototype monitors microphone audio unless a privileged/OEM call-audio source is available."); info.setTextColor(Color.GRAY); info.setPadding(0,25,0,0); box.addView(info);
        setContentView(box);
        SharedPreferences p=getSharedPreferences("vg",0); url.setText(p.getString("url",""));
        save.setOnClickListener(v->{p.edit().putString("url",url.getText().toString().trim()).apply(); status.setText("Server URL saved.");});
        perms.setOnClickListener(v->requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},REQ));
        test.setOnClickListener(v->{if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},REQ);return;} startService(new Intent(this,VoiceMonitorService.class).putExtra("manual",true)); status.setText("Microphone monitor started. Stop it from the notification.");});
    }
}
